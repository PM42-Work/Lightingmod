import bpy
import numpy as np
import os
import mathutils
import bpy_extras
import math
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

class ADVLIGHTING_OT_load_gobo_image(bpy.types.Operator, ImportHelper):
    bl_idname = "advlighting.load_gobo_image"
    bl_label = "Import Image"
    bl_options = {'REGISTER', 'UNDO'}
    
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.exr", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        sc = context.scene
        if os.path.exists(self.filepath):
            img = bpy.data.images.load(self.filepath)
            sc.adv_gobo_image = img
            self.report({'INFO'}, f"Loaded: {img.name}")
        return {'FINISHED'}


class ADVLIGHTING_OT_spawn_gobo_camera(bpy.types.Operator):
    bl_idname = "advlighting.spawn_gobo_camera"
    bl_label = "Spawn Gobo Camera"
    
    def execute(self, context):
        sc = context.scene
        if not sc.adv_gobo_image:
            self.report({'ERROR'}, "Select or Import a Gobo Image first!")
            return {'CANCELLED'}
            
        cam_data = bpy.data.cameras.new(name="Gobo_Cam_Data")
        cam_data.show_background_images = True
        bg = cam_data.background_images.new()
        bg.image = sc.adv_gobo_image
        bg.alpha = 0.8  
        bg.display_depth = 'FRONT'
        
        # FIX 1: Explicitly force 'FIT' to prevent Viewport stretching
        bg.frame_method = 'FIT'
        
        cam_obj = bpy.data.objects.new("Gobo_Projector", cam_data)
        cam_obj["is_adv_gobo_cam"] = True 
        
        context.scene.collection.objects.link(cam_obj)
        
        # Snap to viewport perspective
        if context.region_data and context.area.type == 'VIEW_3D':
            cam_obj.matrix_world = context.region_data.view_matrix.inverted()
            context.space_data.camera = cam_obj
            context.region_data.view_perspective = 'CAMERA'
            
        sc.adv_gobo_camera = cam_obj
        self.report({'INFO'}, "Gobo Camera spawned! Align it to target your drones.")
        return {'FINISHED'}


class ADVLIGHTING_OT_remove_gobo_cameras(bpy.types.Operator):
    bl_idname = "advlighting.remove_gobo_cameras"
    bl_label = "Clear All Gobo Cameras"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        count = 0
        for obj in list(bpy.data.objects):
            if "is_adv_gobo_cam" in obj:
                cam_data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if cam_data:
                    bpy.data.cameras.remove(cam_data, do_unlink=True)
                count += 1
                
        context.scene.adv_gobo_camera = None
        self.report({'INFO'}, f"Deleted {count} Gobo Cameras")
        return {'FINISHED'}


class ADVLIGHTING_OT_apply_gobo(bpy.types.Operator):
    bl_idname = "advlighting.apply_gobo"
    bl_label = "Apply Gobo"

    def execute(self, context):
        if not HAS_OPENCV:
            self.report({'ERROR'}, "OpenCV not found. Run dependencies setup.")
            return {'CANCELLED'}

        sc = context.scene
        cam_obj = sc.adv_gobo_camera
        img_data = sc.adv_gobo_image
        
        if not cam_obj or not img_data:
            self.report({'ERROR'}, "Missing Gobo Camera or Image.")
            return {'CANCELLED'}
            
        path = bpy.path.abspath(img_data.filepath)
        if not os.path.exists(path):
            self.report({'ERROR'}, "Image file missing from disk.")
            return {'CANCELLED'}
            
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None: return {'CANCELLED'}
        h, w = img.shape
        
        ng = bpy.data.node_groups.get("AdvLightingGoboRamp")
        if not ng or "Ramp" not in ng.nodes: return {'CANCELLED'}
        ramp_lut = [list(ng.nodes["Ramp"].color_ramp.evaluate(i / 999.0))[:3] for i in range(1000)]
        
        start, end = sc.adv_effector_start, sc.adv_effector_end
        frames = list(range(start, end + 1))
        prop_name = f"Layer_{int(sc.adv_effector_target_layer)+1}"
        
        objs = []
        if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
             if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
                 g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects

        drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH' and "Absolute_Position" in o.keys()]
        if not drones:
            self.report({'ERROR'}, "No valid drones found.")
            return {'CANCELLED'}
        
        drone_paths = {}
        for d in drones:
            px, py, pz = d["Absolute_Position"]
            anim = getattr(d, "animation_data", None)
            fcurves = [anim.action.fcurves.find('["Absolute_Position"]', index=i) if anim and anim.action else None for i in range(3)]
            
            drone_paths[d.name] = {}
            for f in frames:
                x = fcurves[0].evaluate(f) if fcurves[0] else px
                y = fcurves[1].evaluate(f) if fcurves[1] else py
                z = fcurves[2].evaluate(f) if fcurves[2] else pz
                drone_paths[d.name][f] = mathutils.Vector((x,y,z))
                
        px_coords = np.zeros((len(frames), len(drones), 2), dtype=np.int32)
        valid_mask = np.zeros((len(frames), len(drones)), dtype=bool)
        
        render = sc.render
        cam_aspect = (render.resolution_x * render.pixel_aspect_x) / max(1.0, (render.resolution_y * render.pixel_aspect_y))
        img_aspect = w / max(1.0, h)
        
        # Grab Animation Settings
        pos_dir = sc.adv_gobo_pos_dir
        pos_speed = sc.adv_gobo_pos_speed
        pos_mode = sc.adv_gobo_pos_mode
        rot_speed = sc.adv_gobo_rot_speed
        rot_mode = sc.adv_gobo_rot_mode
        
        wm = context.window_manager
        wm.progress_begin(0, len(frames))
        
        for f_idx, f in enumerate(frames):
            sc.frame_set(f) 
            
            # --- CALCULATE 2D ANIMATION MATH ONCE PER FRAME ---
            t = f / 24.0 
            
            # Position Bounce/Cycle Logic
            if pos_mode == 'BOUNCE':
                offset_u = pos_dir[0] * (abs(((pos_speed * t - 1.0) % 4.0) - 2.0) - 1.0)
                offset_v = pos_dir[1] * (abs(((pos_speed * t - 1.0) % 4.0) - 2.0) - 1.0)
            else: # CYCLE
                offset_u = pos_dir[0] * pos_speed * t
                offset_v = pos_dir[1] * pos_speed * t
                
            # Rotation Bounce/Cycle Logic
            if rot_mode == 'BOUNCE':
                angle = (1.0 - abs(((rot_speed * t) % 2.0) - 1.0)) * (math.pi * 2.0)
            else: # CYCLE
                angle = rot_speed * t * math.pi * 2.0
                
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            
            for d_idx, d in enumerate(drones):
                p = drone_paths[d.name][f]
                co2d = bpy_extras.object_utils.world_to_camera_view(sc, cam_obj, p)
                
                if co2d.z > 0: 
                    u = co2d.x
                    v = co2d.y
                    
                    # 1. Aspect Ratio Correction
                    if cam_aspect > img_aspect:
                        u = (u - 0.5) * (cam_aspect / img_aspect) + 0.5
                    else:
                        v = (v - 0.5) * (img_aspect / cam_aspect) + 0.5
                        
                    # 2. Position Offset (Inverse Transform)
                    u -= offset_u
                    v -= offset_v
                    
                    # 3. Rotation (Inverse Transform around Center)
                    u_centered = u - 0.5
                    v_centered = v - 0.5
                    u_rot = u_centered * cos_a - v_centered * sin_a
                    v_rot = u_centered * sin_a + v_centered * cos_a
                    u = u_rot + 0.5
                    v = v_rot + 0.5
                    
                    # 4. Cycle Wrapping
                    if pos_mode == 'CYCLE':
                        u = u % 1.0
                        v = v % 1.0
                        
                    # 5. Output Valid Coordinates
                    if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                        ix = int(u * (w - 1))
                        iy = int((1.0 - v) * (h - 1)) 
                        if 0 <= ix < w and 0 <= iy < h:
                            px_coords[f_idx, d_idx, 0] = ix
                            px_coords[f_idx, d_idx, 1] = iy
                            valid_mask[f_idx, d_idx] = True
                            
            wm.progress_update(f_idx)
        wm.progress_end()
        
        sampled_luma = np.zeros((len(frames), len(drones)), dtype=np.float32)
        for f_idx in range(len(frames)):
            mask = valid_mask[f_idx, :]
            if not np.any(mask): continue
            xc, yc = px_coords[f_idx, mask, 0], px_coords[f_idx, mask, 1]
            sampled_luma[f_idx, mask] = img[yc, xc] / 255.0
            
        if sc.adv_gobo_invert:
            sampled_luma = 1.0 - sampled_luma
            sampled_luma[~valid_mask] = 0.0 
            
        indices = np.clip(np.floor(sampled_luma * 999), 0, 999).astype(np.int32)
        ramp_lut_np = np.array(ramp_lut, dtype=np.float32)
        final_colors = ramp_lut_np[indices]
        
        data_path = f'["{prop_name}"]'
        frames_np = np.array(frames, dtype=np.float32)
        
        for d_idx, d in enumerate(drones):
            if prop_name not in d.keys(): d[prop_name] = [0.0, 0.0, 0.0, 1.0]
            if not d.animation_data: d.animation_data_create()
            if not d.animation_data.action: d.animation_data.action = bpy.data.actions.new(name=f"{d.name}_Anim")
            action = d.animation_data.action
            
            for i in range(3):
                fc = action.fcurves.find(data_path=data_path, index=i)
                if not fc: fc = action.fcurves.new(data_path=data_path, index=i)
                
                col_arr = final_colors[:, d_idx, :]
                fc.keyframe_points.clear() 
                
                pts = np.column_stack((frames_np, col_arr[:, i]))
                num_points = len(pts)
                fc.keyframe_points.add(num_points)
                fc.keyframe_points.foreach_set('co', pts.flatten())
                fc.update()
                
                bool_arr = [False] * num_points
                fc.keyframe_points.foreach_set('select_control_point', bool_arr)
                fc.keyframe_points.foreach_set('select_left_handle', bool_arr)
                fc.keyframe_points.foreach_set('select_right_handle', bool_arr)
                
        self.report({'INFO'}, "Gobo Projection Baked Successfully!")
        return {'FINISHED'}