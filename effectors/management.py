import bpy
import colorsys
from ... import utils

class LIGHTINGMOD_OT_apply_effectors(bpy.types.Operator):
    bl_idname="lightingmod.apply_effectors"; bl_label="Apply Effectors"
    def execute(self, context):
        t=context.scene.effector_type
        if   t=='GRADIENT': return bpy.ops.lightingmod.draw_gradient('INVOKE_DEFAULT')
        elif t=='SPARKLE':  return bpy.ops.lightingmod.sparkle()
        elif t=='DOMAIN':   return bpy.ops.lightingmod.domain()
        elif t=='MOVIE':    return bpy.ops.lightingmod.movie_sampler('INVOKE_DEFAULT')
        elif t=='OFFSET':   return bpy.ops.lightingmod.offset_keyframes()
        return{'CANCELLED'}

class LIGHTINGMOD_OT_effector_color_add(bpy.types.Operator):
    bl_idname="lightingmod.effector_color_add"; bl_label=""
    def execute(self, context):
        sc=context.scene
        sc.effector_colors.add()
        sc.effector_colors_index=len(sc.effector_colors)-1
        return{'FINISHED'}

class LIGHTINGMOD_OT_effector_color_remove(bpy.types.Operator):
    bl_idname="lightingmod.effector_color_remove"; bl_label=""
    def execute(self, context):
        sc=context.scene; i=sc.effector_colors_index
        sc.effector_colors.remove(i)
        sc.effector_colors_index=max(0,i-1)
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
