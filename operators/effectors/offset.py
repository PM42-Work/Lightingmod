import bpy
import mathutils
from bpy.props import FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from ... import utils

class LIGHTINGMOD_OT_draw_offset_line(bpy.types.Operator):
    bl_idname = "lightingmod.draw_offset_line"
    bl_label  = "Draw Offset Line"
    bl_description = "Click two points to define the stagger axis"
    first:  FloatVectorProperty()
    second: FloatVectorProperty()
    stage:  IntProperty(default=0)
    
    def invoke(self, context, event):
        self.depsgraph = context.evaluated_depsgraph_get()
        self.stage=0
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'},"Offset: click first point")
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            region = context.region; rv3d=context.region_data
            coord=(event.mouse_region_x,event.mouse_region_y)
            vec   = view3d_utils.region_2d_to_vector_3d(region,rv3d,coord)
            orig  = view3d_utils.region_2d_to_origin_3d(region,rv3d,coord)
            hit,loc,*_ = context.scene.ray_cast(self.depsgraph,orig,vec)
            if not hit:
                plane_pt=context.scene.cursor.location
                plane_no=rv3d.view_rotation@mathutils.Vector((0,0,-1))
                loc=mathutils.geometry.intersect_line_plane(orig,orig+vec,plane_pt,plane_no,False)
            if self.stage==0:
                self.first=loc; self.stage=1
                self.report({'INFO'},"Offset: click second point")
                return {'RUNNING_MODAL'}
            else:
                self.second=loc
                sc=context.scene
                sc.offset_line_start=self.first
                sc.offset_line_end  =self.second
                self.report({'INFO'},"Offset line set")
                return {'FINISHED'}
        if event.type in {'RIGHTMOUSE','ESC'}:
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

class LIGHTINGMOD_OT_offset_keyframes(bpy.types.Operator):
    bl_idname = "lightingmod.offset_keyframes"
    bl_label  = "Offset Keyframes"
    def execute(self, context):
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        sc   = context.scene
        p0   = mathutils.Vector(sc.offset_line_start)
        p1   = mathutils.Vector(sc.offset_line_end)
        mode = sc.gradient_mode
        dur  = sc.effector_duration

        if mode == 'RADIAL_2D':
            region = context.region
            rv3d   = context.region_data
            co0_2d = location_3d_to_region_2d(region, rv3d, p0)
            co1_2d = location_3d_to_region_2d(region, rv3d, p1) if co0_2d else None
            radius_2d = (co1_2d - co0_2d).length if (co0_2d and co1_2d) else dur

        for obj in context.selected_objects:
            if not (obj.get("md_sphere") and obj.type=='MESH'): continue
            world_pos = obj.matrix_world.to_translation()
            if mode == 'LINEAR':
                vec = p1 - p0
                denom = vec.dot(vec) or 1.0
                t = (world_pos - p0).dot(vec) / denom
            elif mode == 'RADIAL_2D':
                region = context.region
                rv3d   = context.region_data
                co_obj_2d = location_3d_to_region_2d(region, rv3d, world_pos)
                if co0_2d and co_obj_2d and radius_2d > 0.0:
                    t = (co_obj_2d - co0_2d).length / radius_2d
                else:
                    t = 0.0
            else:
                dist = (world_pos - p0).length
                maxd = (p1 - p0).length or 1.0
                t = dist / maxd

            t = max(0.0, min(1.0, t))
            offs = t * dur

            ad = obj.animation_data
            if not ad or not ad.action: continue

            for fcu in ad.action.fcurves:
                if not fcu.data_path.startswith('["Layer_'): continue
                for kp in fcu.keyframe_points:
                    if not kp.select_control_point: continue
                    kp.co.x           += offs
                    kp.handle_left.x  += offs
                    kp.handle_right.x += offs
        return {'FINISHED'}
