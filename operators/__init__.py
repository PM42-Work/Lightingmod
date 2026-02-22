from . import layers, baking, batch, effectors, groups, updater

def register():
    layers.register()
    baking.register()
    batch.register()
    effectors.register()
    groups.register()
    updater.register()

def unregister():
    updater.unregister()
    groups.unregister()
    effectors.unregister()
    batch.unregister()
    baking.unregister()
    layers.unregister()