import bpy
import numpy as np
import os
import mathutils

from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from ... import utils

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

class ADVLIGHTING_OT_movie_sampler(bpy.types.Operator, ImportHelper):
    bl_idname = "advlighting.movie_sampler"
    bl_label  = "Project Video"
    bl_options = {'REGISTER', 'UNDO'}
    
    filter_glob: StringProperty(default="*.mp4;*.mov;*.avi;*.mkv;*.webm", options={'HIDDEN'}, maxlen=255)

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not HAS_OPENCV:
            self.report({'ERROR'}, "OpenCV not found. Please check addon dependencies.")
            return {'CANCELLED'}

        if not os.path.exists(self.filepath): return {'CANCELLED'}

        sc = context.scene
        start, end, step = sc.adv_effector_start, sc.adv_effector_end, sc.adv_movie_step
        frames = list(range(start, end + 1, max(1, step)))

        # 1. IDENTIFY DRONES
        objs = []
        if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
             if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
                 g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects

        drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH' and "Absolute_Position" in o.keys()]
        if not drones:
            self.report({'ERROR'}, "No valid drones found. (Did you Bake Positions first?)")
            return {'CANCELLED'}

        cap = cv2.VideoCapture(self.filepath)
        if not cap.isOpened(): return {'CANCELLED'}
        
        vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vid_aspect = vid_w / max(1, vid_h)

        proj_matrix = context.region_data.perspective_matrix
        drone_paths = {} 
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        self.report({'INFO'}, "Calculating Projection Bounds...")
        
        for d in drones:
            drone_paths[d.name] = {}
            anim = getattr(d, "animation_data", None)
            
            fcurves = [None, None, None]
            if anim and anim.action:
                fcurves = [anim.action.fcurves.find('["Absolute_Position"]', index=i) for i in range(3)]
                
            px_base, py_base, pz_base = d["Absolute_Position"]

            for f in frames:
                px = fcurves[0].evaluate(f) if fcurves[0] else px_base
                py = fcurves[1].evaluate(f) if fcurves[1] else py_base
                pz = fcurves[2].evaluate(f) if fcurves[2] else pz_base
                
                vec4 = proj_matrix @ mathutils.Vector((px, py, pz, 1.0))
                
                if vec4.w > 0.001: 
                    nx, ny = vec4.x / vec4.w, vec4.y / vec4.w
                    min_x = min(min_x, nx)
                    max_x = max(max_x, nx)
                    min_y = min(min_y, ny)
                    max_y = max(max_y, ny)
                else:
                    nx, ny = -9999.0, -9999.0 
                
                drone_paths[d.name][f] = (nx, ny)

        if min_x == float('inf'):
            min_x, max_x = -1.0, 1.0
            min_y, max_y = -1.0, 1.0

        swarm_w = max(1.0, max_x - min_x)
        swarm_h = max(1.0, max_y - min_y)
        swarm_aspect = swarm_w / swarm_h
        
        cx, cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
        
        if vid_aspect > swarm_aspect: map_h, map_w = swarm_h, swarm_h * vid_aspect
        else: map_w, map_h = swarm_w, swarm_w / vid_aspect

        map_min_x = cx - (map_w / 2.0)
        map_min_y = cy - (map_h / 2.0)

        num_frames = len(frames)
        num_drones = len(drones)
        drone_names = [d.name for d in drones]
        
        px_coords = np.zeros((num_frames, num_drones, 2), dtype=np.int32)
        valid_mask = np.zeros((num_frames, num_drones), dtype=bool)
        sampled_colors = np.zeros((num_frames, num_drones, 3), dtype=np.float32)
        
        for f_idx, f in enumerate(frames):
            for d_idx, d_name in enumerate(drone_names):
                nx, ny = drone_paths[d_name][f]
                
                if nx != -9999.0:
                    u = (nx - map_min_x) / map_w
                    v = (ny - map_min_y) / map_h
                    
                    px_x = int(u * (vid_w - 1))
                    px_y = int((1.0 - v) * (vid_h - 1))
                    
                    if 0 <= px_x < vid_w and 0 <= px_y < vid_h:
                        px_coords[f_idx, d_idx, 0] = px_x
                        px_coords[f_idx, d_idx, 1] = px_y
                        valid_mask[f_idx, d_idx] = True

        self.report({'INFO'}, "Sampling Video Frames...")
        current_vid_frame = 0
        
        for f_idx, f in enumerate(frames):
            target_vid_frame = max(0, f - 1)
            
            if target_vid_frame < current_vid_frame:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_vid_frame)
                current_vid_frame = target_vid_frame
                
            while current_vid_frame < target_vid_frame:
                cap.grab(); current_vid_frame += 1
                
            ret, frame_img = cap.retrieve(); current_vid_frame += 1
            if not ret: continue
            
            x_coords = px_coords[f_idx, :, 0]
            y_coords = px_coords[f_idx, :, 1]
            mask = valid_mask[f_idx, :]
            
            if not np.any(mask): continue
            
            bgr_colors = frame_img[y_coords[mask], x_coords[mask]]
            sampled_colors[f_idx, mask, 0] = bgr_colors[:, 2] / 255.0
            sampled_colors[f_idx, mask, 1] = bgr_colors[:, 1] / 255.0 
            sampled_colors[f_idx, mask, 2] = bgr_colors[:, 0] / 255.0
        
        cap.release()
        drone_colors = {drone_names[i]: sampled_colors[:, i, :] for i in range(num_drones)}
        
        self.save_keyframes(context, drones, frames, drone_colors)
        self.report({'INFO'}, f"Successfully projected video onto {num_drones} drones.")
        return {'FINISHED'}

    def save_keyframes(self, context, drones, frames, drone_colors):
        sc = context.scene
        prop_name = f"Layer_{int(sc.adv_effector_target_layer)+1}"
        data_path = f'["{prop_name}"]'
        
        for d in drones:
            colors = drone_colors.get(d.name)
            if colors is None: continue
            
            if prop_name not in d.keys(): d[prop_name] = [0.0, 0.0, 0.0, 1.0]
            if not d.animation_data: d.animation_data_create()
            if not d.animation_data.action: d.animation_data.action = bpy.data.actions.new(name=f"{d.name}Action")
            action = d.animation_data.action
            
            f_np = np.array(frames, dtype=np.float32)
            
            for i in range(3):
                fc = action.fcurves.find(data_path=data_path, index=i)
                if not fc: fc = action.fcurves.new(data_path=data_path, index=i)
                
                existing = []
                for kp in fc.keyframe_points:
                    if kp.co[0] < frames[0] or kp.co[0] > frames[-1]:
                        existing.append((kp.co[0], kp.co[1]))
                
                new_keys = np.column_stack((f_np, colors[:, i]))
                if existing:
                    all_keys = np.vstack((existing, new_keys))
                    all_keys = all_keys[all_keys[:, 0].argsort()]
                else:
                    all_keys = new_keys
                
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(all_keys))
                fc.keyframe_points.foreach_set('co', all_keys.flatten())
                fc.update()