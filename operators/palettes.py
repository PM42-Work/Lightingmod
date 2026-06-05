import bpy
import json
import os
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty
from .. import utils

# --- Default Presets ---
DEFAULT_GRADIENTS = [
    ("Cyberpunk",     [(0.0, "#00FFFF"), (0.5, "#FF00FF"), (1.0, "#1A0033")]),
    ("Inferno",       [(0.0, "#000000"), (0.3, "#FF0000"), (0.7, "#FF8800"), (1.0, "#FFFFFF")]),
    ("Aurora",        [(0.0, "#001A0B"), (0.4, "#00FF66"), (0.75, "#00FFFF"), (1.0, "#4400FF")]),
    ("Golden Hour",   [(0.0, "#FF1A00"), (0.5, "#FF0077"), (1.0, "#220044")]),
    ("Deep Ocean",    [(0.0, "#000022"), (0.5, "#0044FF"), (1.0, "#00FFFF")]),
    ("Rainbow",       [(0.0, "#FF0000"), (0.16, "#FFFF00"), (0.33, "#00FF00"), (0.5, "#00FFFF"), (0.66, "#0000FF"), (0.83, "#FF00FF"), (1.0, "#FF0000")]),
    ("Metallic Gold", [(0.0, "#553300"), (0.25, "#FFB700"), (0.5, "#FFF2BB"), (0.75, "#FFB700"), (1.0, "#553300")]),
    ("Silver / Chrome",[(0.0, "#222222"), (0.25, "#AAAAAA"), (0.5, "#FFFFFF"), (0.75, "#AAAAAA"), (1.0, "#222222")]),
    ("Copper",        [(0.0, "#331100"), (0.25, "#B87333"), (0.5, "#FFCCAA"), (0.75, "#B87333"), (1.0, "#331100")]),
    ("Rose Gold",     [(0.0, "#5A2A2A"), (0.25, "#B76E79"), (0.5, "#FFE5E5"), (0.75, "#B76E79"), (1.0, "#5A2A2A")])
]

class ADVLIGHTING_OT_load_presets(bpy.types.Operator):
    bl_idname = "advlighting.load_presets"
    bl_label = "Load Default Presets"
    def execute(self, context):
        sc = context.scene
        for name, stops in DEFAULT_GRADIENTS:
            grad = sc.adv_gradient_palettes.add()
            grad.name = name
            for pos, hex_c in stops:
                st = grad.stops.add()
                st.pos = pos
                st.color = utils.hex_to_rgb(hex_c)
        sc.adv_gradient_palettes_index = 0
        return {'FINISHED'}

# --- Colors ---
class ADVLIGHTING_OT_save_color(bpy.types.Operator):
    bl_idname = "advlighting.save_color"
    bl_label = "Save Color"
    def execute(self, context):
        sc = context.scene
        item = sc.adv_color_palettes.add()
        item.name = utils.rgb_to_hex(sc.adv_batch_primary_color[:3])
        item.color = sc.adv_batch_primary_color[:3]
        sc.adv_color_palettes_index = len(sc.adv_color_palettes) - 1
        return {'FINISHED'}

class ADVLIGHTING_OT_remove_color(bpy.types.Operator):
    bl_idname = "advlighting.remove_color"
    bl_label = "Remove Color"
    def execute(self, context):
        sc = context.scene
        if sc.adv_color_palettes:
            sc.adv_color_palettes.remove(sc.adv_color_palettes_index)
            sc.adv_color_palettes_index = max(0, sc.adv_color_palettes_index - 1)
        return {'FINISHED'}

class ADVLIGHTING_OT_apply_color(bpy.types.Operator):
    bl_idname = "advlighting.apply_color"
    bl_label = "Apply Color"
    def execute(self, context):
        sc = context.scene
        if sc.adv_color_palettes:
            sc.adv_batch_primary_color[:3] = sc.adv_color_palettes[sc.adv_color_palettes_index].color
        return {'FINISHED'}

# --- Gradients ---
class ADVLIGHTING_OT_save_gradient(bpy.types.Operator):
    bl_idname = "advlighting.save_gradient"
    bl_label = "Save Gradient"
    
    def execute(self, context):
        sc = context.scene
        ng = utils.ensure_gradient_nodegroup()
        ramp = ng.nodes["Ramp"].color_ramp
        
        item = sc.adv_gradient_palettes.add()
        item.name = "Custom Gradient"
        for el in ramp.elements:
            st = item.stops.add()
            st.pos = el.position
            st.color = list(el.color)[:3]
            
        sc.adv_gradient_palettes_index = len(sc.adv_gradient_palettes) - 1
        return {'FINISHED'}

class ADVLIGHTING_OT_remove_gradient(bpy.types.Operator):
    bl_idname = "advlighting.remove_gradient"
    bl_label = "Remove Gradient"
    def execute(self, context):
        sc = context.scene
        if sc.adv_gradient_palettes:
            sc.adv_gradient_palettes.remove(sc.adv_gradient_palettes_index)
            sc.adv_gradient_palettes_index = max(0, sc.adv_gradient_palettes_index - 1)
        return {'FINISHED'}

class ADVLIGHTING_OT_apply_gradient(bpy.types.Operator):
    bl_idname = "advlighting.apply_gradient"
    bl_label = "Apply to Effector"
    def execute(self, context):
        sc = context.scene
        if not sc.adv_gradient_palettes: return {'CANCELLED'}
        
        ng_preview = utils.ensure_gradient_preview_nodegroup()
        ng_active = utils.ensure_gradient_nodegroup()
        
        prev_ramp = ng_preview.nodes["Ramp"].color_ramp
        act_ramp = ng_active.nodes["Ramp"].color_ramp
        
        for i in range(len(act_ramp.elements)-1, 0, -1):
            act_ramp.elements.remove(act_ramp.elements[i])
            
        act_ramp.elements[0].position = prev_ramp.elements[0].position
        act_ramp.elements[0].color = prev_ramp.elements[0].color
        for i in range(1, len(prev_ramp.elements)):
            el = act_ramp.elements.new(prev_ramp.elements[i].position)
            el.color = prev_ramp.elements[i].color
            
        self.report({'INFO'}, "Gradient Applied!")
        return {'FINISHED'}

# --- JSON Import / Export ---
class ADVLIGHTING_OT_import_palettes(bpy.types.Operator, ImportHelper):
    bl_idname = "advlighting.import_palettes"
    bl_label = "Import JSON"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'}, maxlen=255)
    
    def execute(self, context):
        sc = context.scene
        with open(self.filepath, 'r') as f: data = json.load(f)
            
        if "colors" in data:
            for c in data["colors"]:
                item = sc.adv_color_palettes.add()
                item.name = c.get("name", "Imported")
                val = c["value"]
                if isinstance(val, str): item.color = utils.hex_to_rgb(val)
                elif isinstance(val, list): item.color = [min(255, max(0, v))/255.0 for v in val[:3]]
                
        if "gradients" in data:
            for g in data["gradients"]:
                item = sc.adv_gradient_palettes.add()
                item.name = g.get("name", "Imported")
                for s in g.get("stops", []):
                    st = item.stops.add()
                    st.pos = float(s["pos"])
                    val = s["color"]
                    if isinstance(val, str): st.color = utils.hex_to_rgb(val)
                    elif isinstance(val, list): st.color = [min(255, max(0, v))/255.0 for v in val[:3]]

        self.report({'INFO'}, "Palettes Imported")
        return {'FINISHED'}

class ADVLIGHTING_OT_export_palettes(bpy.types.Operator, ExportHelper):
    bl_idname = "advlighting.export_palettes"
    bl_label = "Export JSON"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        sc = context.scene
        data = {"colors": [], "gradients": []}
        
        for c in sc.adv_color_palettes:
            data["colors"].append({"name": c.name, "value": utils.rgb_to_hex(c.color)})
            
        for g in sc.adv_gradient_palettes:
            stops = []
            for s in g.stops: stops.append({"pos": round(s.pos, 3), "color": utils.rgb_to_hex(s.color)})
            data["gradients"].append({"name": g.name, "stops": stops})
            
        with open(self.filepath, 'w') as f: json.dump(data, f, indent=2)
        self.report({'INFO'}, "Palettes Exported")
        return {'FINISHED'}

classes = (
    ADVLIGHTING_OT_load_presets,
    ADVLIGHTING_OT_save_color, ADVLIGHTING_OT_remove_color, ADVLIGHTING_OT_apply_color,
    ADVLIGHTING_OT_save_gradient, ADVLIGHTING_OT_remove_gradient, ADVLIGHTING_OT_apply_gradient,
    ADVLIGHTING_OT_import_palettes, ADVLIGHTING_OT_export_palettes
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)