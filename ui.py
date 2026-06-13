import bpy
from . import utils

class ADVLIGHTING_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        sc = context.scene; row = layout.row(align=True)
        row.label(text=f"{index+1}: {item.name}")
        btn_row = row.row(align=True); btn_row.enabled = not sc.adv_needs_layer_rebuild 
        solo_icon = 'RADIOBUT_ON' if item.solo else 'RADIOBUT_OFF'
        btn_row.operator("advlighting.layer_toggle_solo", text="", icon=solo_icon).index = index
        mute_icon = 'MUTE_IPO_ON' if item.mute else 'MUTE_IPO_OFF'
        btn_row.operator("advlighting.layer_toggle_mute", text="", icon=mute_icon).index = index

class ADVLIGHTING_UL_color_palettes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "color", text="", emboss=True); row.prop(item, "name", text="", emboss=False)

class ADVLIGHTING_UL_gradient_palettes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='COLOR')

class ADVLIGHTING_UL_effector_colors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "color", text="", emboss=True)

class ADVLIGHTING_UL_formations(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='OUTLINER_COLLECTION')

class ADVLIGHTING_UL_groups(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='GROUP')

class ADVLIGHTING_UL_group_drones(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.object_name, icon='MESH_UVSPHERE')

class ADVLIGHTING_UL_temporal_stages(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='TIME')

class ADVLIGHTING_UL_spark_profiles(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False, icon='SHADERFX'); row.label(text=item.style.capitalize())

class ADVLIGHTING_PT_panel(bpy.types.Panel):
    bl_label="Advanced Lighting V3"; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category="Advanced Lighting"

    def draw(self, context):
        sc=context.scene; obj=context.object; L=sc.adv_layers; idx=L and sc.adv_layers_index; layout=self.layout

        # --- LAYERS BLOCK ---
        box=layout.box(); box.label(text="Layers")
        if sc.adv_needs_layer_rebuild:
            box.operator("advlighting.apply_layer_order", text="Apply Layer Order", icon='ERROR')
            
        row=box.row(align=True)
        add_rm_row = row.row(align=True); add_rm_row.enabled = not sc.adv_needs_layer_rebuild 
        add_rm_row.operator("advlighting.layer_add",icon='ADD',text="")
        add_rm_row.operator("advlighting.layer_remove",icon='REMOVE',text="")
        
        row.operator("advlighting.layer_move", icon='TRIA_UP', text="").direction = 'UP'
        row.operator("advlighting.layer_move", icon='TRIA_DOWN', text="").direction = 'DOWN'
        
        bake_row = box.row(align=True); bake_row.enabled = not sc.adv_needs_layer_rebuild
        
        # Modified Bake UI: Targets the base layer for final export!
        bake_col = bake_row.column(align=True)
        r = bake_col.row(align=True)
        r.prop(sc, "adv_bake_start", text="Bake Start")
        r.operator("advlighting.set_bake_start", icon='PREV_KEYFRAME', text="")
        r = bake_col.row(align=True)
        r.prop(sc, "adv_bake_end", text="Bake End")
        r.operator("advlighting.set_bake_end", icon='NEXT_KEYFRAME', text="")
        
        br = bake_col.row(align=True)
        br.operator("advlighting.bake_colors",icon='RENDER_STILL',text="Bake Mix to Base")
        br.operator("advlighting.bake_positions", icon='CON_LOCLIKE', text="Bake Positions")
        
        box.template_list("ADVLIGHTING_UL_layers","",sc,"adv_layers",sc,"adv_layers_index",rows=3)
        
        redraw_row = box.row(); redraw_row.enabled = not sc.adv_needs_layer_rebuild
        redraw_row.operator("advlighting.redraw_nodes",icon='FILE_REFRESH',text="Layer Redraw")
        redraw_row.operator("advlighting.view_baked", icon='RESTRICT_VIEW_OFF', text="Baked Redraw")
        
        if L:
            props_col = box.column(); props_col.enabled = not sc.adv_needs_layer_rebuild
            itm=L[idx]; props_col.prop(itm,"name",text=("Base Layer" if idx==0 else "Layer"))
            if idx>0: props_col.prop(itm,"blend_mode"); props_col.prop(itm,"opacity")

        main_col = layout.column(); main_col.enabled = not sc.adv_needs_layer_rebuild

        # --- BATCH COLOR ---
        box=main_col.box(); box.label(text="Batch Color")
        box.prop(sc,"adv_batch_target_layer",text="Target Layer")
        row=box.row(align=True)
        row.prop(sc,"adv_batch_primary_color",text="")
        row.operator("advlighting.swap_batch_colors",icon='FILE_REFRESH',text="")
        row.prop(sc,"adv_batch_secondary_color",text="")
        col=box.column(align=True)
        col.operator("advlighting.batch_color_keyframe",text="Color & Keyframe")
        col.operator("advlighting.batch_color",       text="Color Only")
        col.operator("advlighting.keyframe_current",  text="Keyframe Current")

        icon = 'TRIA_DOWN' if sc.adv_show_color_palettes else 'TRIA_RIGHT'
        box.prop(sc, "adv_show_color_palettes", icon=icon, text="Color Palette", emboss=False)
        if sc.adv_show_color_palettes:
            pbox = box.box()
            pbox.template_list("ADVLIGHTING_UL_color_palettes", "", sc, "adv_color_palettes", sc, "adv_color_palettes_index", rows=3)
            row = pbox.row(align=True)
            row.operator("advlighting.save_color", icon='ADD', text="Save Primary")
            row.operator("advlighting.remove_color", icon='REMOVE', text="")
            pbox.operator("advlighting.apply_color", icon='RESTRICT_COLOR_OFF', text="Set as Primary")

        # --- EFFECTORS ---
        box=main_col.box(); box.label(text="Effectors")
        box.prop(sc,"adv_effector_target_layer",text="Target Layer")
        box.prop(sc,"adv_effector_type",       text="Type")
        box.prop(sc,"adv_effector_selection_mode", text="Apply To")

        tp = sc.adv_effector_type
        if tp not in {'GRADIENT','OFFSET'}:
            row=box.row(align=True)
            row.prop(sc,"adv_effector_start",text="Start")
            row.operator("advlighting.set_effector_start",icon='PREV_KEYFRAME',text="")
            row=box.row(align=True)
            row.prop(sc,"adv_effector_end",  text="End")
            row.operator("advlighting.set_effector_end",  icon='NEXT_KEYFRAME',text="")

        if tp=='SPARKLE':
            box.prop(sc, "adv_effector_influence", text="Density")
            box.row().prop(sc, "adv_color_source", expand=True)
            
            if sc.adv_color_source == 'SAMPLED':
                pbox = box.box()
                op = pbox.operator("advlighting.sample_drone_colors", icon='CAMERA_DATA')
                op.target = 'SPARKLE'
                pbox.label(text=f"Cached: {len(sc.adv_sampled_colors)} Drones", icon='INFO')
                pbox.prop(sc, "adv_sparkle_style", text="Style")
                pbox.prop(sc, "adv_effector_transition", text="Lifespan (Frames)")
            else:
                box.prop(sc, "adv_use_advanced_spark_profiles", text="Use Multiple Profiles", icon='TRIA_DOWN' if sc.adv_use_advanced_spark_profiles else 'TRIA_RIGHT')
                if not sc.adv_spark_profiles:
                    box.operator("advlighting.spark_profile_add", text="Initialize Base Profile", icon='ADD')
                else:
                    if sc.adv_use_advanced_spark_profiles:
                        box.label(text="Profiles")
                        box.template_list("ADVLIGHTING_UL_spark_profiles", "", sc, "adv_spark_profiles", sc, "adv_spark_profiles_index", rows=3)
                        row = box.row(align=True)
                        row.operator("advlighting.spark_profile_add", icon='ADD', text="")
                        row.operator("advlighting.spark_profile_remove", icon='REMOVE', text="")
                        if sc.adv_spark_profiles:
                            prof = sc.adv_spark_profiles[sc.adv_spark_profiles_index]
                            p_box = box.box(); p_box.label(text=f"Editing: {prof.name}")
                            p_box.prop(prof, "style", text="Style"); p_box.prop(prof, "weight", text="Relative Weight"); p_box.prop(prof, "lifespan", text="Lifespan (Frames)")
                            p_box.template_list("ADVLIGHTING_UL_effector_colors", "", prof, "colors", prof, "colors_index", rows=2)
                            row = p_box.row(align=True)
                            op = row.operator("advlighting.effector_color_add", icon='ADD', text=""); op.target = 'SPARK_PROFILE'
                            op = row.operator("advlighting.effector_color_remove", icon='REMOVE', text=""); op.target = 'SPARK_PROFILE'
                    else:
                        prof = sc.adv_spark_profiles[0]
                        box.prop(prof, "style", text="Style"); box.prop(prof, "lifespan", text="Lifespan (Frames)"); box.label(text="Colors")
                        box.template_list("ADVLIGHTING_UL_effector_colors", "", prof, "colors", prof, "colors_index", rows=3)
                        row = box.row(align=True)
                        op = row.operator("advlighting.effector_color_add", icon='ADD', text=""); op.target = 'SPARK_PROFILE'
                        op = row.operator("advlighting.effector_color_remove", icon='REMOVE', text=""); op.target = 'SPARK_PROFILE'

        elif tp=='TEMPORAL_SPARKLE':
            box.prop(sc, "adv_sparkle_style")
            box.label(text="Temporal Stages")
            box.template_list("ADVLIGHTING_UL_temporal_stages", "", sc, "adv_temporal_stages", sc, "adv_temporal_stages_index", rows=2)
            row = box.row(align=True)
            row.operator("advlighting.stage_add", icon='ADD', text=""); row.operator("advlighting.stage_remove", icon='REMOVE', text="")
            if sc.adv_temporal_stages:
                stage = sc.adv_temporal_stages[sc.adv_temporal_stages_index]
                box.prop(stage, "transition", text="Lifespan"); box.prop(stage, "influence")
                box.row().prop(stage, "color_source", expand=True)
                if stage.color_source == 'SAMPLED':
                    pbox = box.box()
                    op = pbox.operator("advlighting.sample_drone_colors", icon='CAMERA_DATA')
                    op.target = 'TEMPORAL'
                    pbox.label(text=f"Cached: {len(stage.sampled_colors)} Drones", icon='INFO')
                else:
                    box.template_list("ADVLIGHTING_UL_effector_colors", "", stage, "colors", stage, "colors_index", rows=3)
                    row=box.row(align=True)
                    op=row.operator("advlighting.effector_color_add",icon='ADD',text=""); op.target='TEMPORAL_STAGE'
                    op=row.operator("advlighting.effector_color_remove",icon='REMOVE',text=""); op.target='TEMPORAL_STAGE'

        elif tp == 'NOISE':
            box.label(text="Shape")
            box.prop(sc, "adv_noise_type", text="")
            
            if sc.adv_noise_type == 'WAVE':
                box.prop(sc, "adv_noise_wave_distortion")
            elif sc.adv_noise_type == 'MUSGRAVE':
                row = box.row(align=True)
                row.prop(sc, "adv_noise_musgrave_detail")
                row.prop(sc, "adv_noise_musgrave_roughness")
            
            row = box.row(align=True)
            if sc.adv_noise_scale_linked:
                row.prop(sc, "adv_noise_scale_master", text="Scale")
            else:
                col = row.column(align=True)
                col.prop(sc, "adv_noise_scale_xyz", index=0, text="X")
                col.prop(sc, "adv_noise_scale_xyz", index=1, text="Y")
                col.prop(sc, "adv_noise_scale_xyz", index=2, text="Z")
            row.prop(sc, "adv_noise_scale_linked", icon='LINKED' if sc.adv_noise_scale_linked else 'UNLINKED', text="")
            
            box.prop(sc, "adv_noise_contrast")
            
            box.label(text="Motion & Rotation")
            row = box.row(); col = row.column(align=True)
            col.prop(sc, "adv_noise_direction", index=0, text="Flow X"); col.prop(sc, "adv_noise_direction", index=1, text="Flow Y"); col.prop(sc, "adv_noise_direction", index=2, text="Flow Z")
            col2 = row.column(align=True)
            col2.operator("advlighting.draw_noise_flow", icon='BRUSH_DATA', text="Draw")
            col2.operator("advlighting.align_noise_camera", icon='VIEW_CAMERA', text="Align")
            box.prop(sc, "adv_noise_speed")
            
            row = box.row(); col = row.column(align=True)
            col.prop(sc, "adv_noise_rotation_axis", index=0, text="Rot Axis X"); col.prop(sc, "adv_noise_rotation_axis", index=1, text="Rot Axis Y"); col.prop(sc, "adv_noise_rotation_axis", index=2, text="Rot Axis Z")
            box.prop(sc, "adv_noise_rotation_speed")
            
            # --- Fading ---
            box.label(text="Fading (Frames)")
            row1 = box.row(align=True)
            row1.prop(sc, "adv_noise_fade_in", text="Fade In")
            row1.prop(sc, "adv_noise_fade_in_mode", expand=True)
            
            row2 = box.row(align=True)
            row2.prop(sc, "adv_noise_fade_out", text="Fade Out")
            row2.prop(sc, "adv_noise_fade_out_mode", expand=True)
            
            box.label(text="Colors")
            ng = bpy.data.node_groups.get("AdvLightingNoiseRamp")
            if ng and "Ramp" in ng.nodes: 
                box.template_color_ramp(ng.nodes["Ramp"], "color_ramp")
            else: 
                box.operator("advlighting.create_noise_nodegroup", text="Create Ramp")

        elif tp == 'GOBO':
            box.label(text="Gobo Projection", icon='LIGHT_SPOT')
            
            row = box.row(align=True)
            row.prop(sc, "adv_gobo_image", text="")
            row.operator("advlighting.load_gobo_image", icon='FILEBROWSER', text="")
            
            row = box.row(align=True)
            row.operator("advlighting.spawn_gobo_camera", icon='ADD', text="Spawn Camera")
            row.operator("advlighting.remove_gobo_cameras", icon='TRASH', text="Clear All")
            
            if sc.adv_gobo_camera:
                box.prop(sc, "adv_gobo_camera", text="Active")
                
            box.prop(sc, "adv_gobo_invert")
            
            # --- NEW UI SECTION ---
            box.label(text="Motion & Rotation", icon='DRIVER_TRANSFORM')
            row = box.row(align=True)
            row.prop(sc, "adv_gobo_pos_dir", index=0, text="Dir X")
            row.prop(sc, "adv_gobo_pos_dir", index=1, text="Dir Y")
            
            row = box.row(align=True)
            row.prop(sc, "adv_gobo_pos_speed", text="Pos Speed")
            row.prop(sc, "adv_gobo_pos_mode", text="")
            
            row = box.row(align=True)
            row.prop(sc, "adv_gobo_rot_speed", text="Rot Speed")
            row.prop(sc, "adv_gobo_rot_mode", text="")
            box.separator()
            # ----------------------
            
            box.label(text="Mask to Color Mapping")
            ng = bpy.data.node_groups.get("AdvLightingGoboRamp")
            if ng and "Ramp" in ng.nodes: 
                box.template_color_ramp(ng.nodes["Ramp"], "color_ramp")
            else: 
                box.operator("advlighting.create_gobo_nodegroup", text="Create Ramp")

        elif tp in {'GRADIENT', 'OFFSET'}:
            box.prop(sc, "adv_gradient_mode", text="Mode")
            if sc.adv_gradient_mode == 'CURVE':
                box.prop(sc, "adv_curve_object"); box.prop(sc, "adv_curve_radius"); box.prop(sc, "adv_curve_mode")
            if tp == 'GRADIENT':
                ng = bpy.data.node_groups.get("AdvLightingGradient")
                if ng and "Ramp" in ng.nodes: 
                    box.template_color_ramp(ng.nodes["Ramp"], "color_ramp")
                else: 
                    box.operator("advlighting.create_gradient_nodegroup", text="Create Ramp")
                    
                icon = 'TRIA_DOWN' if sc.adv_show_gradient_palettes else 'TRIA_RIGHT'
                box.prop(sc, "adv_show_gradient_palettes", icon=icon, text="Gradient Library", emboss=False)
                
                if sc.adv_show_gradient_palettes:
                    gbox = box.box()
                    if not sc.adv_gradient_palettes:
                        gbox.operator("advlighting.load_presets", text="Load Defaults", icon='FILE_TICK')
                    else:
                        gbox.template_list("ADVLIGHTING_UL_gradient_palettes", "", sc, "adv_gradient_palettes", sc, "adv_gradient_palettes_index", rows=4)
                        row = gbox.row(align=True)
                        row.operator("advlighting.save_gradient", icon='ADD', text="Save Active")
                        row.operator("advlighting.remove_gradient", icon='REMOVE', text="")
                        png = utils.ensure_gradient_preview_nodegroup()
                        pcol = gbox.column(align=True)
                        pcol.label(text="Preview:")
                        pcol.template_color_ramp(png.nodes["Ramp"], "color_ramp")
                        gbox.operator("advlighting.apply_gradient", icon='CHECKMARK', text="Apply to Active")

                if sc.adv_gradient_mode != 'CURVE': box.operator("advlighting.draw_gradient", icon='BRUSH_DATA', text="Draw Gradient")
            else:
                box.prop(sc, "adv_effector_duration")
                if sc.adv_gradient_mode != 'CURVE': box.operator("advlighting.draw_offset_line", icon='BRUSH_DATA', text="Draw Offset Line")

        if tp=='DOMAIN':
            box.prop(sc,"adv_domain_object"); box.template_list("ADVLIGHTING_UL_effector_colors","",sc,"adv_effector_colors",sc,"adv_effector_colors_index",rows=3)
            row=box.row(align=True); row.operator("advlighting.effector_color_add",icon='ADD',text=""); row.operator("advlighting.effector_color_remove",icon='REMOVE',text="")

        elif tp == 'MOVIE':
            box.label(text="Video Projection", icon='FILE_MOVIE')
            
            row = box.row(align=True)
            row.prop(sc, "adv_movie_clip", text="")
            row.operator("advlighting.load_movie_clip", icon='FILEBROWSER', text="")
            
            row = box.row(align=True)
            row.operator("advlighting.spawn_movie_camera", icon='ADD', text="Spawn Camera")
            row.operator("advlighting.remove_movie_cameras", icon='TRASH', text="Clear All")
            
            if sc.adv_movie_camera:
                box.prop(sc, "adv_movie_camera", text="Active")

        box.operator("advlighting.apply_effectors", text="Apply")

        
        
        # --- FORMATIONS ---
        box = main_col.box()
        box.label(text="Formations & Groups", icon='GROUP')
        
        # Add the two new Mesh Data Export/Import buttons side-by-side
        row = box.row(align=True)
        
        row.operator("advlighting.write_groups_to_mesh", text="Export to Meshes", icon='EXPORT')
        row.operator("advlighting.rebuild_groups_from_mesh", text="Recover Groups", icon='IMPORT')

        box.template_list("ADVLIGHTING_UL_formations", "", sc, "adv_drone_formations", sc, "adv_drone_formations_index", rows=2)
        row = box.row(align=True)
        row.operator("advlighting.formation_add", icon='ADD', text=""); row.operator("advlighting.formation_remove", icon='REMOVE', text="")

        if sc.adv_drone_formations:
            f = sc.adv_drone_formations[sc.adv_drone_formations_index]
            sub = box.box(); sub.label(text=f"Groups in {f.name}")
            sub.template_list("ADVLIGHTING_UL_groups", "", f, "groups", f, "groups_index", rows=2)
            row = sub.row(align=True)
            row.operator("advlighting.group_add", icon='ADD', text=""); row.operator("advlighting.group_remove", icon='REMOVE', text="")

            if f.groups:
                g = f.groups[f.groups_index]
                sub2 = sub.box(); sub2.label(text=f"Drones in {g.name}")
                sub2.template_list("ADVLIGHTING_UL_group_drones", "", g, "drones", g, "drones_index", rows=4)
                row = sub2.row(align=True)
                row.operator("advlighting.group_add_selected", icon='IMPORT', text="Add"); row.operator("advlighting.group_remove_selected", icon='TRASH', text="Remove")
                row = sub2.row(align=True)
                op = row.operator("advlighting.group_select", icon='RESTRICT_SELECT_OFF', text="Select"); op.additive = False
                op = row.operator("advlighting.group_select", icon='ADD', text="+"); op.additive = True

        # JSON Import/Export (For Palettes only now)
        box = main_col.box()
        box.label(text="JSON Palettes", icon='OUTLINER_DATA_GREASEPENCIL')
        row = box.row(align=True)
        row.operator("advlighting.import_palettes", text="Import", icon='IMPORT')
        row.operator("advlighting.export_palettes", text="Export", icon='EXPORT')

classes = (
    ADVLIGHTING_UL_layers, ADVLIGHTING_UL_color_palettes, ADVLIGHTING_UL_gradient_palettes, ADVLIGHTING_UL_effector_colors, 
    ADVLIGHTING_UL_formations, ADVLIGHTING_UL_groups, ADVLIGHTING_UL_group_drones, 
    ADVLIGHTING_UL_temporal_stages, ADVLIGHTING_UL_spark_profiles, ADVLIGHTING_PT_panel,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)