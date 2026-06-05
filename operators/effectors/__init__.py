from . import gradient, sparkle, domain, movie, offset, management, temporal, noise

classes = (
    gradient.ADVLIGHTING_OT_draw_gradient,
    gradient.ADVLIGHTING_OT_create_gradient_nodegroup,
    gradient.ADVLIGHTING_OT_flip_color_ramp, 
    
    sparkle.ADVLIGHTING_OT_sparkle_effector,
    
    domain.ADVLIGHTING_OT_domain_effector,
    
    movie.ADVLIGHTING_OT_movie_sampler,
    # (generate_uv was removed from here)
    
    offset.ADVLIGHTING_OT_draw_offset_line,
    offset.ADVLIGHTING_OT_offset_keyframes,
    
    management.ADVLIGHTING_OT_apply_effectors,
    management.ADVLIGHTING_OT_sample_drone_colors, # <--- Added!
    management.ADVLIGHTING_OT_effector_color_add,
    management.ADVLIGHTING_OT_effector_color_remove,
    management.ADVLIGHTING_OT_effector_monochrome,
    management.ADVLIGHTING_OT_set_start_frame,
    management.ADVLIGHTING_OT_set_end_frame,
    management.ADVLIGHTING_OT_spark_profile_add,
    management.ADVLIGHTING_OT_spark_profile_remove,
    
    temporal.ADVLIGHTING_OT_temporal_sparkle,
    temporal.ADVLIGHTING_OT_stage_add,
    temporal.ADVLIGHTING_OT_stage_remove,

    management.ADVLIGHTING_OT_create_noise_nodegroup,
    management.ADVLIGHTING_OT_draw_noise_flow,

    noise.ADVLIGHTING_OT_noise_effector,
)

def register():
    for cls in classes:
        import bpy
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        import bpy
        bpy.utils.unregister_class(cls)