import bpy
import colorsys
from bpy_extras import view3d_utils
from ... import utils

class ADVLIGHTING_OT_apply_effectors(bpy.types.Operator):
    bl_idname="advlighting.apply_effectors"; bl_label="Apply Effectors"
    def execute(self, context):
        t=context.scene.adv_effector_type
        if   t=='GRADIENT': return bpy.ops.advlighting.draw_gradient('INVOKE_DEFAULT')
        elif t=='SPARKLE':  return bpy.ops.advlighting.sparkle()
        elif t=='TEMPORAL_SPARKLE': return bpy.ops.advlighting.temporal_sparkle()
        elif t=='NOISE':    return bpy.ops.advlighting.noise_effector()
        elif t=='DOMAIN':   return bpy.ops.advlighting.domain()
        elif t=='MOVIE':    return bpy.ops.advlighting.movie_sampler('INVOKE_DEFAULT')
        elif t=='OFFSET':   return bpy.ops.advlighting.offset_keyframes()
        return{'CANCELLED'}

class ADVLIGHTING_OT_sample_drone_colors(bpy.types.Operator):
    bl_idname = "advlighting.sample_drone_colors"
    bl_label = "Sample Colors from Current Frame"
    
    target: bpy.props.EnumProperty(
        items=[('SPARKLE', 'Sparkle', ''), ('TEMPORAL', 'Temporal Stage', '')]
    )
    
    def execute(self, context):
        sc = context.scene
        # Target the specific layered property
        prop = f"Layer_{int(sc.adv_effector_target_layer)+1}"
        drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
        
        if not drones:
            self.report({'WARNING'}, "No drones selected")
            return {'CANCELLED'}
            
        target_col = None
        if self.target == 'SPARKLE':
            target_col = sc.adv_sampled_colors
        elif self.target == 'TEMPORAL':
            if sc.adv_temporal_stages:
                target_col = sc.adv_temporal_stages[sc.adv_temporal_stages_index].sampled_colors
                
        if target_col is None: return {'CANCELLED'}
            
        target_col.clear()
        for d in drones:
            if prop in d.keys():
                item = target_col.add()
                item.name = d.name
                item.color = d[prop][:3]
                
        self.report({'INFO'}, f"Sampled {len(target_col)} drones")
        return {'FINISHED'}

class ADVLIGHTING_OT_spark_profile_add(bpy.types.Operator):
    bl_idname="advlighting.spark_profile_add"; bl_label="Add Profile"
    def execute(self, context):
        sc = context.scene; p = sc.adv_spark_profiles.add()
        p.name = f"Profile {len(sc.adv_spark_profiles)}"
        sc.adv_spark_profiles_index = len(sc.adv_spark_profiles) - 1
        return {'FINISHED'}

class ADVLIGHTING_OT_spark_profile_remove(bpy.types.Operator):
    bl_idname="advlighting.spark_profile_remove"; bl_label="Remove Profile"
    def execute(self, context):
        sc = context.scene; idx = sc.adv_spark_profiles_index
        if 0 <= idx < len(sc.adv_spark_profiles):
            sc.adv_spark_profiles.remove(idx)
            sc.adv_spark_profiles_index = max(0, idx - 1)
        return {'FINISHED'}

class ADVLIGHTING_OT_effector_color_add(bpy.types.Operator):
    bl_idname="advlighting.effector_color_add"; bl_label=""
    target: bpy.props.EnumProperty(
        items=[('SPARKLE','Sparkle',''), ('TEMPORAL_STAGE','Stage',''), ('SPARK_PROFILE','Profile','')], 
        default='SPARKLE'
    )
    def execute(self, context):
        sc=context.scene
        if self.target == 'SPARKLE':
            sc.adv_effector_colors.add()
            sc.adv_effector_colors_index=len(sc.adv_effector_colors)-1
        elif self.target == 'TEMPORAL_STAGE':
            if sc.adv_temporal_stages:
                stage = sc.adv_temporal_stages[sc.adv_temporal_stages_index]
                stage.colors.add()
                stage.colors_index = len(stage.colors)-1
        elif self.target == 'SPARK_PROFILE':
            if sc.adv_spark_profiles:
                idx = sc.adv_spark_profiles_index if sc.adv_use_advanced_spark_profiles else 0
                prof = sc.adv_spark_profiles[idx]
                prof.colors.add()
                prof.colors_index = len(prof.colors)-1
        return{'FINISHED'}

class ADVLIGHTING_OT_effector_color_remove(bpy.types.Operator):
    bl_idname="advlighting.effector_color_remove"; bl_label=""
    target: bpy.props.EnumProperty(
        items=[('SPARKLE','Sparkle',''), ('TEMPORAL_STAGE','Stage',''), ('SPARK_PROFILE','Profile','')], 
        default='SPARKLE'
    )
    def execute(self, context):
        sc=context.scene
        if self.target == 'SPARKLE':
            i=sc.adv_effector_colors_index
            if 0 <= i < len(sc.adv_effector_colors):
                sc.adv_effector_colors.remove(i)
                sc.adv_effector_colors_index=max(0,i-1)
        elif self.target == 'TEMPORAL_STAGE':
             if sc.adv_temporal_stages:
                stage = sc.adv_temporal_stages[sc.adv_temporal_stages_index]
                if 0 <= stage.colors_index < len(stage.colors):
                    stage.colors.remove(stage.colors_index)
                    stage.colors_index = max(0, stage.colors_index - 1)
        elif self.target == 'SPARK_PROFILE':
            if sc.adv_spark_profiles:
                idx = sc.adv_spark_profiles_index if sc.adv_use_advanced_spark_profiles else 0
                prof = sc.adv_spark_profiles[idx]
                if 0 <= prof.colors_index < len(prof.colors):
                    prof.colors.remove(prof.colors_index)
                    prof.colors_index = max(0, prof.colors_index - 1)
        return{'FINISHED'}

class ADVLIGHTING_OT_effector_monochrome(bpy.types.Operator):
    bl_idname="advlighting.effector_monochrome"; bl_label="Monochrome"
    def execute(self, context):
        cols=context.scene.adv_effector_colors
        if not cols: return{'CANCELLED'}
        r,g,b,a=cols[0].color; h,_,_=colorsys.rgb_to_hsv(r,g,b)
        for it in cols:
            rr,gg,bb,aa=it.color
            _,s,v=colorsys.rgb_to_hsv(rr,gg,bb)
            cr,cg,cb=colorsys.hsv_to_rgb(h,s,v)
            it.color=(cr,cg,cb,aa)
        return{'FINISHED'}

class ADVLIGHTING_OT_set_effector_start(bpy.types.Operator):
    bl_idname="advlighting.set_effector_start"; bl_label=""
    def execute(self, context):
        context.scene.adv_effector_start=context.scene.frame_current
        return{'FINISHED'}

class ADVLIGHTING_OT_set_effector_end(bpy.types.Operator):
    bl_idname="advlighting.set_effector_end"; bl_label=""
    def execute(self, context):
        context.scene.adv_effector_end=context.scene.frame_current
        return{'FINISHED'}
    
class ADVLIGHTING_OT_create_noise_nodegroup(bpy.types.Operator):
    bl_idname = "advlighting.create_noise_nodegroup"
    bl_label = "Create Noise Ramp"
    def execute(self, context):
        from ... import utils
        utils.ensure_noise_nodegroup()
        return {'FINISHED'}

class ADVLIGHTING_OT_draw_noise_flow(bpy.types.Operator):
    bl_idname = "advlighting.draw_noise_flow"
    bl_label = "Draw Flow Direction"
    bl_options = {'REGISTER', 'UNDO'}
    start_point = None
    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.report({'INFO'}, "Cancelled Flow Direction Draw")
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region, rv3d, coord = context.region, context.region_data, (event.mouse_region_x, event.mouse_region_y)
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
            hit, location, *_ = context.scene.ray_cast(context.view_layer.depsgraph, ray_origin, view_vector)

            if not hit:
                if view_vector.z != 0:
                    t = -ray_origin.z / view_vector.z
                    location = ray_origin + view_vector * t
                else:
                    location = ray_origin

            if not self.start_point:
                self.start_point = location
                self.report({'INFO'}, "Start Point Set. Click to set Flow Direction.")
            else:
                end_point = location
                direction = end_point - self.start_point
                if direction.length > 0:
                    direction.normalize()
                    context.scene.adv_noise_direction = direction
                    self.report({'INFO'}, f"Direction Ratio Set: X:{direction.x:.2f} Y:{direction.y:.2f} Z:{direction.z:.2f}")
                return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Must run in the 3D Viewport")
            return {'CANCELLED'}
        self.start_point = None
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Click first point for Flow Direction")
        return {'RUNNING_MODAL'}