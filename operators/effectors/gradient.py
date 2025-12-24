import bpy
import mathutils
from bpy.props import FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from ... import utils
from .evaluator import EffectorEvaluator  # <--- NEW IMPORT

class LIGHTINGMOD_OT_create_gradient_nodegroup(bpy.types.Operator):
    bl_idname = "lightingmod.create_gradient_nodegroup"
    bl_label = "Create Gradient Ramp NodeGroup"
    def execute(self, context):
        utils.ensure_gradient_nodegroup()
        return {'FINISHED'}

class LIGHTINGMOD_OT_draw_gradient(bpy.types.Operator):
    bl_idname = "lightingmod.draw_gradient"
    bl_label  = "Draw Gradient"
    bl_description = "Click two points to define your gradient domain"

    first:  FloatVectorProperty()
    second: FloatVectorProperty()
    stage:  IntProperty(default=0)

    def invoke(self, context, event):
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
        ng = bpy.data.node_groups.get("LightingModGradient")
        if not ng or "Ramp" not in ng.nodes:
            utils.ensure_gradient_nodegroup()
            ng = bpy.data.node_groups.get("LightingModGradient")
        
        ramp = ng.nodes["Ramp"].color_ramp
        layer_idx = int(sc.effector_target_layer) + 1
        prop = f"Layer_{layer_idx}"
        
        # --- NEW LOGIC USING EVALUATOR ---
        evaluator = EffectorEvaluator(context, sc.gradient_mode, self.first, self.second)

        objs = context.selected_objects if sc.effector_selected_only else bpy.data.objects
        for obj in objs:
            if not (obj.get("md_sphere") and obj.type=='MESH'): continue
            if prop not in obj.keys(): continue

            # Get t from the common evaluator
            t = evaluator.get_t(obj.matrix_world.to_translation())
            r, g, b, a = ramp.evaluate(t)
            
            base = obj[prop]
            fac  = a
            newcol = [ base[i]*(1-fac) + c*fac for i,c in enumerate((r,g,b)) ]
            obj[prop] = newcol
            obj.keyframe_insert(data_path=f'["{prop}"]', frame=sc.frame_current)