from . import gradient, sparkle, domain, movie, offset, management

classes = (
    gradient.LIGHTINGMOD_OT_draw_gradient,
    gradient.LIGHTINGMOD_OT_create_gradient_nodegroup,
    
    sparkle.LIGHTINGMOD_OT_sparkle_effector,
    
    domain.LIGHTINGMOD_OT_domain_effector,
    
    movie.LIGHTINGMOD_OT_movie_sampler,
    movie.LIGHTINGMOD_OT_generate_uv,
    
    offset.LIGHTINGMOD_OT_draw_offset_line,
    offset.LIGHTINGMOD_OT_offset_keyframes,
    
    management.LIGHTINGMOD_OT_apply_effectors,
    management.LIGHTINGMOD_OT_effector_color_add,
    management.LIGHTINGMOD_OT_effector_color_remove,
    management.LIGHTINGMOD_OT_effector_monochrome,
    management.LIGHTINGMOD_OT_set_start_frame,
    management.LIGHTINGMOD_OT_set_end_frame,
)

def register():
    for cls in classes:
        import bpy
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        import bpy
        bpy.utils.unregister_class(cls)
