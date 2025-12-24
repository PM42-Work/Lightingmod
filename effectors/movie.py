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

    def invoke(self, context, event):
        sc = context.scene
        img = sc.image_texture
        if not img:
            self.report({'ERROR'}, "Pick an Image Texture")
            return {'CANCELLED'}
        start,end,step = sc.effector_start, sc.effector_end, sc.movie_step
        self.frames = list(range(start,end+1,step))
        if not self.frames:
            self.report({'ERROR'}, "No frames to sample")
            return {'CANCELLED'}
        objs = context.selected_objects if sc.effector_selected_only else bpy.data.objects
        self.drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH']
        if not self.drones:
            self.report({'WARNING'}, "No md_sphere meshes")
            return {'CANCELLED'}
        img.reload(); self.img=img
        self.w,self.h = img.size
        self.uv_map    = sc.movie_uv_map
        self.target_prop = f'Layer_{int(sc.effector_target_layer)+1}'
        self.idx = 0
        wm = context.window_manager
        wm.progress_begin(0, len(self.frames))
        fps      = getattr(sc.render,"fps",24)
        fps_base = getattr(sc.render,"fps_base",1.0)
        interval = 1.0/(fps/fps_base)
        self._timer = wm.event_timer_add(interval, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        wm = context.window_manager
        if event.type in {'ESC','RIGHTMOUSE'}:
            wm.event_timer_remove(self._timer)
            wm.progress_end()
            return {'CANCELLED'}
        if event.type=='TIMER':
            if self.idx < len(self.frames):
                frame = self.frames[self.idx]
                context.scene.frame_set(frame)
                # Force update
                # for area in context.screen.areas: area.tag_redraw()
                
                self.img.reload()
                px = list(self.img.pixels)
                w,h = self.w,self.h
                uv_map = self.uv_map
                prop   = self.target_prop
                import mathutils
                
                for o in self.drones:
                    if uv_map not in o.data.uv_layers: continue
                    loops = o.data.uv_layers[uv_map].data
                    avg = mathutils.Vector((0.0,0.0))
                    for lp in loops: avg += lp.uv
                    avg /= len(loops) if loops else 1.0
                    u = min(1.0,max(0.0,avg.x)); v = min(1.0,max(0.0,avg.y))
                    xf, yf = u*(w-1), v*(h-1)
                    x0,y0=int(xf),int(yf)
                    x1,y1=min(w-1,x0+1),min(h-1,y0+1)
                    dx,dy=xf-x0,yf-y0
                    
                    def pix(x,y):
                        i=(y*w+x)*4
                        return None if i<0 or i+2>=len(px) else (px[i],px[i+1],px[i+2])
                    
                    p00,p10 = pix(x0,y0), pix(x1,y0)
                    p01,p11 = pix(x0,y1), pix(x1,y1)
                    if None in (p00,p10,p01,p11): continue
                    
                    def lerp(a,b,t): return a*(1-t)+b*t
                    r0=lerp(p00[0],p10[0],dx); g0=lerp(p00[1],p10[1],dx); b0=lerp(p00[2],p10[2],dx)
                    r1=lerp(p01[0],p11[0],dx); g1=lerp(p01[1],p11[1],dx); b1=lerp(p01[2],p11[2],dx)
                    r=lerp(r0,r1,dy); g=lerp(g0,g1,dy); b=lerp(b0,b1,dy)
                    
                    o[prop]=[r,g,b]
                    o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
                
                self.idx += 1
                wm.progress_update(self.idx)
                return {'RUNNING_MODAL'}
            
            wm.event_timer_remove(self._timer)
            wm.progress_end()
            return {'FINISHED'}
        return {'PASS_THROUGH'}
