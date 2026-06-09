from . import gradient, sparkle, domain, movie, offset, management, temporal, noise, gobo

classes = (
    gradient.ADVLIGHTING_OT_draw_gradient,
    gradient.ADVLIGHTING_OT_create_gradient_nodegroup,
    gradient.ADVLIGHTING_OT_flip_color_ramp, 
    
    sparkle.ADVLIGHTING_OT_sparkle_effector,
    
    domain.ADVLIGHTING_OT_domain_effector,
    
    # --- MOVIE ---
    movie.ADVLIGHTING_OT_load_movie_clip,
    movie.ADVLIGHTING_OT_spawn_movie_camera,
    movie.ADVLIGHTING_OT_remove_movie_cameras,
    movie.ADVLIGHTING_OT_movie_sampler,
    
    offset.ADVLIGHTING_OT_draw_offset_line,
    offset.ADVLIGHTING_OT_offset_keyframes,
    
    # --- GOBO ---
    management.ADVLIGHTING_OT_create_gobo_nodegroup,
    gobo.ADVLIGHTING_OT_load_gobo_image,
    gobo.ADVLIGHTING_OT_spawn_gobo_camera,
    gobo.ADVLIGHTING_OT_remove_gobo_cameras,
    gobo.ADVLIGHTING_OT_apply_gobo,
    
    management.ADVLIGHTING_OT_apply_effectors,
    management.ADVLIGHTING_OT_sample_drone_colors, 
    management.ADVLIGHTING_OT_effector_color_add,
    management.ADVLIGHTING_OT_effector_color_remove,
    management.ADVLIGHTING_OT_effector_monochrome,
    management.ADVLIGHTING_OT_set_effector_start, 
    management.ADVLIGHTING_OT_set_effector_end,   
    management.ADVLIGHTING_OT_spark_profile_add,
    management.ADVLIGHTING_OT_spark_profile_remove,
    
    temporal.ADVLIGHTING_OT_temporal_sparkle,
    temporal.ADVLIGHTING_OT_stage_add,
    temporal.ADVLIGHTING_OT_stage_remove,

    management.ADVLIGHTING_OT_create_noise_nodegroup,
    management.ADVLIGHTING_OT_draw_noise_flow,
    management.ADVLIGHTING_OT_align_noise_camera,

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