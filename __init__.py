bl_info = {
    "name": "Advanced Lighting",
    "author": "Raghuvansh Agarwal",
    "version": (0, 3, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Advanced Lighting",
    "description": "Modular advanced drone color & effector controls",
    "category": "3D View",
}

import bpy
from bpy.props import (StringProperty, EnumProperty, FloatProperty, IntProperty,
                       FloatVectorProperty, CollectionProperty, BoolProperty, PointerProperty)

from . import utils
from . import properties
from . import ui
from . import operators

def _on_active_layer_changed(self, context):
    sc = context.scene
    idx = sc.ly_layers_index
    sc.batch_target_layer = str(idx)
    sc.effector_target_layer = str(idx)
    utils.set_editor_filter_for_layer(context, idx)

def get_layer_items(self, context):
    return [(str(i), f"{i+1}: {item.name}", "") for i, item in enumerate(context.scene.ly_layers)]

def register():
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
    
    # NEW: Selection Mode
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
          ('DOMAIN','Domain',''),
          ('MOVIE','Movie UV',''),
          ('OFFSET','Offset',''),
        ], default='SPARKLE'
    )
    sc.effector_start = IntProperty(name="Start", default=1)
    sc.effector_end = IntProperty(name="End", default=250)
    sc.effector_transition = IntProperty(name="Transition", default=10, min=0)
    sc.effector_influence = FloatProperty(name="Influence", min=0, max=1, default=0.5)
    sc.effector_selected_only = BoolProperty(name="Selected Only", default=False)
    sc.domain_object = PointerProperty(name="Domain Object", type=bpy.types.Object)
    sc.effector_duration = IntProperty(name="Duration", default=10, min=0)

    sc.effector_colors = CollectionProperty(type=properties.LightingModEffectorColorItem)
    sc.effector_colors_index = IntProperty(default=0)

    sc.new_uv_map_name = StringProperty(name="UV Name", default="LIGHTINGMOD")
    sc.movie_uv_map = EnumProperty(
        name="UV Map",
        items=lambda self, context: [(uv.name,uv.name,"") for uv in (context.object.data.uv_layers if context.object and context.object.type=='MESH' else [])]
    )
    sc.movie_step = IntProperty(name="Step", default=1, min=1)
    sc.image_texture = PointerProperty(name="Image", type=bpy.types.Image)

    # NEW: Curve & Split Modes
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

    # NEW: Collections
    sc.drone_formations = CollectionProperty(type=properties.LightingModFormation)
    sc.drone_formations_index = IntProperty()
    sc.temporal_stages = CollectionProperty(type=properties.LightingModTemporalStage)
    sc.temporal_stages_index = IntProperty()

    # Init Filter
    try:
        if bpy.context and bpy.context.scene:
            utils.set_editor_filter_for_layer(bpy.context, bpy.context.scene.ly_layers_index)
    except: pass

def unregister():
    ui.unregister()
    operators.unregister()
    properties.unregister()
    
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
    del bpy.types.Scene.drone_formations
    del bpy.types.Scene.drone_formations_index
    del bpy.types.Scene.temporal_stages
    del bpy.types.Scene.temporal_stages_index

if __name__ == "__main__":
    register()