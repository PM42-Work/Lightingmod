import bpy
import mathutils
from bpy.props import FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from ... import utils
from .evaluator import EffectorEvaluator

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
        sc = context.scene
        
        # Init Evaluator
        evaluator = EffectorEvaluator(context, sc.gradient_mode, sc.offset_line_start, sc.offset_line_end,
                                      sc.curve_object, sc.curve_radius, sc.curve_mode)

        # Collect Objects (Selection OR Group)
        objs = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects

        moved = False
        for obj in objs:
            if not (obj.get("md_sphere") and obj.type=='MESH'): continue
            
            # Get t from common evaluator
            t, valid = evaluator.get_t(obj.matrix_world.to_translation())
            if not valid: continue
            
            offs = t * sc.effector_duration

            ad = obj.animation_data
            if not ad or not ad.action: continue

            for fcu in ad.action.fcurves:
                if not fcu.data_path.startswith('["Layer_'): continue
                for kp in fcu.keyframe_points:
                    if not kp.select_control_point: continue
                    kp.co.x           += offs
                    kp.handle_left.x  += offs
                    kp.handle_right.x += offs
                    moved = True
        
        if not moved:
            self.report({'WARNING'}, "No keyframes moved (ensure you have keyframes selected in graph editor)")
            return {'CANCELLED'}
            
        return {'FINISHED'}