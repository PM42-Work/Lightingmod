from . import layers, baking, batch, effectors, groups

def register():
    layers.register()
    baking.register()
    batch.register()
    effectors.register()
    groups.register()

def unregister():
    groups.unregister()
    effectors.unregister()
    batch.unregister()
    baking.unregister()
    layers.unregister()