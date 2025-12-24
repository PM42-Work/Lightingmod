import bpy
import numpy as np
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
    bl_label  = "Sample Image (Bulk)"
    _timer = None
    
    # Data Storage
    lookup_table = []   # [(obj, pixel_index), ...]
    drone_data = {}     # {obj_name: [[r,g,b], [r,g,b], ...]}
    
    def invoke(self, context, event):
        sc = context.scene
        img = sc.image_texture
        
        if not img:
            self.report({'ERROR'}, "Pick an Image Texture")
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

        # 2. Image & Props
        self.img = img
        self.w, self.h = img.size
        if self.w == 0 or self.h == 0:
            self.report({'ERROR'}, "Image has 0 size.")
            return {'CANCELLED'}
            
        self.uv_map_name = sc.movie_uv_map
        self.target_prop = f'Layer_{int(sc.effector_target_layer)+1}'
        self.target_data_path = f'["{self.target_prop}"]' # e.g. ["Layer_1"]
        
        # 3. Pre-Calc Pixel Indices (Lookup Table)
        self.lookup_table = []
        self.drone_data = {}
        
        w_int = int(self.w)
        h_int = int(self.h)
        
        for o in self.drones:
            if self.uv_map_name not in o.data.uv_layers: continue
            loops = o.data.uv_layers[self.uv_map_name].data
            if not loops: continue
            
            # Init storage for this drone
            self.drone_data[o.name] = []
            
            # UV Average
            avg_u, avg_v = 0.0, 0.0
            for lp in loops:
                avg_u += lp.uv[0]
                avg_v += lp.uv[1]
            count = len(loops)
            u = max(0.0, min(1.0, avg_u / count))
            v = max(0.0, min(1.0, avg_v / count))
            
            px_x = int(u * (w_int - 1))
            px_y = int(v * (h_int - 1))
            
            # Index = (y * w + x) * 4
            base_idx = (px_y * w_int + px_x) * 4
            self.lookup_table.append((o, base_idx))

        if not self.lookup_table:
             self.report({'WARNING'}, f"No drones have valid UVs")
             return {'CANCELLED'}

        # 4. Start Modal
        self.idx = 0
        wm = context.window_manager
        wm.progress_begin(0, len(self.frames))
        context.window.cursor_modal_set('WAIT')
        
        # Fast Timer
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        
        print(f"--- Sampling Movie: {len(self.frames)} frames ---")
        return {'RUNNING_MODAL'}

    def save_keyframes(self, context):
        """Bulk write all stored data to F-Curves using NumPy"""
        print("Writing keyframes to F-Curves...")
        
        frames_arr = np.array(self.frames, dtype=np.float32)
        count = len(frames_arr)
        
        # We need an array of [frame, val, frame, val...]
        # We can pre-allocate the 'frame' part since it's the same for everyone
        # But we must interleave it per channel.
        
        for obj_name, color_data in self.drone_data.items():
            obj = bpy.data.objects.get(obj_name)
            if not obj: continue
            
            # Ensure Action
            if not obj.animation_data:
                obj.animation_data_create()
            if not obj.animation_data.action:
                obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}Action")
            
            action = obj.animation_data.action
            
            # Convert color list to numpy (frames x 3)
            # This is a matrix of [[r,g,b], [r,g,b], ...]
            # If color_data is incomplete (cancelled early), trim frames
            if len(color_data) != count:
                print(f"Skipping {obj_name}: Data mismatch")
                continue
                
            colors_np = np.array(color_data, dtype=np.float32) # Shape: (N, 3)
            
            # Process R, G, B channels
            for i in range(3):
                # 1. Get or Create F-Curve
                # We try to find existing one to overwrite, or make new
                fc = action.fcurves.find(data_path=self.target_data_path, index=i)
                if fc:
                    # Clear existing points to avoid conflicts
                    fc.keyframe_points.clear()
                else:
                    fc = action.fcurves.new(data_path=self.target_data_path, index=i)
                
                # 2. Add empty points
                fc.keyframe_points.add(count)
                
                # 3. Interleave [Frame, Value, Frame, Value...]
                # Create empty array of size N*2
                flat_data = np.empty(count * 2, dtype=np.float32)
                
                # Fill even indices with frames: 0, 2, 4...
                flat_data[0::2] = frames_arr
                # Fill odd indices with color values: 1, 3, 5...
                flat_data[1::2] = colors_np[:, i]
                
                # 4. Fast Set
                fc.keyframe_points.foreach_set('co', flat_data)
                
                # 5. Update Curve
                fc.update()

    def cleanup(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        context.window_manager.progress_end()
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cleanup(context)
            self.report({'WARNING'}, "Baking Cancelled")
            return {'CANCELLED'}
            
        if event.type == 'TIMER':
            if self.idx < len(self.frames):
                frame = self.frames[self.idx]
                
                context.scene.frame_set(frame)
                context.view_layer.update()
                
                try:
                    # Fast Pixel Read
                    raw_pixels = np.empty(self.w * self.h * 4, dtype=np.float32)
                    self.img.pixels.foreach_get(raw_pixels)
                except Exception:
                    self.idx += 1
                    return {'RUNNING_MODAL'}

                # Fast Collection (No Writing to Blender API yet)
                for obj, base_idx in self.lookup_table:
                    if base_idx + 2 < len(raw_pixels):
                        r = raw_pixels[base_idx]
                        g = raw_pixels[base_idx+1]
                        b = raw_pixels[base_idx+2]
                        # Append to storage
                        self.drone_data[obj.name].append((r, g, b))
                    else:
                        # Fallback for out of bounds
                        self.drone_data[obj.name].append((0.0, 0.0, 0.0))

                self.idx += 1
                
                # Update UI
                if self.idx % 5 == 0:
                    context.window_manager.progress_update(self.idx)
                    print(f"Sampling Frame {self.idx}/{len(self.frames)}")
                
                return {'RUNNING_MODAL'}
            
            # --- FINISHED LOOP ---
            # Now we write everything at once
            self.save_keyframes(context)
            
            self.cleanup(context)
            self.report({'INFO'}, "Movie Bake Complete")
            return {'FINISHED'}
            
        return {'PASS_THROUGH'}