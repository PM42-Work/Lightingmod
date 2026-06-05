import bpy
import os
import json
from .. import utils

# Define your custom property names
METADATA_SPHERE = "md_sphere"
METADATA_EMPTY = "md_empty"

class ADVLIGHTING_OT_swap_batch_colors(bpy.types.Operator):
    bl_idname = "advlighting.swap_batch_colors"
    bl_label  = ""
    def execute(self, context):
        sc = context.scene
        tmp = sc.adv_batch_primary_color[:]
        sc.adv_batch_primary_color = sc.adv_batch_secondary_color
        sc.adv_batch_secondary_color = tmp
        return {'FINISHED'}

class ADVLIGHTING_OT_batch_color_keyframe(bpy.types.Operator):
    bl_idname = "advlighting.batch_color_keyframe"
    bl_label  = "Color & Keyframe"
    def execute(self, context):
        sc = context.scene; idx = int(sc.adv_batch_target_layer); prop = f"Layer_{idx+1}"
        frame = sc.frame_current; prev = {}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                prev[o.name] = o[prop][:]
        rgb = list(sc.adv_batch_primary_color)[:3]
        for nm, old in prev.items():
            o = bpy.data.objects[nm]; o[prop] = rgb; o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
        utils.last_batch_history = {'action': 'color_keyframe', 'prop': prop, 'values': prev, 'frame': frame}
        return {'FINISHED'}

class ADVLIGHTING_OT_batch_color(bpy.types.Operator):
    bl_idname = "advlighting.batch_color"
    bl_label  = "Color Only"
    def execute(self, context):
        sc = context.scene; idx = int(sc.adv_batch_target_layer); prop = f"Layer_{idx+1}"; prev = {}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                prev[o.name] = o[prop][:]
        rgb = list(sc.adv_batch_primary_color)[:3]
        for nm in prev: bpy.data.objects[nm][prop] = rgb
        utils.last_batch_history = {'action': 'color', 'prop': prop, 'values': prev}
        return {'FINISHED'}

class ADVLIGHTING_OT_keyframe_current(bpy.types.Operator):
    bl_idname = "advlighting.keyframe_current"
    bl_label  = "Keyframe Current"
    def execute(self, context):
        sc = context.scene; idx = int(sc.adv_batch_target_layer); prop = f"Layer_{idx+1}"; frame = sc.frame_current
        utils.last_batch_history = {'action': 'keyframe', 'prop': prop, 'frame': frame}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
        return {'FINISHED'}

class ADVLIGHTING_OT_undo_last_edit(bpy.types.Operator):
    bl_idname = "advlighting.undo_last_edit"
    bl_label  = "Undo Last Edit"
    def execute(self, context):
        hist = utils.last_batch_history
        if not hist: return {'CANCELLED'}
        prop = hist['prop']
        if hist['action'] in ('color', 'color_keyframe'):
            for nm, old in hist['values'].items():
                o = bpy.data.objects.get(nm)
                if o: o[prop] = old
        if hist['action'] in ('color_keyframe', 'keyframe'):
            frame = hist['frame']
            for o in context.selected_objects:
                if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                    o.keyframe_delete(data_path=f'["{prop}"]', frame=frame)
        utils.last_batch_history = {}
        return {'FINISHED'}

classes = (
    ADVLIGHTING_OT_swap_batch_colors,
    ADVLIGHTING_OT_batch_color_keyframe,
    ADVLIGHTING_OT_batch_color,
    ADVLIGHTING_OT_keyframe_current,
    ADVLIGHTING_OT_undo_last_edit,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)