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
        for lnk in mix.inputs['Fac'].links:
            links.remove(lnk)
            
        if mode == 'REPLACE' and USE_MAX_CHANNEL_MATTE:
            links.new(math_mul.outputs[0], mix.inputs['Fac'])
        else:
            links.new(val_node.outputs[0], mix.inputs['Fac'])

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