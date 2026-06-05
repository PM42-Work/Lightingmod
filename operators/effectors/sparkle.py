import bpy
from .generator import apply_sparkle_effect

class LIGHTINGMOD_OT_sparkle_effector(bpy.types.Operator):
    bl_idname = "lightingmod.sparkle"
    bl_label  = "Sparkle"
    
    def execute(self, context):
        res = apply_sparkle_effect(context, is_temporal=False)
        if res == 'CANCELLED_NO_PROFILES':
            self.report({'WARNING'}, "Add at least one profile with colors")
            return {'CANCELLED'}
        return {'FINISHED'}