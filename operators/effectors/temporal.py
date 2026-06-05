import bpy
from .generator import apply_sparkle_effect

class ADVLIGHTING_OT_temporal_sparkle(bpy.types.Operator):
    bl_idname = "advlighting.temporal_sparkle"
    bl_label = "Temporal Sparkle"
    
    def execute(self, context):
        res = apply_sparkle_effect(context, is_temporal=True)
        if res == 'CANCELLED_NO_STAGES':
            self.report({'WARNING'}, "Need at least 2 stages")
            return {'CANCELLED'}
        return {'FINISHED'}

class ADVLIGHTING_OT_stage_add(bpy.types.Operator):
    bl_idname = "advlighting.stage_add"
    bl_label = "Add Stage"
    def execute(self, context):
        sc = context.scene
        st = sc.adv_temporal_stages.add()
        st.name = f"Stage {len(sc.adv_temporal_stages)}"
        return {'FINISHED'}

class ADVLIGHTING_OT_stage_remove(bpy.types.Operator):
    bl_idname = "advlighting.stage_remove"
    bl_label = "Remove Stage"
    def execute(self, context):
        sc = context.scene
        if sc.adv_temporal_stages:
            sc.adv_temporal_stages.remove(sc.adv_temporal_stages_index)
            sc.adv_temporal_stages_index = max(0, sc.adv_temporal_stages_index - 1)
        return {'FINISHED'}