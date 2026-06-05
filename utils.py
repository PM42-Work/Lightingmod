import bpy
import math
import re

last_batch_history = {}
baked_colors = {}
USE_MAX_CHANNEL_MATTE = True

BLEND_MAP = {
    'REPLACE':'MIX','MIX':'MIX','ADD':'ADD','SUBTRACT':'SUBTRACT',
    'MULTIPLY':'MULTIPLY','LIGHTEN':'LIGHTEN','DARKEN':'DARKEN','SCREEN':'SCREEN',
}

# --- Layer Mixing Helpers ---
def blend_colors(base, top, mode, fac):
    b = [max(0.0, min(1.0, c)) for c in base]
    t = [max(0.0, min(1.0, c)) for c in top]

    if mode == 'REPLACE':
        if USE_MAX_CHANNEL_MATTE:
            alpha = max(0.0, min(1.0, max(t[0], t[1], t[2])))
            out = [b[i] * (1.0 - alpha) + t[i] * alpha for i in range(3)]
        else:
            out = t[:]
    elif mode == 'ADD':      out = [min(1.0, b[i]+t[i]) for i in range(3)]
    elif mode == 'SUBTRACT': out = [max(0.0, b[i]-t[i]) for i in range(3)]
    elif mode == 'MULTIPLY': out = [b[i]*t[i]       for i in range(3)]
    elif mode == 'LIGHTEN':  out = [max(b[i], t[i]) for i in range(3)]
    elif mode == 'DARKEN':   out = [min(b[i], t[i]) for i in range(3)]
    elif mode == 'SCREEN':   out = [1-(1-b[i])*(1-t[i]) for i in range(3)]
    else:                    out = t[:]
    
    return [ b[i]*(1-fac) + out[i]*fac for i in range(3) ]

def refresh_layer_enable(sc):
    if not getattr(sc, "adv_layers", None): return
    any_solo = any(l.solo for l in sc.adv_layers)
    mat = bpy.data.materials.get("drone colour")
    nodes = mat.node_tree.nodes if (mat and mat.node_tree) else None

    for i, layer in enumerate(sc.adv_layers):
        enabled = (not layer.mute) and (layer.solo or not any_solo)
        layer.rt_enable = enabled
        if not nodes: continue

        if i == 0:
            base_attr = nodes.get("Base_Layer") or nodes.get("Layer_1")
            if base_attr: base_attr.mute = not enabled
        else:
            mx = nodes.get(f"Layer_Mix_{i+1}")
            if mx: mx.mute = not enabled

def update_mix_node(context, passed_idx=None):
    sc = context.scene
    idx = sc.adv_layers_index if passed_idx is None else passed_idx
    if idx == 0 or idx >= len(sc.adv_layers): return
    
    mat = bpy.data.materials.get("drone colour")
    if not mat: return
    
    mix = mat.node_tree.nodes.get(f"Layer_Mix_{idx+1}")
    if not mix: return
    
    mode = sc.adv_layers[idx].blend_mode
    mix.blend_type = BLEND_MAP.get(mode, 'MIX')
    
    val_node = mat.node_tree.nodes.get(f"Layer_Opacity_{idx+1}")
    math_mul = mat.node_tree.nodes.get(f"Layer_Math_{idx+1}")
    
    if val_node and math_mul:
        for lnk in mix.inputs[0].links: mat.node_tree.links.remove(lnk)
        if mode == 'REPLACE' and USE_MAX_CHANNEL_MATTE:
            mat.node_tree.links.new(math_mul.outputs[0], mix.inputs[0])
        else:
            mat.node_tree.links.new(val_node.outputs[0], mix.inputs[0])

def set_editor_filter_for_layer(context, prop_name: str):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {'GRAPH_EDITOR', 'DOPESHEET_EDITOR'}:
                space = area.spaces.active
                ds = getattr(space, "dopesheet", None)
                if ds:
                    ds.show_only_selected = True
                    ds.use_multi_word_filter = False
                    ds.filter_text = prop_name
                area.tag_redraw()

# --- Nodes ---
def ensure_gradient_nodegroup():
    ng = bpy.data.node_groups.get("AdvLightingGradient")
    if not ng: ng = bpy.data.node_groups.new("AdvLightingGradient", 'ShaderNodeTree')
    if "Ramp" not in ng.nodes:
        ramp = ng.nodes.new('ShaderNodeValToRGB')
        ramp.name = "Ramp"; ramp.label = "Gradient Ramp"
        ramp.color_ramp.color_mode = 'OKLAB'; ramp.color_ramp.interpolation = 'EASE'
    return ng

def ensure_gradient_preview_nodegroup():
    ng = bpy.data.node_groups.get("AdvLightingGradientPreview")
    if not ng: ng = bpy.data.node_groups.new("AdvLightingGradientPreview", 'ShaderNodeTree')
    if "Ramp" not in ng.nodes:
        ramp = ng.nodes.new('ShaderNodeValToRGB')
        ramp.name = "Ramp"; ramp.label = "Preview Ramp"
        ramp.color_ramp.color_mode = 'OKLAB'; ramp.color_ramp.interpolation = 'EASE'
    return ng

def ensure_noise_nodegroup():
    ng = bpy.data.node_groups.get("AdvLightingNoiseRamp")
    if not ng:
        ng = bpy.data.node_groups.new("AdvLightingNoiseRamp", 'ShaderNodeTree')
        ng.interface.new_socket(name="Value", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket(name="Color", in_out='OUTPUT', socket_type='NodeSocketColor')
        
        ramp = ng.nodes.new('ShaderNodeValToRGB'); ramp.name = "Ramp"
        ramp.color_ramp.color_mode = 'OKLAB'; ramp.color_ramp.interpolation = 'EASE'
        
        inp = ng.nodes.new('NodeGroupInput'); outp = ng.nodes.new('NodeGroupOutput')
        ng.links.new(inp.outputs[0], ramp.inputs['Fac'])
        ng.links.new(ramp.outputs['Color'], outp.inputs[0])
    return ng

# --- Palette / Math Helpers ---
def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6: return [1.0, 1.0, 1.0]
    return [int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4)]

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(
        int(max(0, min(1, rgb[0])) * 255),
        int(max(0, min(1, rgb[1])) * 255),
        int(max(0, min(1, rgb[2])) * 255)
    )

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)

def linear_to_srgb(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * math.pow(c, 1 / 2.4) - 0.055

def rgb_to_oklch(r, g, b):
    lr, lg, lb = srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)
    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
    l_, m_, s_ = math.cbrt(max(0, l)) if l>=0 else -math.cbrt(-l), math.cbrt(max(0, m)) if m>=0 else -math.cbrt(-m), math.cbrt(max(0, s)) if s>=0 else -math.cbrt(-s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.sqrt(a*a + b_*b_)
    H = math.atan2(b_, a)
    if H < 0: H += 2 * math.pi
    return [L, C, H]

def oklch_to_rgb(L, C, H):
    a, b_ = C * math.cos(H), C * math.sin(H)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b_
    m_ = L - 0.1055613458 * a - 0.0638541728 * b_
    s_ = L - 0.0894841775 * a - 1.2914855480 * b_
    l, m, s = l_**3, m_**3, s_**3
    lr = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return [max(0, min(1, linear_to_srgb(lr))), max(0, min(1, linear_to_srgb(lg))), max(0, min(1, linear_to_srgb(lb)))]

def interpolate_oklch(color1, color2, t):
    l1, c1, h1 = rgb_to_oklch(*color1)
    l2, c2, h2 = rgb_to_oklch(*color2)
    
    diff = h2 - h1
    if diff > math.pi: h1 += 2 * math.pi
    elif diff < -math.pi: h2 += 2 * math.pi
        
    L, C, H = l1*(1-t) + l2*t, c1*(1-t) + c2*t, h1*(1-t) + h2*t
    return oklch_to_rgb(L, C, H)