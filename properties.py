import bpy
from bpy.props import (StringProperty, EnumProperty, FloatProperty, BoolProperty, FloatVectorProperty, CollectionProperty, IntProperty)
from . import utils

class AdvLightingLayerItem(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    data_source: StringProperty(name="Data Source")
    blend_mode: EnumProperty(
        name="Blend Mode",
        items=[(k,k.title(),"") for k in utils.BLEND_MAP.keys()],
        default='REPLACE',
        update=lambda self,ctx: utils.update_mix_node(ctx)
    )
    opacity: FloatProperty(name="Influence", min=0.0, max=1.0, default=1.0)
    solo: BoolProperty(name="Solo", default=False)
    mute: BoolProperty(name="Mute", default=False)
    rt_enable: BoolProperty(name="Runtime Enabled", default=True)

class AdvLightingColorPaletteItem(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Saved Color")
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0)

class AdvLightingGradientStop(bpy.types.PropertyGroup):
    pos: FloatProperty(name="Position")
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0)

class AdvLightingGradientPaletteItem(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Saved Gradient")
    stops: CollectionProperty(type=AdvLightingGradientStop)

class AdvLightingSampledColor(bpy.types.PropertyGroup):
    name: StringProperty(name="Drone Name")
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0)

class AdvLightingEffectorColorItem(bpy.types.PropertyGroup):
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=4, min=0.0, max=1.0, default=(1,1,1,1))

class AdvLightingTemporalStage(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Stage")
    transition: IntProperty(name="Transition", min=1, default=10)
    influence: FloatProperty(name="Influence", min=0, max=1, default=0.5)
    colors: CollectionProperty(type=AdvLightingEffectorColorItem)
    colors_index: IntProperty(default=0)
    color_source: EnumProperty(
        name="Color Source",
        items=[('PALETTE', 'Palette', ''), ('SAMPLED', 'Sampled', '')],
        default='PALETTE'
    )
    sampled_colors: CollectionProperty(type=AdvLightingSampledColor)

class AdvLightingSparkProfile(bpy.types.PropertyGroup):
    name: StringProperty(name="Profile Name", default="Profile")
    style: EnumProperty(items=[('PULSE', 'Pulse', ''), ('TWINKLE', 'Twinkle', '')], default='PULSE')
    weight: FloatProperty(name="Weight", min=0.0, default=1.0)
    lifespan: IntProperty(name="Lifespan", min=1, default=10)
    colors: CollectionProperty(type=AdvLightingEffectorColorItem)
    colors_index: IntProperty(default=0)

class AdvLightingDroneRef(bpy.types.PropertyGroup):
    object_name: StringProperty(name="Object")

class AdvLightingDroneGroup(bpy.types.PropertyGroup):
    name: StringProperty(name="Group Name", default="Group")
    drones: CollectionProperty(type=AdvLightingDroneRef)
    drones_index: IntProperty(default=0)

class AdvLightingFormation(bpy.types.PropertyGroup):
    name: StringProperty(name="Formation Name", default="Formation")
    groups: CollectionProperty(type=AdvLightingDroneGroup)
    groups_index: IntProperty(default=0)

classes = (
    AdvLightingLayerItem, AdvLightingColorPaletteItem, AdvLightingGradientStop, 
    AdvLightingGradientPaletteItem, AdvLightingSampledColor, AdvLightingEffectorColorItem, 
    AdvLightingTemporalStage, AdvLightingSparkProfile, AdvLightingDroneRef, 
    AdvLightingDroneGroup, AdvLightingFormation,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)