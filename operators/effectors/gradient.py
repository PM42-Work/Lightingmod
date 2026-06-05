import bpy
import mathutils
from bpy.props import FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from ... import utils
from .evaluator import EffectorEvaluator

class ADVLIGHTING_OT_create_gradient_nodegroup(bpy.types.Operator):
    bl_idname = "advlighting.create_gradient_nodegroup"
    bl_label = "Create Gradient Ramp NodeGroup"
    def execute(self, context):
        utils.ensure_gradient_nodegroup()
        return {'FINISHED'}

class ADVLIGHTING_OT_flip_color_ramp(bpy.types.Operator):
    bl_idname = "advlighting.flip_color_ramp"
    bl_label  = "Flip Gradient Colors"
    bl_description = "Inverts the color ramp (flips 0.0 to 1.0)"

    def execute(self, context):
        ng = context.scene.adv_gradient_ng
        if not ng or "Ramp" not in ng.nodes:
            self.report({'WARNING'}, "Gradient Node Group not found")
            return {'CANCELLED'}
        
        ramp = ng.nodes["Ramp"].color_ramp
        snapshot = [e for e in ramp.elements]
        for e in snapshot:
            e.position = 1.0 - e.position
            
        context.area.tag_redraw()
        self.report({'INFO'}, "Gradient Ramp Flipped")
        return {'FINISHED'}

class ADVLIGHTING_OT_draw_gradient(bpy.types.Operator):
    bl_idname = "advlighting.draw_gradient"
    bl_label  = "Draw Gradient"
    bl_description = "Click two points to define your gradient domain"

    first:  FloatVectorProperty()
    second: FloatVectorProperty()
    stage:  IntProperty(default=0)

    def invoke(self, context, event):
        sc = context.scene
        
        if sc.adv_gradient_mode == 'CURVE':
            if not sc.adv_curve_object:
                self.report({'ERROR'}, "Please assign a Curve Object in the panel first.")
                return {'CANCELLED'}
            self.first = (0.0, 0.0, 0.0)
            self.second = (0.0, 0.0, 0.0)
            self.apply_gradient(context)
            self.report({'INFO'}, "Curve Gradient applied instantly")
            return {'FINISHED'}
            
        self.depsgraph = context.evaluated_depsgraph_get()
        self.stage = 0
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Gradient: click first point")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            region = context.region
            rv3d   = context.region_data
            coord  = (event.mouse_region_x, event.mouse_region_y)

            view_vec   = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d( region, rv3d, coord)
            hit, loc, *_ = context.scene.ray_cast(self.depsgraph, ray_origin, view_vec)

            if not hit:
                plane_pt = context.scene.cursor.location
                plane_no = rv3d.view_rotation @ mathutils.Vector((0,0,-1))
                loc = mathutils.geometry.intersect_line_plane(
                    ray_origin, ray_origin+view_vec,
                    plane_pt, plane_no, False)

            if self.stage == 0:
                self.first = loc
                self.stage = 1
                self.report({'INFO'}, "Gradient: click second point")
                return {'RUNNING_MODAL'}
            else:
                self.second = loc
                self.apply_gradient(context)
                self.report({'INFO'}, "Gradient applied")
                return {'FINISHED'}

        if event.type in {'RIGHTMOUSE','ESC'}:
            self.report({'WARNING'}, "Gradient canceled")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def apply_gradient(self, context):
        sc = context.scene
        ng = bpy.data.node_groups.get("AdvLightingGradient")
        if not ng or "Ramp" not in ng.nodes:
            utils.ensure_gradient_nodegroup()
            ng = bpy.data.node_groups.get("AdvLightingGradient")
        
        ramp = ng.nodes["Ramp"].color_ramp
        layer_idx = int(sc.adv_effector_target_layer) + 1
        prop = f"Layer_{layer_idx}"
        
        evaluator = EffectorEvaluator(context, sc.adv_gradient_mode, self.first, self.second, 
                                      sc.adv_curve_object, sc.adv_curve_radius, sc.adv_curve_mode)

        objs = []
        if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
             if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
                 g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']

        for obj in objs:
            if prop not in obj.keys(): continue

            t, valid = evaluator.get_t(obj.matrix_world.to_translation())
            if not valid: continue
            
            r, g, b, a = ramp.evaluate(t)
            base = obj[prop]
            fac  = a
            newcol = [ base[i]*(1-fac) + c*fac for i,c in enumerate((r,g,b)) ]
            obj[prop] = newcol
            obj.keyframe_insert(data_path=f'["{prop}"]', frame=sc.frame_current)