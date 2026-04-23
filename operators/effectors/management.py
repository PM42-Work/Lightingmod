import bpy
import colorsys
from bpy_extras import view3d_utils
from ... import utils

class LIGHTINGMOD_OT_apply_effectors(bpy.types.Operator):
    bl_idname="lightingmod.apply_effectors"; bl_label="Apply Effectors"
    def execute(self, context):
        t=context.scene.effector_type
        if   t=='GRADIENT': return bpy.ops.lightingmod.draw_gradient('INVOKE_DEFAULT')
        elif t=='SPARKLE':  return bpy.ops.lightingmod.sparkle()
        elif t=='TEMPORAL_SPARKLE': return bpy.ops.lightingmod.temporal_sparkle()
        elif t=='NOISE':    return bpy.ops.lightingmod.noise_effector() # <--- NEW!
        elif t=='DOMAIN':   return bpy.ops.lightingmod.domain()
        elif t=='MOVIE':    return bpy.ops.lightingmod.movie_sampler('INVOKE_DEFAULT')
        elif t=='OFFSET':   return bpy.ops.lightingmod.offset_keyframes()
        return{'CANCELLED'}

# --- NEW: Profile Add/Remove ---
class LIGHTINGMOD_OT_spark_profile_add(bpy.types.Operator):
    bl_idname="lightingmod.spark_profile_add"
    bl_label="Add Profile"
    def execute(self, context):
        sc = context.scene
        p = sc.spark_profiles.add()
        p.name = f"Profile {len(sc.spark_profiles)}"
        sc.spark_profiles_index = len(sc.spark_profiles) - 1
        return {'FINISHED'}

class LIGHTINGMOD_OT_spark_profile_remove(bpy.types.Operator):
    bl_idname="lightingmod.spark_profile_remove"
    bl_label="Remove Profile"
    def execute(self, context):
        sc = context.scene
        idx = sc.spark_profiles_index
        if 0 <= idx < len(sc.spark_profiles):
            sc.spark_profiles.remove(idx)
            sc.spark_profiles_index = max(0, idx - 1)
        return {'FINISHED'}

class LIGHTINGMOD_OT_effector_color_add(bpy.types.Operator):
    bl_idname="lightingmod.effector_color_add"; bl_label=""
    target: bpy.props.EnumProperty(
        items=[('SPARKLE','Sparkle',''), ('TEMPORAL_STAGE','Stage',''), ('SPARK_PROFILE','Profile','')], 
        default='SPARKLE'
    )
    
    def execute(self, context):
        sc=context.scene
        if self.target == 'SPARKLE':
            sc.effector_colors.add()
            sc.effector_colors_index=len(sc.effector_colors)-1
        elif self.target == 'TEMPORAL_STAGE':
            if sc.temporal_stages:
                stage = sc.temporal_stages[sc.temporal_stages_index]
                stage.colors.add()
                stage.colors_index = len(stage.colors)-1
        elif self.target == 'SPARK_PROFILE':
            if sc.spark_profiles:
                # Force index 0 if in simple mode
                idx = sc.spark_profiles_index if sc.use_advanced_spark_profiles else 0
                prof = sc.spark_profiles[idx]
                prof.colors.add()
                prof.colors_index = len(prof.colors)-1
        return{'FINISHED'}

class LIGHTINGMOD_OT_effector_color_remove(bpy.types.Operator):
    bl_idname="lightingmod.effector_color_remove"; bl_label=""
    target: bpy.props.EnumProperty(
        items=[('SPARKLE','Sparkle',''), ('TEMPORAL_STAGE','Stage',''), ('SPARK_PROFILE','Profile','')], 
        default='SPARKLE'
    )

    def execute(self, context):
        sc=context.scene
        if self.target == 'SPARKLE':
            i=sc.effector_colors_index
            if 0 <= i < len(sc.effector_colors):
                sc.effector_colors.remove(i)
                sc.effector_colors_index=max(0,i-1)
        elif self.target == 'TEMPORAL_STAGE':
             if sc.temporal_stages:
                stage = sc.temporal_stages[sc.temporal_stages_index]
                if 0 <= stage.colors_index < len(stage.colors):
                    stage.colors.remove(stage.colors_index)
                    stage.colors_index = max(0, stage.colors_index - 1)
        elif self.target == 'SPARK_PROFILE':
            if sc.spark_profiles:
                # Force index 0 if in simple mode
                idx = sc.spark_profiles_index if sc.use_advanced_spark_profiles else 0
                prof = sc.spark_profiles[idx]
                if 0 <= prof.colors_index < len(prof.colors):
                    prof.colors.remove(prof.colors_index)
                    prof.colors_index = max(0, prof.colors_index - 1)
        return{'FINISHED'}

class LIGHTINGMOD_OT_effector_monochrome(bpy.types.Operator):
    bl_idname="lightingmod.effector_monochrome"; bl_label="Monochrome"
    def execute(self, context):
        cols=context.scene.effector_colors
        if not cols: return{'CANCELLED'}
        r,g,b,a=cols[0].color; h,_,_=colorsys.rgb_to_hsv(r,g,b)
        for it in cols:
            rr,gg,bb,aa=it.color
            _,s,v=colorsys.rgb_to_hsv(rr,gg,bb)
            cr,cg,cb=colorsys.hsv_to_rgb(h,s,v)
            it.color=(cr,cg,cb,aa)
        return{'FINISHED'}

class LIGHTINGMOD_OT_set_start_frame(bpy.types.Operator):
    bl_idname="lightingmod.set_start_frame"; bl_label=""
    def execute(self, context):
        context.scene.effector_start=context.scene.frame_current
        return{'FINISHED'}

class LIGHTINGMOD_OT_set_end_frame(bpy.types.Operator):
    bl_idname="lightingmod.set_end_frame"; bl_label=""
    def execute(self, context):
        context.scene.effector_end=context.scene.frame_current
        return{'FINISHED'}
    
class LIGHTINGMOD_OT_create_noise_nodegroup(bpy.types.Operator):
    bl_idname = "lightingmod.create_noise_nodegroup"
    bl_label = "Create Noise Ramp"
    def execute(self, context):
        from ... import utils
        utils.ensure_noise_nodegroup()
        return {'FINISHED'}

class LIGHTINGMOD_OT_draw_noise_flow(bpy.types.Operator):
    bl_idname = "lightingmod.draw_noise_flow"
    bl_label = "Draw Flow Direction"
    bl_options = {'REGISTER', 'UNDO'}

    start_point = None

    def modal(self, context, event):
        context.area.tag_redraw()

        # Cancel the tool if they press Escape or Right-Click
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.report({'INFO'}, "Cancelled Flow Direction Draw")
            return {'CANCELLED'}

        # Execute on Left Click
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = context.region
            rv3d = context.region_data
            coord = event.mouse_region_x, event.mouse_region_y

            # 1. Calculate the 3D ray from the user's screen into the scene
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

            # 2. Try to hit an object (like a drone)
            hit, location, normal, index, obj, matrix = context.scene.ray_cast(
                context.view_layer.depsgraph, ray_origin, view_vector
            )

            # 3. Fallback: If they clicked empty air, calculate the hit on the Z=0 ground plane
            if not hit:
                if view_vector.z != 0:
                    t = -ray_origin.z / view_vector.z
                    location = ray_origin + view_vector * t
                else:
                    location = ray_origin

            # 4. Handle the Clicks
            if not self.start_point:
                self.start_point = location
                self.report({'INFO'}, "Start Point Set. Click to set Flow Direction.")
            else:
                end_point = location
                direction = end_point - self.start_point
                
                # Normalize the vector (force its length to 1.0) so it acts strictly as a ratio
                if direction.length > 0:
                    direction.normalize()
                    context.scene.noise_direction = direction
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