import bpy
from bpy.props import IntProperty
from .. import utils

class LIGHTINGMOD_OT_layer_add(bpy.types.Operator):
    bl_idname = "lightingmod.layer_add"
    bl_label  = "Add Layer"
    def execute(self, context):
        sc = context.scene
        idx = len(sc.ly_layers)
        sc.ly_layers.add()
        sc.ly_layers_index = idx
        if idx == 0:
            sc.ly_layers[0].name = "Base Layer"
        
        mat = bpy.data.materials.get("drone colour") or bpy.data.materials.new("drone colour")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes; links = mat.node_tree.links
        for n in [n for n in nodes if n.type=='BSDF_PRINCIPLED']:
            nodes.remove(n)
        out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
        out.location = (600,0)
        em = nodes.get("Emission") or nodes.new("ShaderNodeEmission")
        em.location = (400,0)
        if not em.outputs['Emission'].links:
            links.new(em.outputs['Emission'], out.inputs['Surface'])
            
        if idx == 0:
            a0 = nodes.new("ShaderNodeAttribute")
            a0.name = 'Base_Layer'; a0.attribute_name = "Layer_1"; a0.attribute_type='OBJECT'; a0.location=(0,0)
            links.new(a0.outputs['Color'], em.inputs['Color'])
            
        prop = f"Layer_{idx+1}"
        for obj in bpy.data.objects:
            if obj.get("md_sphere") and obj.type=='MESH':
                if mat.name not in {m.name for m in obj.data.materials}:
                    obj.data.materials.append(mat)
                obj[prop] = [0.5,0.5,0.5]
                ui = obj.id_properties_ui(prop)
                ui.update(min=0, max=1, subtype='COLOR')
        
        if idx > 0:
            oldlink = em.inputs['Color'].links[0]
            prev = oldlink.from_socket
            links.remove(oldlink)
            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"Layer_Mix_{idx+1}"
            mix.location = (200,-200*idx)
            mix.blend_type = utils.BLEND_MAP[ sc.ly_layers[idx].blend_mode ]
            
            drv = mix.inputs['Fac'].driver_add('default_value').driver
            var = drv.variables.new(); var.name='inf'
            tgt = var.targets[0]; tgt.id_type='SCENE'; tgt.id=sc; tgt.data_path=f'ly_layers[{idx}].opacity'
            drv.expression = var.name
            
            attr = nodes.new("ShaderNodeAttribute")
            attr.name=prop; attr.attribute_name=prop; attr.attribute_type='OBJECT'; attr.location=(0,-200*idx)
            links.new(prev,                   mix.inputs['Color1'])
            links.new(attr.outputs['Color'], mix.inputs['Color2'])
            links.new(mix.outputs['Color'],  em.inputs['Color'])
            
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
                prev_links = mix.inputs['Color1'].links
                prev_sock  = prev_links[0].from_socket if prev_links else None
                outs       = [lk.to_socket for lk in mix.outputs['Color'].links]
                nodes.remove(mix)
                if prev_sock:
                    for to in outs: links.new(prev_sock,to)
            attr = nodes.get(prop)
            if attr: nodes.remove(attr)
        sc.ly_layers.remove(idx)
        sc.ly_layers_index = max(0, idx-1)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_toggle_solo(bpy.types.Operator):
    bl_idname = "lightingmod.layer_toggle_solo"
    bl_label  = "Toggle Solo"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene
        L = sc.ly_layers
        if 0 <= self.index < len(L):
            L[self.index].solo = not L[self.index].solo
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

class LIGHTINGMOD_OT_layer_toggle_mute(bpy.types.Operator):
    bl_idname = "lightingmod.layer_toggle_mute"
    bl_label  = "Toggle Mute"
    index: IntProperty()
    def execute(self, context):
        sc = context.scene
        L = sc.ly_layers
        if 0 <= self.index < len(L):
            L[self.index].mute = not L[self.index].mute
            utils.refresh_layer_enable(sc)
        return {'FINISHED'}

classes = (
    LIGHTINGMOD_OT_layer_add,
    LIGHTINGMOD_OT_layer_remove,
    LIGHTINGMOD_OT_layer_toggle_solo,
    LIGHTINGMOD_OT_layer_toggle_mute,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
