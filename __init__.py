bl_info = {
    "name": "Advanced Lighting (Layered V3)",
    "author": "Raghuvansh Agarwal",
    "version": (3, 0, 0),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Advanced Lighting",
    "description": "Multi-layer drone color engine with OKLCH & 4.3 Support",
    "category": "3D View",
}

import sys, os, platform, bpy
from bpy.props import (StringProperty, EnumProperty, FloatProperty, IntProperty,
                       FloatVectorProperty, CollectionProperty, BoolProperty, PointerProperty)

current_dir = os.path.dirname(os.path.realpath(__file__))
system_platform = platform.system().lower() 
dep_folder = "win" if system_platform == 'windows' else "mac" if system_platform == 'darwin' else "linux"
dep_path = os.path.join(current_dir, "dependencies", dep_folder)
if dep_path not in sys.path: sys.path.insert(0, dep_path)

from . import utils, properties, ui, operators

class AdvLightingPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    use_experimental_updates: BoolProperty(name="Opt-in to Experimental Beta Updates", default=False)
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_experimental_updates")
        btn_text = "Check for Beta Updates" if self.use_experimental_updates else "Check for Stable Updates"
        layout.operator("advlighting.update_addon", text=btn_text, icon='FILE_REFRESH')

def _on_active_layer_changed(self, context):
    sc = context.scene
    idx = sc.adv_layers_index
    sc.adv_batch_target_layer = str(idx)
    sc.adv_effector_target_layer = str(idx)
    utils.set_editor_filter_for_layer(context, f"Layer_{idx+1}")

def get_layer_items(self, context):
    if not context.scene.adv_layers:
        return [('0', "No Layers", "")]
    return [(str(i), f"{i+1}: {item.name}", "") for i, item in enumerate(context.scene.adv_layers)]

def _on_effector_type_changed(self, context):
    if context.scene.adv_effector_type == 'SPARKLE' and not context.scene.adv_spark_profiles:
        p = context.scene.adv_spark_profiles.add()
        p.name = "Base Profile"

def _update_gradient_preview(self, context):
    sc = context.scene
    if not sc.adv_gradient_palettes: return
    item = sc.adv_gradient_palettes[sc.adv_gradient_palettes_index]
    
    ng = utils.ensure_gradient_preview_nodegroup()
    ramp = ng.nodes["Ramp"].color_ramp
    
    for i in range(len(ramp.elements)-1, 0, -1):
        ramp.elements.remove(ramp.elements[i])
        
    ramp.elements[0].position = item.stops[0].pos
    ramp.elements[0].color = list(item.stops[0].color) + [1.0]
    
    for i in range(1, len(item.stops)):
        el = ramp.elements.new(item.stops[i].pos)
        el.color = list(item.stops[i].color) + [1.0]

def register():
    bpy.utils.register_class(AdvLightingPreferences)
    properties.register()
    ui.register()
    operators.register()

    sc = bpy.types.Scene
    sc.adv_layers = CollectionProperty(type=properties.AdvLightingLayerItem)
    sc.adv_layers_index = IntProperty(default=0, update=_on_active_layer_changed)
    sc.adv_needs_layer_rebuild = BoolProperty(default=False)
    
    sc.adv_batch_primary_color = FloatVectorProperty(subtype='COLOR',size=4,default=(1,1,1,1),min=0,max=1)
    sc.adv_batch_secondary_color = FloatVectorProperty(subtype='COLOR',size=4,default=(0,0,0,1),min=0,max=1)
    sc.adv_batch_target_layer = EnumProperty(name="Target Layer",items=get_layer_items)
    
    sc.adv_bake_start = IntProperty(name="Bake Start", default=1)
    sc.adv_bake_end = IntProperty(name="Bake End", default=250)
    
    sc.adv_color_palettes = CollectionProperty(type=properties.AdvLightingColorPaletteItem)
    sc.adv_color_palettes_index = IntProperty(default=0)
    sc.adv_show_color_palettes = BoolProperty(default=False)
    
    sc.adv_gradient_palettes = CollectionProperty(type=properties.AdvLightingGradientPaletteItem)
    sc.adv_gradient_palettes_index = IntProperty(default=0, update=_update_gradient_preview)
    sc.adv_show_gradient_palettes = BoolProperty(default=False)
    
    sc.adv_color_source = EnumProperty(
        name="Color Source", items=[('PALETTE', 'Palette', ''), ('SAMPLED', 'Sampled', '')], default='PALETTE'
    )
    sc.adv_sampled_colors = CollectionProperty(type=properties.AdvLightingSampledColor)
    
    sc.adv_effector_target_layer = EnumProperty(name="Target Layer",items=get_layer_items)
    sc.adv_effector_selection_mode = EnumProperty(
        name="Target", items=[('SELECTED', "Selected Objects", ""), ('GROUP', "Active Group", "")], default='SELECTED'
    )
    sc.adv_effector_type = EnumProperty(
        name="Type",
        items=[
          ('GRADIENT','Gradient',''), ('SPARKLE','Sparkle',''), ('TEMPORAL_SPARKLE','Temporal Sparkle',''),
          ('NOISE', 'Noise', ''), ('DOMAIN','Domain',''), ('MOVIE','Movie Proj',''), ('OFFSET','Offset',''),
        ], default='SPARKLE', update=_on_effector_type_changed
    )
    sc.adv_sparkle_style = EnumProperty(
        name="Style", items=[('PULSE', 'Pulse (Smooth Fade)', ''), ('TWINKLE', 'Twinkle (Sharp Pop)', '')], default='PULSE'
    )

    sc.adv_effector_start = IntProperty(name="Start", default=1)
    sc.adv_effector_end = IntProperty(name="End", default=250)
    sc.adv_effector_transition = IntProperty(name="Transition", default=10, min=0)
    sc.adv_effector_influence = FloatProperty(name="Influence", min=0, max=1, default=0.5)
    sc.adv_domain_object = PointerProperty(name="Domain Object", type=bpy.types.Object)
    sc.adv_effector_duration = IntProperty(name="Duration", default=10, min=0)
    sc.adv_effector_colors = CollectionProperty(type=properties.AdvLightingEffectorColorItem)
    sc.adv_effector_colors_index = IntProperty(default=0)
    sc.adv_movie_step = IntProperty(name="Step", default=1, min=1)

    sc.adv_gradient_mode = EnumProperty(
        name="Mode", items=[
          ('LINEAR','Linear',''), ('SPLIT','Split Linear',''), ('RADIAL_2D','2D Radial',''),
          ('RADIAL_3D','3D Radial',''), ('CURVE','Curve',''),
        ], default='LINEAR'
    )
    sc.adv_curve_object = PointerProperty(name="Curve", type=bpy.types.Object)
    sc.adv_curve_radius = FloatProperty(name="Radius", default=0.5)
    sc.adv_curve_mode   = EnumProperty(items=[('PER_CURVE', 'Each Curve 0-1', ''), ('GLOBAL', 'Relative to Longest', '')], default='PER_CURVE')
    sc.adv_offset_line_start = FloatVectorProperty(name="Offset Line Start", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    sc.adv_offset_line_end = FloatVectorProperty(name="Offset Line End", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    
    sc.adv_drone_formations = CollectionProperty(type=properties.AdvLightingFormation)
    sc.adv_drone_formations_index = IntProperty()
    sc.adv_temporal_stages = CollectionProperty(type=properties.AdvLightingTemporalStage)
    sc.adv_temporal_stages_index = IntProperty()
    sc.adv_spark_profiles = CollectionProperty(type=properties.AdvLightingSparkProfile)
    sc.adv_spark_profiles_index = IntProperty(default=0)
    sc.adv_use_advanced_spark_profiles = BoolProperty(name="Use Multiple Profiles", default=False)

    sc.adv_noise_type = bpy.props.EnumProperty(
        name="Noise Type", items=[('PERLIN', 'Perlin (Clouds)', ''), ('VORONOI', 'Voronoi (Cells)', '')], default='PERLIN'
    )
    # Advanced Noise Scaling Properties
    sc.adv_noise_scale_linked = bpy.props.BoolProperty(name="Linked", default=True)
    sc.adv_noise_scale_master = bpy.props.FloatProperty(name="Scale", default=0.02, min=0.001)
    sc.adv_noise_scale_xyz = bpy.props.FloatVectorProperty(name="Scale XYZ", default=(0.02, 0.02, 0.02), min=0.001, subtype='XYZ')
    
    sc.adv_noise_contrast = bpy.props.FloatProperty(name="Contrast", default=0.0, min=0.0, max=1.0)
    sc.adv_noise_direction = bpy.props.FloatVectorProperty(name="Direction", default=(0.0, 0.0, 1.0), subtype='XYZ')
    sc.adv_noise_speed = bpy.props.FloatProperty(name="Speed", default=1.0)
    sc.adv_noise_fade_in = bpy.props.IntProperty(name="Fade In", default=0, min=0)
    sc.adv_noise_fade_out = bpy.props.IntProperty(name="Fade Out", default=0, min=0)

def unregister():
    ui.unregister()
    operators.unregister()
    properties.unregister()
    bpy.utils.unregister_class(AdvLightingPreferences)
    
    # We will let Blender's garbage collector handle the properties safely upon unregistration
    # to avoid bloat in the unregister function.