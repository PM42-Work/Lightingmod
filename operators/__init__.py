from . import layers, baking, batch, effectors

def register():
    layers.register()
    baking.register()
    batch.register()
    effectors.register()

def unregister():
    effectors.unregister()
    batch.unregister()
    baking.unregister()
    layers.unregister()
