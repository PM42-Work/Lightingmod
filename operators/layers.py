import bpy
import re
from bpy.props import IntProperty
from .. import utils

class LIGHTINGMOD_OT_layer_add(bpy.types.Operator):
    bl_idname = "lightingmod.layer_add"
    bl_label  = "Add Layer"
    def execute(self, context):
        sc = context.scene
        idx = len(sc.ly_layers)
        
        layer = sc.ly_layers.add()
        layer.data_source = f"Layer_{idx+1}" # Initialize the pointer
        
        sc.ly_layers_index = idx
        if idx == 0:
            sc.ly_layers[0].name = "Base Layer"
        
        mat = bpy.data.materials.get("drone colour") or bpy.data.materials.new("drone colour")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes; links = mat.node_tree.links
        for n in [n for n in nodes if n.type=='BSDF_PRINCIPLED']: nodes.remove(n)
        out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
        out.location = (600,0)
        em = nodes.get("Emission") or nodes.new("ShaderNodeEmission")
        em.location = (400,0)
        
        if not em.outputs[0].links:
            links.new(em.outputs[0], out.inputs[0])
            
        if idx == 0:
            a0 = nodes.new("ShaderNodeAttribute")
            a0.name = 'Base_Layer'; a0.attribute_name = "Layer_1"; a0.attribute_type='OBJECT'; a0.location=(0,0)
            links.new(a0.outputs[0], em.inputs[0])
            
        prop = f"Layer_{idx+1}"
        for obj in bpy.data.objects:
            if obj.get("md_sphere") and obj.type=='MESH':
                if mat.name not in {m.name for m in obj.data.materials}: obj.data.materials.append(mat)
                obj[prop] = [0.5,0.5,0.5]
                ui = obj.id_properties_ui(prop)
                ui.update(min=0, max=1, subtype='COLOR')
        
        if idx > 0:
            oldlink = em.inputs[0].links[0]
            prev = oldlink.from_socket
            links.remove(oldlink)
            
            attr = nodes.new("ShaderNodeAttribute")
            attr.name=prop; attr.attribute_name=prop; attr.attribute_type='OBJECT'; attr.location=(-200,-300*idx)
            
            val_node = nodes.new("ShaderNodeValue")
            val_node.name = f"Layer_Opacity_{idx+1}"
            val_node.location = (-200, -300*idx - 150)
            
            drv = val_node.outputs[0].driver_add('default_value').driver
            var = drv.variables.new(); var.name='inf'
            tgt = var.targets[0]; tgt.id_type='SCENE'; tgt.id=sc; tgt.data_path=f'ly_layers[{idx}].opacity'
            drv.expression = var.name
            
            sep_hsv = nodes.new("ShaderNodeSeparateHSV")
            sep_hsv.name = f"Layer_HSV_{idx+1}"
            sep_hsv.location = (0, -300*idx + 150)
            links.new(attr.outputs[0], sep_hsv.inputs[0])
            
            math_mul = nodes.new("ShaderNodeMath")
            math_mul.name = f"Layer_Math_{idx+1}"
            math_mul.operation = 'MULTIPLY'
            math_mul.location = (0, -300*idx)
            links.new(sep_hsv.outputs[2], math_mul.inputs[0])
            links.new(val_node.outputs[0], math_mul.inputs[1])
            
            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"Layer_Mix_{idx+1}"
            mix.location = (200, -300*idx)
            
            links.new(prev, mix.inputs[1])
            links.new(attr.outputs[0], mix.inputs[2])
            links.new(mix.outputs[0],  em.inputs[0])
            
            utils.update_mix_node(context, idx)
            
        utils.refresh_layer_enable(context.scene)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_remove(bpy.types.Operator):
    bl_idname = "lightingmod.layer_remove"
    bl_label  = "Remove Layer"
    def execute(self, context):
        sc = context.scene; idx = sc.ly_layers_index
        if idx == 0: return {'CANCELLED'}
        prop = f"Layer_{idx+1}"
        for obj in bpy.data.objects:
            if prop in obj.keys(): del obj[prop]
            
        mat = bpy.data.materials.get("drone colour")
        if mat:
            nodes=mat.node_tree.nodes; links=mat.node_tree.links
            mix=nodes.get(f"Layer_Mix_{idx+1}")
            if mix:
                prev_links = mix.inputs[1].links
                prev_sock  = prev_links[0].from_socket if prev_links else None
                outs       = [lk.to_socket for lk in mix.outputs[0].links]
                nodes.remove(mix)
                if prev_sock:
                    for to in outs: links.new(prev_sock,to)
                    
            for prefix in ["Layer_Opacity_", "Layer_HSV_", "Layer_Math_"]:
                nd = nodes.get(f"{prefix}{idx+1}")
                if nd: nodes.remove(nd)
            attr = nodes.get(prop)
            if attr: nodes.remove(attr)
            
        sc.ly_layers.remove(idx)
        sc.ly_layers_index = max(0, idx-1)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_move(bpy.types.Operator):
    bl_idname = "lightingmod.layer_move"
    bl_label = "Move Layer"
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])

    def execute(self, context):
        sc = context.scene
        idx = sc.ly_layers_index
        if idx == 0:
            self.report({'WARNING'}, "Cannot move the Base Layer")
            return {'CANCELLED'}

        target_idx = idx - 1 if self.direction == 'UP' else idx + 1
        if target_idx <= 0 or target_idx >= len(sc.ly_layers):
            return {'CANCELLED'}

        # Fix missing data sources if migrating an old file
        for i, l in enumerate(sc.ly_layers):
            if not l.data_source: l.data_source = f"Layer_{i+1}"

        sc.ly_layers.move(idx, target_idx)
        sc.ly_layers_index = target_idx
        sc.needs_layer_rebuild = True # Engage UI Lock
        return {'FINISHED'}

class LIGHTINGMOD_OT_apply_layer_order(bpy.types.Operator):
    bl_idname = "lightingmod.apply_layer_order"
    bl_label = "Apply Layer Order"
    bl_description = "Executes the data swap and heals the layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        
        # 1. Build the Mapping (Target -> Source)
        mapping = {}
        for i, layer in enumerate(sc.ly_layers):
            target_prop = f"Layer_{i+1}"
            source_prop = layer.data_source
            mapping[target_prop] = source_prop
            layer.data_source = target_prop # Reset pointer for future
            
        # 2. Swap Object Properties and F-Curves
        for obj in bpy.data.objects:
            if not (obj.get("md_sphere") and obj.type == 'MESH'): continue
            
            # Snapshot properties
            snapshot = {}
            for i in range(len(sc.ly_layers)):
                p = f"Layer_{i+1}"
                snapshot[p] = list(obj.get(p, [0.0, 0.0, 0.0]))
            
            # Reassign based on mapping
            for target, source in mapping.items():
                if source in snapshot:
                    obj[target] = snapshot[source]
                    
            # Swap F-Curves safely via TEMP prefix
            if obj.animation_data and obj.animation_data.action:
                act = obj.animation_data.action
                for fc in act.fcurves:
                    if re.match(r'\["Layer_(\d+)"\]', fc.data_path):
                        fc.data_path = "TEMP_" + fc.data_path
                        
                for target, source in mapping.items():
                    for fc in act.fcurves:
                        if fc.data_path == f'TEMP_["{source}"]':
                            fc.data_path = f'["{target}"]'
                            
        # 3. Swap Scene Opacity F-Curves
        if sc.animation_data and sc.animation_data.action:
            act = sc.animation_data.action
            for fc in act.fcurves:
                if re.match(r'ly_layers\[(\d+)\]\.opacity', fc.data_path):
                    fc.data_path = "TEMP_" + fc.data_path
                    
            for i, layer in enumerate(sc.ly_layers):
                source_idx = int(mapping[f"Layer_{i+1}"].split("_")[1]) - 1
                for fc in act.fcurves:
                    if fc.data_path == f"TEMP_ly_layers[{source_idx}].opacity":
                        fc.data_path = f"ly_layers[{i}].opacity"

        # 4. Release Lock & Heal
        sc.needs_layer_rebuild = False
        bpy.ops.lightingmod.redraw_nodes()
        self.report({'INFO'}, "Layers Ordered and Rebuilt Successfully!")
        return {'FINISHED'}

class LIGHTINGMOD_OT_redraw_nodes(bpy.types.Operator):
    bl_idname = "lightingmod.redraw_nodes"
    bl_label  = "Redraw Node Tree"
    bl_description = "Rebuilds the Drone material nodes from scratch based on the UI layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        mat = bpy.data.materials.get("drone colour")
        if not mat: mat = bpy.data.materials.new("drone colour")
            
        mat.use_nodes = True
        nodes = mat.node_tree.nodes; links = mat.node_tree.links
        nodes.clear()
        
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (600, 0)
        em = nodes.new("ShaderNodeEmission")
        em.location = (400, 0)
        links.new(em.outputs[0], out.inputs[0])
        
        if not sc.ly_layers: return {'FINISHED'}

        a0 = nodes.new("ShaderNodeAttribute")
        a0.name = 'Base_Layer'; a0.attribute_name = "Layer_1"; a0.attribute_type = 'OBJECT'; a0.location = (0, 0)
        links.new(a0.outputs[0], em.inputs[0])

        for idx in range(1, len(sc.ly_layers)):
            layer = sc.ly_layers[idx]
            prop = f"Layer_{idx+1}"
            
            oldlink = em.inputs[0].links[0]
            prev_out = oldlink.from_socket
            links.remove(oldlink)
            
            attr = nodes.new("ShaderNodeAttribute")
            attr.name = prop; attr.attribute_name = prop; attr.attribute_type = 'OBJECT'; attr.location = (-400, -300 * idx)
            
            val_node = nodes.new("ShaderNodeValue")
            val_node.name = f"Layer_Opacity_{idx+1}"
            val_node.location = (-400, -300 * idx - 150)
            
            drv = val_node.outputs[0].driver_add('default_value').driver
            var = drv.variables.new(); var.name = 'inf'
            tgt = var.targets[0]; tgt.id_type = 'SCENE'; tgt.id = sc; tgt.data_path = f'ly_layers[{idx}].opacity'
            drv.expression = var.name

            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"Layer_Mix_{idx+1}"
            mix.location = (100, -300 * idx)
            mix.blend_type = utils.BLEND_MAP.get(layer.blend_mode, 'MIX')
            
            if layer.blend_mode == 'REPLACE' and utils.USE_MAX_CHANNEL_MATTE:
                sep_hsv = nodes.new("ShaderNodeSeparateHSV")
                sep_hsv.name = f"Layer_HSV_{idx+1}"
                sep_hsv.location = (-200, -300 * idx + 150)
                links.new(attr.outputs[0], sep_hsv.inputs[0])
                
                math_mul = nodes.new("ShaderNodeMath")
                math_mul.name = f"Layer_Math_{idx+1}"
                math_mul.operation = 'MULTIPLY'
                math_mul.location = (-50, -300 * idx)
                
                links.new(sep_hsv.outputs[2], math_mul.inputs[0])
                links.new(val_node.outputs[0], math_mul.inputs[1])
                links.new(math_mul.outputs[0], mix.inputs[0])
            else:
                links.new(val_node.outputs[0], mix.inputs[0])

            links.new(prev_out, mix.inputs[1])
            links.new(attr.outputs[0], mix.inputs[2])
            links.new(mix.outputs[0], em.inputs[0])

        utils.refresh_layer_enable(sc)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_toggle_solo(bpy.types.Operator):
    bl_idname = "lightingmod.layer_toggle_solo"
    bl_label  = "Toggle Solo"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene; L = sc.ly_layers
        if 0 <= self.index < len(L):
            L[self.index].solo = not L[self.index].solo
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_toggle_mute(bpy.types.Operator):
    bl_idname = "lightingmod.layer_toggle_mute"
    bl_label  = "Toggle Mute"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene; L = sc.ly_layers
        if 0 <= self.index < len(L):
            L[self.index].mute = not L[self.index].mute
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

classes = (
    LIGHTINGMOD_OT_layer_add,
    LIGHTINGMOD_OT_layer_remove,
    LIGHTINGMOD_OT_layer_move,
    LIGHTINGMOD_OT_apply_layer_order,
    LIGHTINGMOD_OT_redraw_nodes,
    LIGHTINGMOD_OT_layer_toggle_solo,
    LIGHTINGMOD_OT_layer_toggle_mute,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)