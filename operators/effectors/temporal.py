import bpy
from .generator import apply_sparkle_effect

class LIGHTINGMOD_OT_temporal_sparkle(bpy.types.Operator):
    bl_idname = "lightingmod.temporal_sparkle"
    bl_label = "Temporal Sparkle"
    
    def execute(self, context):
        res = apply_sparkle_effect(context, is_temporal=True)
        if res == 'CANCELLED_NO_STAGES':
            self.report({'WARNING'}, "Need at least 2 stages")
            return {'CANCELLED'}
        return {'FINISHED'}

class LIGHTINGMOD_OT_stage_add(bpy.types.Operator):
    bl_idname = "lightingmod.stage_add"
    bl_label = "Add Stage"
    def execute(self, context):
        sc = context.scene
        st = sc.temporal_stages.add()
        st.name = f"Stage {len(sc.temporal_stages)}"
        return {'FINISHED'}

class LIGHTINGMOD_OT_stage_remove(bpy.types.Operator):
    bl_idname = "lightingmod.stage_remove"
    bl_label = "Remove Stage"
    def execute(self, context):
        sc = context.scene
        if sc.temporal_stages:
            sc.temporal_stages.remove(sc.temporal_stages_index)
            sc.temporal_stages_index = max(0, sc.temporal_stages_index - 1)
        return {'FINISHED'}