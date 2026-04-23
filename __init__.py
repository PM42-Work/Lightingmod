bl_info = {
    "name": "Advanced Lighting",
    "author": "Raghuvansh Agarwal",
    "version": (1, 4, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Advanced Lighting",
    "description": "Modular advanced drone color & effector controls",
    "category": "3D View",
}

import sys
import os
import platform
import bpy

# Register Dependencies
current_dir = os.path.dirname(os.path.realpath(__file__))
system_platform = platform.system().lower() 

if system_platform == 'windows':
    dep_folder = "win"
elif system_platform == 'darwin':
    dep_folder = "mac"
else:
    dep_folder = "linux"

dep_path = os.path.join(current_dir, "dependencies", dep_folder)
if dep_path not in sys.path:
    sys.path.insert(0, dep_path)

from bpy.props import (StringProperty, EnumProperty, FloatProperty, IntProperty,
                       FloatVectorProperty, CollectionProperty, BoolProperty, PointerProperty)

from . import utils
from . import properties
from . import ui
from . import operators

# --- ADDON PREFERENCES ---
class LightingModPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    use_experimental_updates: BoolProperty(
        name="Opt-in to Experimental Beta Updates",
        default=False,
        description="Download pre-release versions from GitHub when updating"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_experimental_updates")
        
        btn_text = "Check for Beta Updates" if self.use_experimental_updates else "Check for Stable Updates"
        layout.operator("lightingmod.update_addon", text=btn_text, icon='FILE_REFRESH')


def _on_active_layer_changed(self, context):
    sc = context.scene
    idx = sc.ly_layers_index
    sc.batch_target_layer = str(idx)
    sc.effector_target_layer = str(idx)
    utils.set_editor_filter_for_layer(context, idx)

def get_layer_items(self, context):
    return [(str(i), f"{i+1}: {item.name}", "") for i, item in enumerate(context.scene.ly_layers)]

def _on_effector_type_changed(self, context):
    if context.scene.effector_type == 'SPARKLE' and not context.scene.spark_profiles:
        p = context.scene.spark_profiles.add()
        p.name = "Base Profile"

def _trigger_noise_preview(self, context):
    from . import utils
    utils.update_noise_preview(context)

def register():
    bpy.utils.register_class(LightingModPreferences)
    properties.register()
    ui.register()
    operators.register()

    sc = bpy.types.Scene
    sc.ly_layers = CollectionProperty(type=properties.LightingModLayerItem)
    sc.ly_layers_index = IntProperty(default=0, update=_on_active_layer_changed)
    
    sc.batch_primary_color = FloatVectorProperty(subtype='COLOR',size=4,default=(1,1,1,1),min=0,max=1)
    sc.batch_secondary_color = FloatVectorProperty(subtype='COLOR',size=4,default=(0,0,0,1),min=0,max=1)
    sc.batch_target_layer = EnumProperty(name="Target Layer",items=get_layer_items)
    
    sc.effector_target_layer = EnumProperty(name="Target Layer",items=get_layer_items)
    
    sc.effector_selection_mode = EnumProperty(
        name="Target",
        items=[('SELECTED', "Selected Objects", ""), ('GROUP', "Active Group", "")],
        default='SELECTED'
    )

    sc.effector_type = EnumProperty(
        name="Type",
        items=[
          ('GRADIENT','Gradient',''),
          ('SPARKLE','Sparkle',''),
          ('TEMPORAL_SPARKLE','Temporal Sparkle',''),
          ('NOISE', 'Noise', ''),
          ('DOMAIN','Domain',''),
          ('MOVIE','Movie UV',''),
          ('OFFSET','Offset',''),
        ], default='SPARKLE', update=_on_effector_type_changed # <--- Added update hook
    )

    sc.sparkle_style = EnumProperty(
        name="Style",
        items=[
            ('PULSE', 'Pulse (Smooth Fade)', ''),
            ('TWINKLE', 'Twinkle (Sharp Pop)', '')
        ],
        default='PULSE'
    )

    sc.effector_start = IntProperty(name="Start", default=1)
    sc.effector_end = IntProperty(name="End", default=250)
    sc.effector_transition = IntProperty(name="Transition", default=10, min=0)
    sc.effector_influence = FloatProperty(name="Influence", min=0, max=1, default=0.5)
    sc.effector_selected_only = BoolProperty(name="Selected Only", default=False)
    sc.domain_object = PointerProperty(name="Domain Object", type=bpy.types.Object)
    sc.effector_duration = IntProperty(name="Duration", default=10, min=0)

    # --- NEW PROPERTIES ---
    sc.effector_absolute_position = FloatVectorProperty(name="Absolute Position", subtype='TRANSLATION', size=3, default=(0.0, 0.0, 0.0))
    sc.needs_layer_rebuild = BoolProperty(default=False)

    sc.effector_colors = CollectionProperty(type=properties.LightingModEffectorColorItem)
    sc.effector_colors_index = IntProperty(default=0)

    sc.new_uv_map_name = StringProperty(name="UV Name", default="LIGHTINGMOD")
    sc.movie_uv_map = EnumProperty(
        name="UV Map",
        items=lambda self, context: [(uv.name,uv.name,"") for uv in (context.object.data.uv_layers if context.object and context.object.type=='MESH' else [])]
    )
    sc.movie_step = IntProperty(name="Step", default=1, min=1)
    sc.image_texture = PointerProperty(name="Image", type=bpy.types.Image)

    sc.gradient_mode = EnumProperty(
        name="Mode",
        items=[
          ('LINEAR','Linear',''),
          ('SPLIT','Split Linear',''),
          ('RADIAL_2D','2D Radial',''),
          ('RADIAL_3D','3D Radial',''),
          ('CURVE','Curve',''),
        ], default='LINEAR'
    )
    sc.gradient_ng = PointerProperty(type=bpy.types.NodeTree)
    sc.curve_object = PointerProperty(name="Curve", type=bpy.types.Object)
    sc.curve_radius = FloatProperty(name="Radius", default=0.5)
    sc.curve_mode   = EnumProperty(items=[('PER_CURVE', 'Each Curve 0-1', ''), ('GLOBAL', 'Relative to Longest', '')], default='PER_CURVE')
    
    sc.offset_line_start = FloatVectorProperty(name="Offset Line Start", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    sc.offset_line_end = FloatVectorProperty(name="Offset Line End", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    
    sc.export_folder = StringProperty(name="Export Folder", subtype='DIR_PATH', default="//")
    sc.export_filename = StringProperty(name="Filename", default="color_transfer", description="Name of the exported JSON file")

    sc.drone_formations = CollectionProperty(type=properties.LightingModFormation)
    sc.drone_formations_index = IntProperty()
    sc.temporal_stages = CollectionProperty(type=properties.LightingModTemporalStage)
    sc.temporal_stages_index = IntProperty()
    sc.spark_profiles = CollectionProperty(type=properties.LightingModSparkProfile)
    sc.spark_profiles_index = IntProperty(default=0)
    sc.use_advanced_spark_profiles = BoolProperty(name="Use Multiple Profiles", default=False)

    # --- NOISE PROPERTIES ---
    sc.noise_type = bpy.props.EnumProperty(
        name="Noise Type",
        items=[('PERLIN', 'Perlin (Clouds)', ''), ('VORONOI', 'Voronoi (Cells)', '')], 
        default='PERLIN', update=_trigger_noise_preview
    )
    
    sc.noise_scale = bpy.props.FloatProperty(name="Scale", default=0.02, min=0.001, update=_trigger_noise_preview)
    sc.noise_contrast = bpy.props.FloatProperty(name="Contrast", default=0.0, min=0.0, max=1.0, update=_trigger_noise_preview)
    sc.noise_direction = bpy.props.FloatVectorProperty(name="Direction", default=(0.0, 0.0, 1.0), subtype='XYZ', update=_trigger_noise_preview)
    sc.noise_speed = bpy.props.FloatProperty(name="Speed", default=1.0, update=_trigger_noise_preview)
    sc.noise_fade_in = bpy.props.IntProperty(name="Fade In", default=0, min=0)
    sc.noise_fade_out = bpy.props.IntProperty(name="Fade Out", default=0, min=0)

    try:
        if bpy.context and bpy.context.scene:
            utils.set_editor_filter_for_layer(bpy.context, bpy.context.scene.ly_layers_index)
    except: pass

def unregister():
    ui.unregister()
    operators.unregister()
    properties.unregister()
    bpy.utils.unregister_class(LightingModPreferences)
    
    del bpy.types.Scene.ly_layers
    del bpy.types.Scene.ly_layers_index
    del bpy.types.Scene.batch_primary_color
    del bpy.types.Scene.batch_secondary_color
    del bpy.types.Scene.batch_target_layer
    del bpy.types.Scene.effector_target_layer
    del bpy.types.Scene.effector_selection_mode
    del bpy.types.Scene.effector_type
    del bpy.types.Scene.effector_start
    del bpy.types.Scene.effector_end
    del bpy.types.Scene.effector_transition
    del bpy.types.Scene.effector_influence
    del bpy.types.Scene.effector_selected_only
    del bpy.types.Scene.domain_object
    del bpy.types.Scene.effector_duration
    del bpy.types.Scene.effector_absolute_position # <--- Clean up absolute position
    del bpy.types.Scene.needs_layer_rebuild        # <--- Clean up UI lock flag
    del bpy.types.Scene.effector_colors
    del bpy.types.Scene.effector_colors_index
    del bpy.types.Scene.new_uv_map_name
    del bpy.types.Scene.movie_uv_map
    del bpy.types.Scene.movie_step
    del bpy.types.Scene.image_texture
    del bpy.types.Scene.gradient_mode
    del bpy.types.Scene.gradient_ng
    del bpy.types.Scene.curve_object
    del bpy.types.Scene.curve_radius
    del bpy.types.Scene.curve_mode
    del bpy.types.Scene.offset_line_start
    del bpy.types.Scene.offset_line_end
    del bpy.types.Scene.export_folder
    del bpy.types.Scene.export_filename
    del bpy.types.Scene.drone_formations
    del bpy.types.Scene.drone_formations_index
    del bpy.types.Scene.temporal_stages
    del bpy.types.Scene.temporal_stages_index
    del bpy.types.Scene.spark_profiles
    del bpy.types.Scene.spark_profiles_index
    del bpy.types.Scene.use_advanced_spark_profiles
    del bpy.types.Scene.noise_type
    del bpy.types.Scene.noise_scale
    del bpy.types.Scene.noise_contrast
    del bpy.types.Scene.noise_direction
    del bpy.types.Scene.noise_speed
    del bpy.types.Scene.noise_fade_in
    del bpy.types.Scene.noise_fade_out

if __name__ == "__main__":
    register()