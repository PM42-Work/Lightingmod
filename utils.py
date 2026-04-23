import bpy
import re

# --- Globals ---
last_batch_history = {}
baked_colors = {}

USE_MAX_CHANNEL_MATTE = True

# Map REPLACE to MIX so the viewport native nodes behave correctly
BLEND_MAP = {
    'REPLACE':'MIX','MIX':'MIX','ADD':'ADD','SUBTRACT':'SUBTRACT',
    'MULTIPLY':'MULTIPLY','LIGHTEN':'LIGHTEN','DARKEN':'DARKEN','SCREEN':'SCREEN',
}

_LAYER_PROP_RE  = re.compile(r'\["Layer_(\d+)"\]')
_SCN_OPACITY_RE = re.compile(r'ly_layers\[(\d+)\]\.opacity')

# --- Helper Functions ---
def blend_colors(base, top, mode, fac):
    # Clamp inputs 0-1 for safety
    b = [max(0.0, min(1.0, c)) for c in base]
    t = [max(0.0, min(1.0, c)) for c in top]

    if mode == 'REPLACE':
        if USE_MAX_CHANNEL_MATTE:
            alpha = max(t[0], t[1], t[2])
            alpha = max(0.0, min(1.0, alpha))
            out = [b[i] * (1.0 - alpha) + t[i] * alpha for i in range(3)]
        else:
            out = t[:]
    elif mode == 'ADD':      out = [min(1.0, b[i]+t[i]) for i in range(3)]
    elif mode == 'SUBTRACT': out = [max(0.0, b[i]-t[i]) for i in range(3)]
    elif mode == 'MULTIPLY': out = [b[i]*t[i]       for i in range(3)]
    elif mode == 'LIGHTEN':  out = [max(b[i], t[i]) for i in range(3)]
    elif mode == 'DARKEN':   out = [min(b[i], t[i]) for i in range(3)]
    elif mode == 'SCREEN':   out = [1-(1-b[i])*(1-t[i]) for i in range(3)]
    elif mode == 'MIX':      out = t[:]
    else:                    out = t[:]
    
    return [ b[i]*(1-fac) + out[i]*fac for i in range(3) ]

def refresh_layer_enable(sc):
    if not getattr(sc, "ly_layers", None):
        return
    any_solo = any(l.solo for l in sc.ly_layers)
    mat = bpy.data.materials.get("drone colour")
    nodes = mat.node_tree.nodes if (mat and mat.node_tree) else None

    for i, layer in enumerate(sc.ly_layers):
        enabled = (not layer.mute) and (layer.solo or not any_solo)
        layer.rt_enable = enabled
        if not nodes: continue

        if i == 0:
            base_attr = nodes.get("Base_Layer") or nodes.get("Layer_1")
            if base_attr:
                base_attr.mute = not enabled
        else:
            mx = nodes.get(f"Layer_Mix_{i+1}")
            if mx:
                mx.mute = not enabled

def update_mix_node(context, passed_idx=None):
    """Safely updates the mix node. Ignores if nodes are missing (user must click Redraw)"""
    sc = context.scene
    idx = sc.ly_layers_index if passed_idx is None else passed_idx
    if idx == 0 or idx >= len(sc.ly_layers): return
    
    mat = bpy.data.materials.get("drone colour")
    if not mat: return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    mix = nodes.get(f"Layer_Mix_{idx+1}")
    if not mix: return
    
    mode = sc.ly_layers[idx].blend_mode
    mix.blend_type = BLEND_MAP.get(mode, 'MIX')
    
    val_node = nodes.get(f"Layer_Opacity_{idx+1}")
    math_mul = nodes.get(f"Layer_Math_{idx+1}")
    
    # Only rewire if the advanced nodes actually exist
    if val_node and math_mul:
        # mix.inputs[0] is always 'Factor' / 'Fac' across all Blender versions
        for lnk in mix.inputs[0].links:
            links.remove(lnk)
            
        if mode == 'REPLACE' and USE_MAX_CHANNEL_MATTE:
            links.new(math_mul.outputs[0], mix.inputs[0])
        else:
            links.new(val_node.outputs[0], mix.inputs[0])

def set_editor_filter_for_layer(context, idx_zero_based: int):
    token = f'Layer_{idx_zero_based+1}'
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR'}:
                space = area.spaces.active
                ds = getattr(space, "dopesheet", None)
                if ds:
                    ds.show_only_selected = True
                    ds.use_multi_word_filter = False
                    ds.filter_text = token
                area.tag_redraw()

def ensure_gradient_nodegroup():
    ng = bpy.data.node_groups.get("LightingModGradient")
    if not ng:
        ng = bpy.data.node_groups.new("LightingModGradient", 'ShaderNodeTree')
    if "Ramp" not in ng.nodes:
        ramp = ng.nodes.new('ShaderNodeValToRGB')
        ramp.name = "Ramp"
        ramp.label = "Gradient Ramp"
    return ng

def ensure_noise_nodegroup():
    ng = bpy.data.node_groups.get("LightingModNoiseRamp")
    if not ng:
        ng = bpy.data.node_groups.new("LightingModNoiseRamp", 'ShaderNodeTree')
        
        # Setup Inputs and Outputs so we can connect it in the live shader
        ng.interface.new_socket(name="Value", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket(name="Color", in_out='OUTPUT', socket_type='NodeSocketColor')
        
        ramp = ng.nodes.new('ShaderNodeValToRGB')
        ramp.name = "Ramp"
        ramp.color_ramp.color_mode = 'OKLAB'
        ramp.color_ramp.interpolation = 'EASE'
        
        inp = ng.nodes.new('NodeGroupInput')
        outp = ng.nodes.new('NodeGroupOutput')
        
        ng.links.new(inp.outputs[0], ramp.inputs['Fac'])
        ng.links.new(ramp.outputs['Color'], outp.inputs[0])
    return ng

def update_noise_preview(context):
    sc = context.scene
    mat = bpy.data.materials.get("drone colour") 
    if not mat or not mat.use_nodes: return
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    # 1. CLEANUP
    if not sc.noise_preview:
        for n in list(nodes):
            if n.name.startswith("LM_NoisePreview_"): nodes.remove(n)
        update_mix_node(context) 
        return

    # 2. DO WE NEED TO REBUILD? (Only rebuild if missing or if Noise Type changed)
    rebuild = False
    mix = nodes.get("LM_NoisePreview_Mix")
    tex = nodes.get("LM_NoisePreview_Tex")
    if not mix or not tex: 
        rebuild = True
    else:
        if sc.noise_type == 'PERLIN' and tex.bl_idname != 'ShaderNodeTexNoise': rebuild = True
        if sc.noise_type == 'VORONOI' and tex.bl_idname != 'ShaderNodeTexVoronoi': rebuild = True

    # 3. BUILD IT NEATLY (Once)
    if rebuild:
        for n in list(nodes):
            if n.name.startswith("LM_NoisePreview_"): nodes.remove(n)
        
        update_mix_node(context) 
        
        out_node = next((n for n in nodes if n.type == 'EMISSION'), None)
        if not out_node: return

        # FIX: Object Info guarantees 1:1 location accuracy with the Python backend
        obj_info = nodes.new('ShaderNodeObjectInfo')
        obj_info.name = "LM_NoisePreview_Obj"; obj_info.location = (-1000, 200)
        
        add_node = nodes.new('ShaderNodeVectorMath')
        add_node.name = "LM_NoisePreview_Add"; add_node.operation = 'ADD'; add_node.location = (-800, 200)

        ramp_grp = nodes.new('ShaderNodeGroup')
        ramp_grp.name = "LM_NoisePreview_RampGrp"
        ramp_grp.node_tree = ensure_noise_nodegroup(); ramp_grp.location = (-400, 200)
        
        if sc.noise_type == 'PERLIN':
            tex = nodes.new('ShaderNodeTexNoise')
            tex.noise_dimensions = '3D'; tex.inputs['Detail'].default_value = 0.0
            if hasattr(tex, 'normalize'): tex.normalize = False
            links.new(tex.outputs['Fac'], ramp_grp.inputs['Value'])
        elif sc.noise_type == 'VORONOI':
            tex = nodes.new('ShaderNodeTexVoronoi')
            tex.voronoi_dimensions = '3D'; tex.feature = 'F1'; tex.distance = 'EUCLIDEAN'
            links.new(tex.outputs['Distance'], ramp_grp.inputs['Value'])
            
        tex.name = "LM_NoisePreview_Tex"; tex.location = (-600, 200)
        
        mix = nodes.new('ShaderNodeMix')
        mix.name = "LM_NoisePreview_Mix"; mix.data_type = 'RGBA'; mix.inputs[0].default_value = 1.0; mix.location = (-200, 200)
        
        links.new(obj_info.outputs['Location'], add_node.inputs[0])
        links.new(add_node.outputs['Vector'], tex.inputs['Vector'])
        
        orig_socket = out_node.inputs[0]
        if orig_socket.links: links.new(orig_socket.links[0].from_socket, mix.inputs[6]) 
        links.new(ramp_grp.outputs['Color'], mix.inputs[7]) 
        links.new(mix.outputs[2], orig_socket)

    # 4. LIVE DRIVER UPDATE (Updates smoothly when dragging UI sliders)
    tex = nodes.get("LM_NoisePreview_Tex")
    if tex: tex.inputs['Scale'].default_value = sc.noise_scale
    
    add_node = nodes.get("LM_NoisePreview_Add")
    if add_node:
        for i, axis in enumerate(['x', 'y', 'z']):
            d = add_node.inputs[1].driver_add("default_value", i)
            d.driver.expression = f"frame / 24.0 * {getattr(sc.noise_direction, axis)} * {sc.noise_speed}"