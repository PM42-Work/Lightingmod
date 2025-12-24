import bpy
from . import utils

class LIGHTINGMOD_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=f"{index+1}: {item.name}")
        solo_icon = 'RADIOBUT_ON' if item.solo else 'RADIOBUT_OFF'
        row.operator("lightingmod.layer_toggle_solo", text="", icon=solo_icon).index = index
        mute_icon = 'MUTE_IPO_ON' if item.mute else 'MUTE_IPO_OFF'
        row.operator("lightingmod.layer_toggle_mute", text="", icon=mute_icon).index = index

class LIGHTINGMOD_UL_effector_colors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "color", text="", emboss=True)

# --- NEW UI LISTS ---
class LIGHTINGMOD_UL_formations(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='OUTLINER_COLLECTION')

class LIGHTINGMOD_UL_groups(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='GROUP')

class LIGHTINGMOD_UL_group_drones(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.object_name, icon='MESH_UVSPHERE')

class LIGHTINGMOD_UL_temporal_stages(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "name", text="", emboss=False, icon='TIME')


class LIGHTINGMOD_PT_panel(bpy.types.Panel):
    bl_label="Advanced Lighting"; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category="Advanced Lighting"

    def draw(self, context):
        sc=context.scene; obj=context.object; L=sc.ly_layers; idx=L and sc.ly_layers_index
        layout=self.layout

        # Layers
        box=layout.box(); box.label(text="Layers")
        row=box.row(align=True)
        row.operator("lightingmod.layer_add",icon='ADD',text="")
        row.operator("lightingmod.layer_remove",icon='REMOVE',text="")
        row.operator("lightingmod.bake_colors",icon='RENDER_STILL',text="Bake")
        box.template_list("LIGHTINGMOD_UL_layers","",sc,"ly_layers",sc,"ly_layers_index",rows=3)
        if L:
            itm=L[idx]; box.prop(itm,"name",text=("Base Layer" if idx==0 else "Layer"))
            if idx>0: box.prop(itm,"blend_mode"); box.prop(itm,"opacity")
            key=f"Layer_{idx+1}"
            if obj and key in obj.keys(): box.prop(obj,key,text="Layer Value")

        # Batch Color
        box=layout.box(); box.label(text="Batch Color")
        box.prop(sc,"batch_target_layer",text="Target Layer")
        row=box.row(align=True)
        row.prop(sc,"batch_primary_color",text="")
        row.operator("lightingmod.swap_batch_colors",icon='FILE_REFRESH',text="")
        row.prop(sc,"batch_secondary_color",text="")
        col=box.column(align=True)
        col.operator("lightingmod.batch_color_keyframe",text="Color & Keyframe")
        col.operator("lightingmod.batch_color",       text="Color Only")
        col.operator("lightingmod.keyframe_current",  text="Keyframe Current")
        col.operator("lightingmod.undo_last_edit",    text="Undo Last Edit")

        # Effectors
        box=layout.box(); box.label(text="Effectors")
        box.prop(sc,"effector_target_layer",text="Target Layer")
        box.prop(sc,"effector_type",       text="Type")
        box.prop(sc,"effector_selection_mode", text="Apply To")

        tp = sc.effector_type
        if tp not in {'GRADIENT','OFFSET'}:
            row=box.row(align=True)
            row.prop(sc,"effector_start",text="Start")
            row.prop(sc,"effector_end",  text="End")
            row=box.row(align=True)
            row.operator("lightingmod.set_start_frame",icon='PREV_KEYFRAME',text="")
            row.operator("lightingmod.set_end_frame",  icon='NEXT_KEYFRAME',text="")

        if tp=='SPARKLE':
            box.prop(sc,"effector_transition",text="Transition")
            box.prop(sc,"effector_influence",text="Influence")
            box.template_list("LIGHTINGMOD_UL_effector_colors","",sc,"effector_colors",sc,"effector_colors_index",rows=3)
            row=box.row(align=True)
            row.operator("lightingmod.effector_color_add",icon='ADD',text=""); row.operator("lightingmod.effector_color_remove",icon='REMOVE',text="")
            box.operator("lightingmod.effector_monochrome",text="Monochrome")

        elif tp=='TEMPORAL_SPARKLE':
            box.label(text="Temporal Stages")
            box.template_list("LIGHTINGMOD_UL_temporal_stages", "", sc, "temporal_stages", sc, "temporal_stages_index", rows=2)
            row = box.row(align=True)
            row.operator("lightingmod.stage_add", icon='ADD', text=""); row.operator("lightingmod.stage_remove", icon='REMOVE', text="")
            if sc.temporal_stages:
                stage = sc.temporal_stages[sc.temporal_stages_index]
                box.prop(stage, "transition"); box.prop(stage, "influence")
                box.template_list("LIGHTINGMOD_UL_effector_colors", "", stage, "colors", stage, "colors_index", rows=3)
                row=box.row(align=True)
                op=row.operator("lightingmod.effector_color_add",icon='ADD',text=""); op.target='TEMPORAL_STAGE'
                op=row.operator("lightingmod.effector_color_remove",icon='REMOVE',text=""); op.target='TEMPORAL_STAGE'

        elif tp in {'GRADIENT', 'OFFSET'}:
            box.prop(sc, "gradient_mode", text="Mode")
            
            if sc.gradient_mode == 'CURVE':
                box.prop(sc, "curve_object"); box.prop(sc, "curve_radius"); box.prop(sc, "curve_mode")
            
            if tp == 'GRADIENT':
                ng = bpy.data.node_groups.get("LightingModGradient")
                if ng and "Ramp" in ng.nodes: box.template_color_ramp(ng.nodes["Ramp"], "color_ramp")
                else: box.operator("lightingmod.create_gradient_nodegroup", text="Create Ramp")
                if sc.gradient_mode != 'CURVE': box.operator("lightingmod.draw_gradient", icon='BRUSH_DATA', text="Draw Gradient")
            else:
                box.prop(sc, "effector_duration")
                if sc.gradient_mode != 'CURVE': box.operator("lightingmod.draw_offset_line", icon='BRUSH_DATA', text="Draw Offset Line")

        if tp=='DOMAIN':
            box.prop(sc,"domain_object"); box.template_list("LIGHTINGMOD_UL_effector_colors","",sc,"effector_colors",sc,"effector_colors_index",rows=3)
            row=box.row(align=True); row.operator("lightingmod.effector_color_add",icon='ADD',text=""); row.operator("lightingmod.effector_color_remove",icon='REMOVE',text="")

        elif tp=='MOVIE':
            box.prop(sc,"image_texture"); box.prop(sc,"new_uv_map_name")
            box.operator("lightingmod.generate_uv",icon='GROUP_UVS'); box.prop(sc,"movie_uv_map"); box.prop(sc,"movie_step")

        box.operator("lightingmod.apply_effectors", text="Apply")


class LIGHTINGMOD_PT_drone_groups(bpy.types.Panel):
    bl_label="Formations & Groups"; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category="Advanced Lighting"
    
    def draw(self, context):
        sc = context.scene; layout = self.layout
        
        # Formations
        layout.label(text="Formations")
        layout.template_list("LIGHTINGMOD_UL_formations", "", sc, "drone_formations", sc, "drone_formations_index", rows=2)
        row = layout.row(align=True)
        row.operator("lightingmod.formation_add", icon='ADD', text=""); row.operator("lightingmod.formation_remove", icon='REMOVE', text="")

        if sc.drone_formations:
            f = sc.drone_formations[sc.drone_formations_index]
            box = layout.box(); box.label(text=f"Groups in {f.name}")
            box.template_list("LIGHTINGMOD_UL_groups", "", f, "groups", f, "groups_index", rows=2)
            row = box.row(align=True)
            row.operator("lightingmod.group_add", icon='ADD', text=""); row.operator("lightingmod.group_remove", icon='REMOVE', text="")

            if f.groups:
                g = f.groups[f.groups_index]
                sub = box.box(); sub.label(text=f"Drones in {g.name}")
                sub.template_list("LIGHTINGMOD_UL_group_drones", "", g, "drones", g, "drones_index", rows=4)
                
                row = sub.row(align=True)
                row.operator("lightingmod.group_add_selected", icon='IMPORT', text="Add"); row.operator("lightingmod.group_remove_selected", icon='TRASH', text="Remove")
                
                row = sub.row(align=True)
                op = row.operator("lightingmod.group_select", icon='RESTRICT_SELECT_OFF', text="Select"); op.additive = False
                op = row.operator("lightingmod.group_select", icon='ADD', text="+"); op.additive = True

class LIGHTINGMOD_PT_export(bpy.types.Panel):
    bl_label="Export Colors"; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category="Advanced Lighting"
    def draw(self, context):
        sc=context.scene; layout=self.layout
        layout.prop(sc,"export_folder",text="CSV Folder")
        layout.operator("lightingmod.export_csv_colors",text="Overwrite CSV Colors")

classes = (
    LIGHTINGMOD_UL_layers, LIGHTINGMOD_UL_effector_colors,
    LIGHTINGMOD_UL_formations, LIGHTINGMOD_UL_groups, LIGHTINGMOD_UL_group_drones, LIGHTINGMOD_UL_temporal_stages,
    LIGHTINGMOD_PT_panel, LIGHTINGMOD_PT_drone_groups, LIGHTINGMOD_PT_export,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)