import bpy
import re

# --- Globals ---
last_batch_history = {}
baked_colors = {}

BLEND_MAP = {
    'REPLACE':'COLOR','MIX':'MIX','ADD':'ADD','SUBTRACT':'SUBTRACT',
    'MULTIPLY':'MULTIPLY','LIGHTEN':'LIGHTEN','DARKEN':'DARKEN','SCREEN':'SCREEN',
}

_LAYER_PROP_RE  = re.compile(r'\["Layer_(\d+)"\]')
_SCN_OPACITY_RE = re.compile(r'ly_layers\[(\d+)\]\.opacity')

# --- Helper Functions ---
def blend_colors(base, top, mode, fac):
    if   mode=='ADD':      out = [min(1.0, base[i]+top[i]) for i in range(3)]
    elif mode=='SUBTRACT': out = [max(0.0, base[i]-top[i]) for i in range(3)]
    elif mode=='MULTIPLY': out = [base[i]*top[i]       for i in range(3)]
    elif mode=='LIGHTEN':  out = [max(base[i], top[i]) for i in range(3)]
    elif mode=='DARKEN':   out = [min(base[i], top[i]) for i in range(3)]
    elif mode=='SCREEN':   out = [1-(1-base[i])*(1-top[i]) for i in range(3)]
    else:                  out = top[:]
    return [ base[i]*(1-fac) + out[i]*fac for i in range(3) ]

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

def update_mix_node(context):
    sc = context.scene
    idx = sc.ly_layers_index
    if idx == 0: return
    mat = bpy.data.materials.get("drone colour")
    if not mat: return
    node = mat.node_tree.nodes.get(f"Layer_Mix_{idx+1}")
    if node:
        node.blend_type = BLEND_MAP[ sc.ly_layers[idx].blend_mode ]

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
