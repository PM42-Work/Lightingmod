import bpy
import numpy as np
import os
import sys

# Import File Browser Helper
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty

# Try to import OpenCV
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

class LIGHTINGMOD_OT_generate_uv(bpy.types.Operator):
    bl_idname = "lightingmod.generate_uv"
    bl_label  = "Add & Activate UV Map"
    
    def execute(self, context):
        name = context.scene.new_uv_map_name.strip()
        if not name:
            self.report({'ERROR'}, "Enter a UV Map Name")
            return {'CANCELLED'}
        for obj in context.selected_objects:
            if obj.type != 'MESH': continue
            uvl = obj.data.uv_layers
            if name not in uvl: uvl.new(name=name)
            uvl.active = uvl[name]
        self.report({'INFO'}, f"UV map '{name}' added & activated")
        return {'FINISHED'}

class LIGHTINGMOD_OT_movie_sampler(bpy.types.Operator, ImportHelper):
    """Pick a video file and map its pixels to drone colors over time"""
    bl_idname = "lightingmod.movie_sampler"
    bl_label  = "Sample Video File"
    bl_options = {'REGISTER', 'UNDO'}
    
    # ImportHelper props (Configures the file browser)
    filter_glob: StringProperty(
        default="*.mp4;*.mov;*.avi;*.mkv;*.webm",
        options={'HIDDEN'},
        maxlen=255,
    )

    def invoke(self, context, event):
        # --- THE FIX IS HERE ---
        # Do NOT put 'return' in front of fileselect_add. 
        # It returns None, but Blender expects a Set.
        context.window_manager.fileselect_add(self)
        
        # We manually return the status telling Blender "The modal window is running"
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # 1. CHECK DEPENDENCIES
        if not HAS_OPENCV:
            self.report({'ERROR'}, "OpenCV not found. Please check addon dependencies.")
            return {'CANCELLED'}

        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        sc = context.scene
        start, end, step = sc.effector_start, sc.effector_end, sc.movie_step
        if step < 1: step = 1
        
        frames = list(range(start, end + 1, step))
        if not frames:
            self.report({'ERROR'}, "No frames to process")
            return {'CANCELLED'}

        # 2. IDENTIFY DRONES
        objs = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects if sc.effector_selected_only else bpy.data.objects

        drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH']
        if not drones:
            self.report({'WARNING'}, "No valid drones found")
            return {'CANCELLED'}

        # 3. LOAD VIDEO
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            self.report({'ERROR'}, "Could not open video file.")
            return {'CANCELLED'}
        
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # 4. BUILD LOOKUP TABLE (UV -> Pixel Coordinate)
        uv_map_name = sc.movie_uv_map
        lookup_table = [] # [(obj, x, y), ...]
        
        # Dictionary to store results in memory: {obj_name: [(r,g,b), (r,g,b)...]}
        drone_data = {o.name: [] for o in drones} 
        
        for o in drones:
            if uv_map_name not in o.data.uv_layers: continue
            loops = o.data.uv_layers[uv_map_name].data
            if not loops: continue
            
            # Average UV Center
            avg_u, avg_v = 0.0, 0.0
            for lp in loops:
                avg_u += lp.uv[0]
                avg_v += lp.uv[1]
            count = len(loops)
            u = max(0.0, min(1.0, avg_u / count))
            v = max(0.0, min(1.0, avg_v / count))
            
            # Convert to Pixel Coordinates
            # OpenCV Origin = Top-Left. Blender UV Origin = Bottom-Left.
            px_x = int(u * (w - 1))
            px_y = int((1.0 - v) * (h - 1))
            
            lookup_table.append((o, px_x, px_y))

        if not lookup_table:
            cap.release()
            self.report({'WARNING'}, f"No drones found with UV Map '{uv_map_name}'")
            return {'CANCELLED'}

        # 5. PROCESS VIDEO (Memory Only)
        self.report({'INFO'}, "Processing Video...")
        
        for target_frame in frames:
            # Map Timeline Frame to Video Frame (assuming sync start at 0)
            video_frame = max(0, target_frame - 1)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, video_frame)
            ret, frame_img = cap.read()
            
            if not ret:
                # Pad with black if video ends
                for obj, x, y in lookup_table:
                    drone_data[obj.name].append((0.0, 0.0, 0.0))
            else:
                # OpenCV is BGR. We need RGB.
                # Accessing pixels: frame_img[y, x]
                for obj, x, y in lookup_table:
                    if 0 <= x < w and 0 <= y < h:
                        b, g, r = frame_img[y, x]
                        drone_data[obj.name].append((r/255.0, g/255.0, b/255.0))
                    else:
                        drone_data[obj.name].append((0.0, 0.0, 0.0))
        
        cap.release()
        
        # 6. BULK WRITE TO BLENDER
        self.save_keyframes(context, drones, frames, drone_data)
        
        self.report({'INFO'}, f"Successfully mapped video to {len(drones)} drones.")
        return {'FINISHED'}

    def save_keyframes(self, context, drones, frames, drone_data):
        """Writes collected data to F-Curves, preserving outside keys"""
        sc = context.scene
        target_prop = f'Layer_{int(sc.effector_target_layer)+1}'
        data_path = f'["{target_prop}"]'
        
        frames_arr = np.array(frames, dtype=np.float32)
        start_f = frames_arr[0]
        end_f = frames_arr[-1]
        
        for obj in drones:
            colors = drone_data.get(obj.name)
            if not colors or len(colors) != len(frames_arr):
                continue
                
            # Create Action if needed
            if not obj.animation_data: obj.animation_data_create()
            if not obj.animation_data.action:
                obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}Action")
            action = obj.animation_data.action
            
            colors_np = np.array(colors, dtype=np.float32)
            
            for i in range(3): # R, G, B
                # Find/Create Curve
                fc = action.fcurves.find(data_path=data_path, index=i)
                if not fc: fc = action.fcurves.new(data_path=data_path, index=i)
                
                # 1. Preserve keys outside range
                n_points = len(fc.keyframe_points)
                kept_keys = np.empty((0, 2), dtype=np.float32)
                
                if n_points > 0:
                    existing = np.empty(n_points * 2, dtype=np.float32)
                    fc.keyframe_points.foreach_get('co', existing)
                    existing = existing.reshape((-1, 2))
                    
                    # Logic: Keep keys strictly BEFORE start or AFTER end
                    mask = (existing[:, 0] < start_f) | (existing[:, 0] > end_f)
                    kept_keys = existing[mask]
                
                # 2. Prepare new keys
                new_keys = np.empty((len(frames_arr), 2), dtype=np.float32)
                new_keys[:, 0] = frames_arr
                new_keys[:, 1] = colors_np[:, i]
                
                # 3. Merge
                if len(kept_keys) > 0:
                    final_keys = np.vstack((kept_keys, new_keys))
                    # Sort by frame number
                    final_keys = final_keys[final_keys[:, 0].argsort()]
                else:
                    final_keys = new_keys
                
                # 4. Write
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(final_keys))
                fc.keyframe_points.foreach_set('co', final_keys.flatten())
                fc.update()