import bpy
from bpy.props import (StringProperty, EnumProperty, FloatProperty, BoolProperty, FloatVectorProperty)
from . import utils

class LightingModLayerItem(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
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

class LightingModEffectorColorItem(bpy.types.PropertyGroup):
    color: FloatVectorProperty(
        name="Color", subtype='COLOR', size=4,
        min=0.0, max=1.0, default=(1,1,1,1)
    )

classes = (
    LightingModLayerItem,
    LightingModEffectorColorItem,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
