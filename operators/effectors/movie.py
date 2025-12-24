import bpy
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
    bl_label  = "Sample Image"
    _timer = None
    
    # State storage
    temp_scene = None
    orig_scene = None
    cached_drone_data = []

    def invoke(self, context, event):
        sc = context.scene
        img = sc.image_texture
        if not img:
            self.report({'ERROR'}, "Pick an Image Texture")
            return {'CANCELLED'}
        
        # --- FIX 1: FORCE AUTO REFRESH ---
        # Without this, the movie ignores the timeline position
        img.use_auto_refresh = True
        
        start, end, step = sc.effector_start, sc.effector_end, sc.movie_step
        self.frames = list(range(start, end + 1, step))
        if not self.frames:
            self.report({'ERROR'}, "No frames to sample")
            return {'CANCELLED'}
            
        # 1. Identify Drones (Selection or Group)
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

        # 2. Setup Image
        # Note: We do NOT reload() here repeatedly; auto_refresh handles it.
        self.img = img
        self.w, self.h = img.size
        self.uv_map_name = sc.movie_uv_map
        self.target_prop = f'Layer_{int(sc.effector_target_layer)+1}'
        
        # 3. PRE-CALCULATE UVs (Optimization 1)
        self.cached_drone_data = []
        for o in self.drones:
            if self.uv_map_name not in o.data.uv_layers: continue
            loops = o.data.uv_layers[self.uv_map_name].data
            if not loops: continue
            
            # Fast average
            avg_u, avg_v = 0.0, 0.0
            for lp in loops:
                avg_u += lp.uv[0]
                avg_v += lp.uv[1]
            count = len(loops)
            u = max(0.0, min(1.0, avg_u / count))
            v = max(0.0, min(1.0, avg_v / count))
            self.cached_drone_data.append((o, u, v))

        if not self.cached_drone_data:
             self.report({'WARNING'}, f"No drones have UV map '{self.uv_map_name}'")
             return {'CANCELLED'}

        # 4. GHOST SCENE SETUP (Optimization 2)
        # We create an empty scene to scrub the timeline. 
        # This avoids updating the heavy geometry/rigs of the main scene.
        self.orig_scene = context.scene
        self.temp_scene = bpy.data.scenes.new("LightingMod_Temp_Bake")
        
        # Sync render settings so frame rate matches (crucial for video time calculation)
        self.temp_scene.render.fps = self.orig_scene.render.fps
        self.temp_scene.render.fps_base = self.orig_scene.render.fps_base
        self.temp_scene.frame_start = start
        self.temp_scene.frame_end = end
        
        # Switch context to temp scene
        context.window.scene = self.temp_scene

        # 5. Start Timer
        self.idx = 0
        wm = context.window_manager
        wm.progress_begin(0, len(self.frames))
        
        # Fast timer interval
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}

    def cleanup(self, context):
        """Restore original state"""
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        
        context.window_manager.progress_end()
        
        # Restore Scene
        if self.orig_scene:
            context.window.scene = self.orig_scene
            
        # Delete Temp Scene
        if self.temp_scene:
            bpy.data.scenes.remove(self.temp_scene)
            self.temp_scene = None

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cleanup(context)
            self.report({'WARNING'}, "Baking Cancelled")
            return {'CANCELLED'}
            
        if event.type == 'TIMER':
            if self.idx < len(self.frames):
                frame = self.frames[self.idx]
                
                # Update the LIGHTWEIGHT temp scene (very fast)
                self.temp_scene.frame_set(frame)
                
                # --- FIX 2: FORCE DEPENDENCY UPDATE ---
                # This ensures the Image Texture node processes the new frame time.
                # Without this, 'pixels' will return the cached data from the previous frame.
                context.view_layer.update()
                
                # (Optional) 'reload' is usually not needed if auto_refresh is on, 
                # and can actually cause playback stutters. We skip it unless necessary.
                # try: self.img.reload() 
                # except: pass
                    
                try:
                    px = self.img.pixels # This read triggers the buffer fetch
                except Exception:
                    # Fallback for some video formats that might lock up
                    self.img.reload()
                    px = self.img.pixels

                w, h = self.w, self.h
                prop = self.target_prop
                
                # Fast Loop using Pre-calculated UVs
                for o, u, v in self.cached_drone_data:
                    # Map 0-1 UV to Image Coordinates
                    xf, yf = u * (w - 1), v * (h - 1)
                    x0, y0 = int(xf), int(yf)
                    x1, y1 = min(w - 1, x0 + 1), min(h - 1, y0 + 1)
                    dx, dy = xf - x0, yf - y0
                    
                    # Bilinear Sample Helper
                    def get_rgb(x, y):
                        i = (y * w + x) * 4
                        # Safety check for bounds
                        if i < 0 or i + 2 >= len(px): return (0,0,0)
                        return (px[i], px[i+1], px[i+2])

                    try:
                        c00 = get_rgb(x0, y0); c10 = get_rgb(x1, y0)
                        c01 = get_rgb(x0, y1); c11 = get_rgb(x1, y1)
                        
                        # Interpolate X
                        r0 = c00[0]*(1-dx) + c10[0]*dx; g0 = c00[1]*(1-dx) + c10[1]*dx; b0 = c00[2]*(1-dx) + c10[2]*dx
                        r1 = c01[0]*(1-dx) + c11[0]*dx; g1 = c01[1]*(1-dx) + c11[1]*dx; b1 = c01[2]*(1-dx) + c11[2]*dx
                        
                        # Interpolate Y
                        r = r0*(1-dy) + r1*dy
                        g = g0*(1-dy) + g1*dy
                        b = b0*(1-dy) + b1*dy
                        
                        # Apply to object (Object data persists across scenes)
                        o[prop] = [r, g, b]
                        o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
                        
                    except IndexError: continue

                self.idx += 1
                context.window_manager.progress_update(self.idx)
                return {'RUNNING_MODAL'}
            
            # Done
            self.cleanup(context)
            self.report({'INFO'}, "Movie Bake Complete")
            return {'FINISHED'}
            
        return {'PASS_THROUGH'}