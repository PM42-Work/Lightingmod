import bpy
import os
from .. import utils

class LIGHTINGMOD_OT_swap_batch_colors(bpy.types.Operator):
    bl_idname = "lightingmod.swap_batch_colors"
    bl_label  = ""
    def execute(self, context):
        sc=context.scene
        tmp=sc.batch_primary_color[:]
        sc.batch_primary_color=sc.batch_secondary_color
        sc.batch_secondary_color=tmp
        return{'FINISHED'}

class LIGHTINGMOD_OT_batch_color_keyframe(bpy.types.Operator):
    bl_idname="lightingmod.batch_color_keyframe"; bl_label="Color & Keyframe"
    def execute(self, context):
        sc=context.scene; idx=int(sc.batch_target_layer); prop=f"Layer_{idx+1}"
        frame=sc.frame_current; prev={}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type=='MESH' and prop in o.keys():
                prev[o.name]=o[prop][:]
        rgb=list(sc.batch_primary_color)[:3]
        for nm,old in prev.items():
            o=bpy.data.objects[nm]; o[prop]=rgb; o.keyframe_insert(data_path=f'["{prop}"]',frame=frame)
        utils.last_batch_history={'action':'color_keyframe','prop':prop,'values':prev,'frame':frame}
        return{'FINISHED'}

class LIGHTINGMOD_OT_batch_color(bpy.types.Operator):
    bl_idname="lightingmod.batch_color"; bl_label="Color Only"
    def execute(self, context):
        sc=context.scene; idx=int(sc.batch_target_layer); prop=f"Layer_{idx+1}"; prev={}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type=='MESH' and prop in o.keys():
                prev[o.name]=o[prop][:]
        rgb=list(sc.batch_primary_color)[:3]
        for nm in prev: bpy.data.objects[nm][prop]=rgb
        utils.last_batch_history={'action':'color','prop':prop,'values':prev}
        return{'FINISHED'}

class LIGHTINGMOD_OT_keyframe_current(bpy.types.Operator):
    bl_idname="lightingmod.keyframe_current"; bl_label="Keyframe Current"
    def execute(self, context):
        sc=context.scene; idx=int(sc.batch_target_layer); prop=f"Layer_{idx+1}"; frame=sc.frame_current
        utils.last_batch_history={'action':'keyframe','prop':prop,'frame':frame}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type=='MESH' and prop in o.keys():
                o.keyframe_insert(data_path=f'["{prop}"]',frame=frame)
        return{'FINISHED'}

class LIGHTINGMOD_OT_undo_last_edit(bpy.types.Operator):
    bl_idname="lightingmod.undo_last_edit"; bl_label="Undo Last Edit"
    def execute(self, context):
        hist=utils.last_batch_history
        if not hist: return{'CANCELLED'}
        prop=hist['prop']
        if hist['action'] in ('color','color_keyframe'):
            for nm,old in hist['values'].items():
                o=bpy.data.objects.get(nm)
                if o: o[prop]=old
        if hist['action'] in ('color_keyframe','keyframe'):
            frame=hist['frame']
            for o in context.selected_objects:
                if o.get("md_sphere") and o.type=='MESH' and prop in o.keys():
                    o.keyframe_delete(data_path=f'["{prop}"]',frame=frame)
        utils.last_batch_history={}
        return{'FINISHED'}

class LIGHTINGMOD_OT_export_csv_colors(bpy.types.Operator):
    bl_idname="lightingmod.export_csv_colors"; bl_label="Overwrite CSV Colors"
    def execute(self, context):
        sc=context.scene; folder=bpy.path.abspath(sc.export_folder); start=sc.frame_start
        if not utils.baked_colors:
            self.report({'ERROR'}, "No baked colors found. Run 'Bake' first.")
            return {'CANCELLED'}
        for name, frames in utils.baked_colors.items():
            path=os.path.join(folder,f"drone-{name}.csv")
            if not os.path.exists(path): continue
            lines=[l.rstrip('\n') for l in open(path)]
            out=[]
            for idx,line in enumerate(lines):
                cols=line.split('\t')
                f=start+idx
                rgb=frames.get(f)
                if rgb:
                    if len(cols)<7: cols+=['']*(7-len(cols))
                    cols[-3:]=[str(c) for c in rgb]
                out.append('\t'.join(cols))
            with open(path,'w') as f: f.write('\n'.join(out))
        self.report({'INFO'},"CSV colors updated")
        return{'FINISHED'}

classes = (
    LIGHTINGMOD_OT_swap_batch_colors,
    LIGHTINGMOD_OT_batch_color_keyframe,
    LIGHTINGMOD_OT_batch_color,
    LIGHTINGMOD_OT_keyframe_current,
    LIGHTINGMOD_OT_undo_last_edit,
    LIGHTINGMOD_OT_export_csv_colors,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
