import bpy
import numpy as np
import os

# Try to import OpenCV. 
# It will be found if the 'dependencies' folder is correctly set up.
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

from bpy.props import StringProperty
from ... import utils

class LIGHTINGMOD_OT_generate_uv(bpy.types.Operator):
    bl_idname = "lightingmod.generate_uv"
    bl_label  = "Add & Activate UV Map"
    def execute(self, context):
        name = context.scene.new_uv_map_name.strip()
        if not name:
            self.report({'ERROR'}, "Enter a UV Map Name")
            return {'CANCELLED'}
        for obj in context.selected_objects:
            if obj.type!='MESH': continue
            uvl = obj.data.uv_layers
            if name not in uvl: uvl.new(name=name)
            uvl.active = uvl[name]
        self.report({'INFO'}, f"UV map '{name}' added & activated")
        return {'FINISHED'}

class LIGHTINGMOD_OT_movie_sampler(bpy.types.Operator):
    bl_idname = "lightingmod.movie_sampler"
    bl_label  = "Sample Image (Direct File)"
    _timer = None
    
    # Data Storage
    lookup_table = []   # [(obj, pixel_x, pixel_y), ...]
    drone_data = {}     # {obj_name: [[r,g,b], ...]}
    cap = None
    
    def invoke(self, context, event):
        sc = context.scene
        img = sc.image_texture
        
        if not img:
            self.report({'ERROR'}, "Pick an Image Texture")
            return {'CANCELLED'}

        # Get File Path
        filepath = bpy.path.abspath(img.filepath)
        if not os.path.exists(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}
            
        # Check for OpenCV
        if not HAS_OPENCV:
            self.report({'ERROR'}, "OpenCV not found. Please check addon installation.")
            return {'CANCELLED'}

        start, end, step = sc.effector_start, sc.effector_end, sc.movie_step
        if step < 1: step = 1
        
        self.frames = list(range(start, end + 1, step))
        if not self.frames:
            self.report({'ERROR'}, "No frames to sample")
            return {'CANCELLED'}
            
        # 1. Identify Drones
        objs = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects if sc.effector_selected_only else bpy.data.objects

        self.drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH']
        if not self.drones:
            self.report({'WARNING'}, "No valid drones found")
            return {'CANCELLED'}

        # 2. Setup Video Capture (External)
        self.cap = cv2.VideoCapture(filepath)
        if not self.cap.isOpened():
            self.report({'ERROR'}, "Could not open video file.")
            return {'CANCELLED'}
            
        # Get Video Specs
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.uv_map_name = sc.movie_uv_map
        self.target_prop = f'Layer_{int(sc.effector_target_layer)+1}'
        self.target_data_path = f'["{self.target_prop}"]'
        
        # 3. Pre-Calc Pixel Indices (Lookup Table)
        self.lookup_table = []
        self.drone_data = {}
        
        w_int = self.w
        h_int = self.h
        
        for o in self.drones:
            if self.uv_map_name not in o.data.uv_layers: continue
            loops = o.data.uv_layers[self.uv_map_name].data
            if not loops: continue
            
            self.drone_data[o.name] = []
            
            # UV Average
            avg_u, avg_v = 0.0, 0.0
            for lp in loops:
                avg_u += lp.uv[0]
                avg_v += lp.uv[1]
            count = len(loops)
            u = max(0.0, min(1.0, avg_u / count))
            v = max(0.0, min(1.0, avg_v / count))
            
            # OpenCV Origin is Top-Left, Blender UV is Bottom-Left
            # We must flip V
            px_x = int(u * (w_int - 1))
            px_y = int((1.0 - v) * (h_int - 1))
            
            self.lookup_table.append((o, px_x, px_y))

        if not self.lookup_table:
             self.cap.release()
             self.report({'WARNING'}, f"No drones have valid UVs")
             return {'CANCELLED'}

        # 4. Start Modal
        self.idx = 0
        wm = context.window_manager
        wm.progress_begin(0, len(self.frames))
        context.window.cursor_modal_set('WAIT')
        
        # Faster timer (0.01s) - We don't need to wait for Blender UI updates anymore
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        
        print(f"--- Processing Video External: {len(self.frames)} frames ---")
        return {'RUNNING_MODAL'}

    def save_keyframes(self, context):
        """Merges new data with existing F-Curves (Range Overwrite)"""
        print("Merging keyframes...")
        
        frames_arr = np.array(self.frames, dtype=np.float32)
        start_f = frames_arr[0]
        end_f   = frames_arr[-1]
        
        for obj_name, color_data in self.drone_data.items():
            obj = bpy.data.objects.get(obj_name)
            if not obj: continue
            
            if not obj.animation_data: obj.animation_data_create()
            if not obj.animation_data.action:
                obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}Action")
            action = obj.animation_data.action
            
            if len(color_data) != len(frames_arr): continue
                
            colors_np = np.array(color_data, dtype=np.float32) # Shape: (N, 3)
            
            for i in range(3):
                fc = action.fcurves.find(data_path=self.target_data_path, index=i)
                if not fc: fc = action.fcurves.new(data_path=self.target_data_path, index=i)
                
                n_points = len(fc.keyframe_points)
                kept_keys = np.empty((0, 2), dtype=np.float32)
                
                if n_points > 0:
                    existing = np.empty(n_points * 2, dtype=np.float32)
                    fc.keyframe_points.foreach_get('co', existing)
                    existing = existing.reshape((-1, 2))
                    mask = (existing[:, 0] < start_f) | (existing[:, 0] > end_f)
                    kept_keys = existing[mask]
                
                new_keys = np.empty((len(frames_arr), 2), dtype=np.float32)
                new_keys[:, 0] = frames_arr
                new_keys[:, 1] = colors_np[:, i]
                
                if len(kept_keys) > 0:
                    final_keys = np.vstack((kept_keys, new_keys))
                    final_keys = final_keys[final_keys[:, 0].argsort()]
                else:
                    final_keys = new_keys
                
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(final_keys))
                fc.keyframe_points.foreach_set('co', final_keys.flatten())
                fc.update()

    def cleanup(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        if self.cap:
            self.cap.release()
        context.window_manager.progress_end()
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cleanup(context)
            self.report({'WARNING'}, "Baking Cancelled")
            return {'CANCELLED'}
            
        if event.type == 'TIMER':
            # Process a chunk of 5 frames per tick
            frames_per_tick = 5 
            
            for _ in range(frames_per_tick):
                if self.idx >= len(self.frames):
                    self.save_keyframes(context)
                    self.cleanup(context)
                    self.report({'INFO'}, "Movie Bake Complete")
                    return {'FINISHED'}

                target_frame = self.frames[self.idx]
                
                # Seek in video file (Frame 1 in Blender = Frame 0 in Video)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, target_frame - 1))
                ret, frame_img = self.cap.read()
                
                if not ret:
                    # Video ended or error, pad with black
                    for obj, x, y in self.lookup_table:
                        self.drone_data[obj.name].append((0.0, 0.0, 0.0))
                else:
                    # OpenCV is BGR. Access pixels directly.
                    for obj, x, y in self.lookup_table:
                        if 0 <= x < self.w and 0 <= y < self.h:
                            b, g, r = frame_img[y, x]
                            self.drone_data[obj.name].append((r/255.0, g/255.0, b/255.0))
                        else:
                            self.drone_data[obj.name].append((0.0, 0.0, 0.0))

                self.idx += 1
            
            context.window_manager.progress_update(self.idx)
            return {'RUNNING_MODAL'}
            
        return {'PASS_THROUGH'}