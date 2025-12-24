import bpy
from . import utils

class LIGHTINGMOD_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=f"{index+1}: {item.name}")
        solo_icon = 'RADIOBUT_ON' if item.solo else 'RADIOBUT_OFF'
        op = row.operator("lightingmod.layer_toggle_solo", text="", icon=solo_icon)
        op.index = index
        mute_icon = 'MUTE_IPO_ON' if item.mute else 'MUTE_IPO_OFF'
        op = row.operator("lightingmod.layer_toggle_mute", text="", icon=mute_icon)
        op.index = index

class LIGHTINGMOD_UL_effector_colors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "color", text="", emboss=True)

class LIGHTINGMOD_PT_panel(bpy.types.Panel):
    bl_label="Advanced Lighting"
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category="Advanced Lighting"

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
            if idx>0:
                box.prop(itm,"blend_mode",text="Blend Mode")
                box.prop(itm,"opacity",  text="Influence")
            key=f"Layer_{idx+1}"
            if obj and key in obj.keys():
                box.prop(obj,key,text="Layer Value")

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

        tp = sc.effector_type
        if tp not in {'GRADIENT','OFFSET'}:
            row=box.row(align=True)
            row.prop(sc,"effector_start",text="Start")
            row.prop(sc,"effector_end",  text="End")
            row=box.row(align=True)
            row.operator("lightingmod.set_start_frame",icon='PREV_KEYFRAME',text="")
            row.operator("lightingmod.set_end_frame",  icon='NEXT_KEYFRAME',text="")

        if tp not in {'MOVIE','GRADIENT','OFFSET'}:
            box.prop(sc,"effector_transition",text="Transition Frames")

        if tp == 'GRADIENT':
            box.prop(sc, "gradient_mode", text="Mode")
            ng = bpy.data.node_groups.get("LightingModGradient")
            if ng and "Ramp" in ng.nodes:
                ramp_node = ng.nodes["Ramp"]
                box.template_color_ramp(ramp_node, "color_ramp")
            else:
                box.label(text="Gradient ramp missing!")
                box.operator("lightingmod.create_gradient_nodegroup", text="Create Gradient Ramp")
            box.operator("lightingmod.draw_gradient", icon='BRUSH_DATA', text="Draw Gradient")

        elif tp=='SPARKLE':
            box.prop(sc,"effector_influence",text="Influence")
            box.prop(sc,"effector_selected_only",text="Selected Only")

        elif tp=='DOMAIN':
            box.prop(sc,"domain_object",text="Domain Object")
            box.prop(sc,"effector_selected_only",text="Selected Only")

        elif tp=='MOVIE':
            box.prop(sc,"image_texture",   text="Image Texture")
            box.prop(sc,"new_uv_map_name", text="New UV Map Name")
            box.operator("lightingmod.generate_uv",icon='GROUP_UVS',text="Generate UV Map")
            box.prop(sc,"movie_uv_map",    text="UV Map")
            box.prop(sc,"movie_step",      text="Frame Step")

        elif tp=='OFFSET':
            box.prop(sc, "gradient_mode", text="Mode")
            box.prop(sc,"effector_duration",text="Effect Duration")
            box.operator("lightingmod.draw_offset_line",icon='BRUSH_DATA',text="Draw Offset Line")

        if tp in {'SPARKLE','DOMAIN'}:
            box.template_list("LIGHTINGMOD_UL_effector_colors","",
                              sc,"effector_colors",sc,"effector_colors_index",rows=3)
            row=box.row(align=True)
            row.operator("lightingmod.effector_color_add",   icon='ADD',    text="")
            row.operator("lightingmod.effector_color_remove",icon='REMOVE', text="")
            box.operator("lightingmod.effector_monochrome",  text="Monochrome")

        box.operator("lightingmod.apply_effectors", text="Apply")

class LIGHTINGMOD_PT_export(bpy.types.Panel):
    bl_label="Export Colors"
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category="Advanced Lighting"
    
    def draw(self, context):
        sc=context.scene; layout=self.layout
        layout.prop(sc,"export_folder",text="CSV Folder")
        layout.operator("lightingmod.export_csv_colors",text="Overwrite CSV Colors")

classes = (
    LIGHTINGMOD_UL_layers,
    LIGHTINGMOD_UL_effector_colors,
    LIGHTINGMOD_PT_panel,
    LIGHTINGMOD_PT_export,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
