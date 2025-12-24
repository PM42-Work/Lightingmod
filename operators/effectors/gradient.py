import bpy
import mathutils
from bpy.props import FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from ... import utils

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
        
        ramp_node = ng.nodes["Ramp"]
        ramp = ramp_node.color_ramp

        layer_idx = int(sc.effector_target_layer) + 1
        prop = f"Layer_{layer_idx}"
        mode = sc.gradient_mode

        p0 = mathutils.Vector(self.first)
        p1 = mathutils.Vector(self.second)
        vec = p1 - p0
        length = vec.length if vec.length > 0 else 1.0

        if mode == 'RADIAL_2D':
            rgn  = context.region
            rv3d = context.region_data
            co0 = view3d_utils.location_3d_to_region_2d(rgn, rv3d, p0)
            co1 = view3d_utils.location_3d_to_region_2d(rgn, rv3d, p1)
            radius_2d = (co1 - co0).length if (co0 and co1) else length

        objs = context.selected_objects if sc.effector_selected_only else bpy.data.objects
        for obj in objs:
            if not (obj.get("md_sphere") and obj.type=='MESH'): continue
            if prop not in obj.keys(): continue

            pos = obj.matrix_world.to_translation()
            if mode == 'LINEAR':
                t = (pos - p0).dot(vec) / (length*length)
            elif mode == 'RADIAL_2D':
                co  = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, pos)
                t = ((co - co0).length / radius_2d) if (co and co0 and radius_2d>0) else 0.0
            else:
                t = (pos - p0).length / length

            t = max(0.0, min(1.0, t))
            r, g, b, a = ramp.evaluate(t)
            
            base = obj[prop]
            fac  = a
            newcol = [ base[i]*(1-fac) + c*fac for i,c in enumerate((r,g,b)) ]
            obj[prop] = newcol
            obj.keyframe_insert(data_path=f'["{prop}"]', frame=sc.frame_current)
