import bpy
import re
from bpy.props import IntProperty
from .. import utils

class ADVLIGHTING_OT_layer_add(bpy.types.Operator):
    bl_idname = "advlighting.layer_add"
    bl_label  = "Add Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    inherit_base: bpy.props.BoolProperty(name="Inherit existing md_layer_1 keyframes", default=True)
    show_prompt: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    def invoke(self, context, event):
        sc = context.scene
        # If adding the very first layer, check if md_layer_1 already has animation data
        if len(sc.adv_layers) == 0:
            has_anim = False
            for o in bpy.data.objects:
                if o.get("md_sphere") and o.type == 'MESH' and o.animation_data and o.animation_data.action:
                    for fc in o.animation_data.action.fcurves:
                        if fc.data_path == '["md_layer_1"]':
                            has_anim = True; break
                if has_anim: break
            
            if has_anim:
                self.show_prompt = True
                return context.window_manager.invoke_props_dialog(self)
                
        self.show_prompt = False
        return self.execute(context)

    def draw(self, context):
        if self.show_prompt:
            self.layout.label(text="Animation data found on md_layer_1.", icon='INFO')
            self.layout.prop(self, "inherit_base")

    def execute(self, context):
        sc = context.scene
        idx = len(sc.adv_layers)
        
        layer = sc.adv_layers.add()
        layer.data_source = f"Layer_{idx+1}" 
        
        sc.adv_layers_index = idx
        if idx == 0: sc.adv_layers[0].name = "Base Layer"
        
        mat = bpy.data.materials.get("drone colour") or bpy.data.materials.new("drone colour")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes; links = mat.node_tree.links
        for n in [n for n in nodes if n.type=='BSDF_PRINCIPLED']: nodes.remove(n)
        out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
        out.location = (600,0)
        em = nodes.get("Emission") or nodes.new("ShaderNodeEmission")
        em.location = (400,0)
        
        if not em.outputs[0].links: links.new(em.outputs[0], out.inputs[0])
            
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
        
        # --- INHERIT BASE LOGIC ---
        if idx == 0 and self.show_prompt and self.inherit_base:
            for obj in bpy.data.objects:
                if obj.get("md_sphere") and obj.type == 'MESH' and obj.animation_data and obj.animation_data.action:
                    act = obj.animation_data.action
                    base_fcs = [fc for fc in act.fcurves if fc.data_path == '["md_layer_1"]']
                    for b_fc in base_fcs:
                        new_fc = act.fcurves.find('["Layer_1"]', index=b_fc.array_index)
                        if not new_fc: new_fc = act.fcurves.new('["Layer_1"]', index=b_fc.array_index)
                        new_fc.keyframe_points.clear()
                        new_fc.keyframe_points.add(len(b_fc.keyframe_points))
                        
                        coords = [0.0] * (len(b_fc.keyframe_points) * 2)
                        b_fc.keyframe_points.foreach_get('co', coords)
                        new_fc.keyframe_points.foreach_set('co', coords)
                        new_fc.update()

        # Node math generation
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
            tgt = var.targets[0]; tgt.id_type='SCENE'; tgt.id=sc; tgt.data_path=f'adv_layers[{idx}].opacity'
            drv.expression = var.name
            
            sep_hsv = nodes.new("ShaderNodeSeparateHSV")
            sep_hsv.name = f"Layer_HSV_{idx+1}"; sep_hsv.location = (0, -300*idx + 150)
            links.new(attr.outputs[0], sep_hsv.inputs[0])
            
            math_mul = nodes.new("ShaderNodeMath")
            math_mul.name = f"Layer_Math_{idx+1}"; math_mul.operation = 'MULTIPLY'; math_mul.location = (0, -300*idx)
            links.new(sep_hsv.outputs[2], math_mul.inputs[0])
            links.new(val_node.outputs[0], math_mul.inputs[1])
            
            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"Layer_Mix_{idx+1}"; mix.location = (200, -300*idx)
            
            links.new(prev, mix.inputs[1])
            links.new(attr.outputs[0], mix.inputs[2])
            links.new(mix.outputs[0],  em.inputs[0])
            
            utils.update_mix_node(context, idx)
            
        utils.refresh_layer_enable(context.scene)
        return {'FINISHED'}

# --- THE F3 POPUP DUPLICATOR ---
class ADVLIGHTING_OT_copy_base_to_layer(bpy.types.Operator):
    bl_idname = "advlighting.copy_base_to_layer"
    bl_label = "Copy md_layer_1 to AdvLayer"
    bl_description = "Standalone utility to duplicate md_layer_1 fcurves into a specific layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_layer_items(self, context):
        sc = context.scene
        if not getattr(sc, "adv_layers", None) or len(sc.adv_layers) == 0: return [('0', "No Layers Exist", "")]
        return [(str(i), f"Layer {i+1}: {l.name}", "") for i, l in enumerate(sc.adv_layers)]
        
    target_layer: bpy.props.EnumProperty(name="Target Layer", items=get_layer_items)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
        
    def execute(self, context):
        sc = context.scene
        if not sc.adv_layers: return {'CANCELLED'}
        
        target_idx = int(self.target_layer)
        target_prop = f'["Layer_{target_idx+1}"]'
        
        count = 0
        for obj in bpy.data.objects:
            if obj.get("md_sphere") and obj.type == 'MESH' and obj.animation_data and obj.animation_data.action:
                act = obj.animation_data.action
                base_fcs = [fc for fc in act.fcurves if fc.data_path == '["md_layer_1"]']
                if not base_fcs: continue
                
                count += 1
                for b_fc in base_fcs:
                    new_fc = act.fcurves.find(target_prop, index=b_fc.array_index)
                    if not new_fc: new_fc = act.fcurves.new(target_prop, index=b_fc.array_index)
                    new_fc.keyframe_points.clear()
                    new_fc.keyframe_points.add(len(b_fc.keyframe_points))
                    
                    coords = [0.0] * (len(b_fc.keyframe_points) * 2)
                    b_fc.keyframe_points.foreach_get('co', coords)
                    new_fc.keyframe_points.foreach_set('co', coords)
                    new_fc.update()
                    
        self.report({'INFO'}, f"Copied base colors to Layer {target_idx+1} for {count} drones.")
        return {'FINISHED'}

class ADVLIGHTING_OT_layer_remove(bpy.types.Operator):
    bl_idname = "advlighting.layer_remove"
    bl_label  = "Remove Layer"
    def execute(self, context):
        sc = context.scene; idx = sc.adv_layers_index
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
            
        sc.adv_layers.remove(idx)
        sc.adv_layers_index = max(0, idx-1)
        return {'FINISHED'}

class ADVLIGHTING_OT_layer_move(bpy.types.Operator):
    bl_idname = "advlighting.layer_move"
    bl_label = "Move Layer"
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])

    def execute(self, context):
        sc = context.scene
        idx = sc.adv_layers_index

        target_idx = idx - 1 if self.direction == 'UP' else idx + 1
        
        # --- BASE LAYER UNLOCKED ---
        if target_idx < 0 or target_idx >= len(sc.adv_layers):
            return {'CANCELLED'}

        for i, l in enumerate(sc.adv_layers):
            if not l.data_source: l.data_source = f"Layer_{i+1}"

        sc.adv_layers.move(idx, target_idx)
        sc.adv_layers_index = target_idx
        sc.adv_needs_layer_rebuild = True
        return {'FINISHED'}

class ADVLIGHTING_OT_apply_layer_order(bpy.types.Operator):
    bl_idname = "advlighting.apply_layer_order"
    bl_label = "Apply Layer Order"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        mapping = {}
        for i, layer in enumerate(sc.adv_layers):
            target_prop = f"Layer_{i+1}"
            source_prop = layer.data_source
            mapping[target_prop] = source_prop
            layer.data_source = target_prop 
            
        for obj in bpy.data.objects:
            if not (obj.get("md_sphere") and obj.type == 'MESH'): continue
            
            snapshot = {}
            for i in range(len(sc.adv_layers)):
                p = f"Layer_{i+1}"
                snapshot[p] = list(obj.get(p, [0.0, 0.0, 0.0]))
            
            for target, source in mapping.items():
                if source in snapshot: obj[target] = snapshot[source]
                    
            if obj.animation_data and obj.animation_data.action:
                act = obj.animation_data.action
                for fc in act.fcurves:
                    if re.match(r'\["Layer_(\d+)"\]', fc.data_path): fc.data_path = "TEMP_" + fc.data_path
                        
                for target, source in mapping.items():
                    for fc in act.fcurves:
                        if fc.data_path == f'TEMP_["{source}"]': fc.data_path = f'["{target}"]'
                            
        if sc.animation_data and sc.animation_data.action:
            act = sc.animation_data.action
            for fc in act.fcurves:
                if re.match(r'adv_layers\[(\d+)\]\.opacity', fc.data_path): fc.data_path = "TEMP_" + fc.data_path
                    
            for i, layer in enumerate(sc.adv_layers):
                source_idx = int(mapping[f"Layer_{i+1}"].split("_")[1]) - 1
                for fc in act.fcurves:
                    if fc.data_path == f"TEMP_adv_layers[{source_idx}].opacity":
                        fc.data_path = f"adv_layers[{i}].opacity"

        sc.adv_needs_layer_rebuild = False
        bpy.ops.advlighting.redraw_nodes()
        self.report({'INFO'}, "Layers Ordered and Rebuilt Successfully!")
        return {'FINISHED'}

class ADVLIGHTING_OT_redraw_nodes(bpy.types.Operator):
    bl_idname = "advlighting.redraw_nodes"
    bl_label  = "Redraw Node Tree"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        mat = bpy.data.materials.get("drone colour")
        if not mat: mat = bpy.data.materials.new("drone colour")
            
        mat.use_nodes = True
        nodes = mat.node_tree.nodes; links = mat.node_tree.links
        nodes.clear()
        
        out = nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
        em = nodes.new("ShaderNodeEmission"); em.location = (400, 0)
        links.new(em.outputs[0], out.inputs[0])
        
        if not sc.adv_layers: return {'FINISHED'}

        a0 = nodes.new("ShaderNodeAttribute")
        a0.name = 'Base_Layer'; a0.attribute_name = "Layer_1"; a0.attribute_type = 'OBJECT'; a0.location = (0, 0)
        links.new(a0.outputs[0], em.inputs[0])

        for idx in range(1, len(sc.adv_layers)):
            layer = sc.adv_layers[idx]
            prop = f"Layer_{idx+1}"
            
            oldlink = em.inputs[0].links[0]
            prev_out = oldlink.from_socket
            links.remove(oldlink)
            
            attr = nodes.new("ShaderNodeAttribute")
            attr.name = prop; attr.attribute_name = prop; attr.attribute_type = 'OBJECT'; attr.location = (-400, -300 * idx)
            
            val_node = nodes.new("ShaderNodeValue")
            val_node.name = f"Layer_Opacity_{idx+1}"; val_node.location = (-400, -300 * idx - 150)
            
            drv = val_node.outputs[0].driver_add('default_value').driver
            var = drv.variables.new(); var.name = 'inf'
            tgt = var.targets[0]; tgt.id_type = 'SCENE'; tgt.id = sc; tgt.data_path = f'adv_layers[{idx}].opacity'
            drv.expression = var.name

            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"Layer_Mix_{idx+1}"; mix.location = (100, -300 * idx)
            mix.blend_type = utils.BLEND_MAP.get(layer.blend_mode, 'MIX')
            
            if layer.blend_mode == 'REPLACE' and utils.USE_MAX_CHANNEL_MATTE:
                sep_hsv = nodes.new("ShaderNodeSeparateHSV")
                sep_hsv.name = f"Layer_HSV_{idx+1}"; sep_hsv.location = (-200, -300 * idx + 150)
                links.new(attr.outputs[0], sep_hsv.inputs[0])
                
                math_mul = nodes.new("ShaderNodeMath")
                math_mul.name = f"Layer_Math_{idx+1}"; math_mul.operation = 'MULTIPLY'; math_mul.location = (-50, -300 * idx)
                
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

class ADVLIGHTING_OT_layer_toggle_solo(bpy.types.Operator):
    bl_idname = "advlighting.layer_toggle_solo"
    bl_label  = "Toggle Solo"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene; L = sc.adv_layers
        if 0 <= self.index < len(L):
            L[self.index].solo = not L[self.index].solo
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

class ADVLIGHTING_OT_layer_toggle_mute(bpy.types.Operator):
    bl_idname = "advlighting.layer_toggle_mute"
    bl_label  = "Toggle Mute"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene; L = sc.adv_layers
        if 0 <= self.index < len(L):
            L[self.index].mute = not L[self.index].mute
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

classes = (
    ADVLIGHTING_OT_layer_add,
    ADVLIGHTING_OT_copy_base_to_layer,
    ADVLIGHTING_OT_layer_remove,
    ADVLIGHTING_OT_layer_move,
    ADVLIGHTING_OT_apply_layer_order,
    ADVLIGHTING_OT_redraw_nodes,
    ADVLIGHTING_OT_layer_toggle_solo,
    ADVLIGHTING_OT_layer_toggle_mute,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)