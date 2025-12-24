import bpy
import os
import json
from .. import utils

class LIGHTINGMOD_OT_swap_batch_colors(bpy.types.Operator):
    bl_idname = "lightingmod.swap_batch_colors"
    bl_label  = ""
    def execute(self, context):
        sc = context.scene
        tmp = sc.batch_primary_color[:]
        sc.batch_primary_color = sc.batch_secondary_color
        sc.batch_secondary_color = tmp
        return {'FINISHED'}

class LIGHTINGMOD_OT_batch_color_keyframe(bpy.types.Operator):
    bl_idname = "lightingmod.batch_color_keyframe"
    bl_label  = "Color & Keyframe"
    def execute(self, context):
        sc = context.scene; idx = int(sc.batch_target_layer); prop = f"Layer_{idx+1}"
        frame = sc.frame_current; prev = {}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                prev[o.name] = o[prop][:]
        rgb = list(sc.batch_primary_color)[:3]
        for nm, old in prev.items():
            o = bpy.data.objects[nm]; o[prop] = rgb; o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
        utils.last_batch_history = {'action': 'color_keyframe', 'prop': prop, 'values': prev, 'frame': frame}
        return {'FINISHED'}

class LIGHTINGMOD_OT_batch_color(bpy.types.Operator):
    bl_idname = "lightingmod.batch_color"
    bl_label  = "Color Only"
    def execute(self, context):
        sc = context.scene; idx = int(sc.batch_target_layer); prop = f"Layer_{idx+1}"; prev = {}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                prev[o.name] = o[prop][:]
        rgb = list(sc.batch_primary_color)[:3]
        for nm in prev: bpy.data.objects[nm][prop] = rgb
        utils.last_batch_history = {'action': 'color', 'prop': prop, 'values': prev}
        return {'FINISHED'}

class LIGHTINGMOD_OT_keyframe_current(bpy.types.Operator):
    bl_idname = "lightingmod.keyframe_current"
    bl_label  = "Keyframe Current"
    def execute(self, context):
        sc = context.scene; idx = int(sc.batch_target_layer); prop = f"Layer_{idx+1}"; frame = sc.frame_current
        utils.last_batch_history = {'action': 'keyframe', 'prop': prop, 'frame': frame}
        for o in context.selected_objects:
            if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                o.keyframe_insert(data_path=f'["{prop}"]', frame=frame)
        return {'FINISHED'}

class LIGHTINGMOD_OT_undo_last_edit(bpy.types.Operator):
    bl_idname = "lightingmod.undo_last_edit"
    bl_label  = "Undo Last Edit"
    def execute(self, context):
        hist = utils.last_batch_history
        if not hist: return {'CANCELLED'}
        prop = hist['prop']
        if hist['action'] in ('color', 'color_keyframe'):
            for nm, old in hist['values'].items():
                o = bpy.data.objects.get(nm)
                if o: o[prop] = old
        if hist['action'] in ('color_keyframe', 'keyframe'):
            frame = hist['frame']
            for o in context.selected_objects:
                if o.get("md_sphere") and o.type == 'MESH' and prop in o.keys():
                    o.keyframe_delete(data_path=f'["{prop}"]', frame=frame)
        utils.last_batch_history = {}
        return {'FINISHED'}

class LIGHTINGMOD_OT_export_csv_colors(bpy.types.Operator):
    bl_idname = "lightingmod.export_csv_colors"
    bl_label  = "Overwrite CSV Colors"
    def execute(self, context):
        sc = context.scene; folder = bpy.path.abspath(sc.export_folder); start = sc.frame_start
        if not utils.baked_colors:
            self.report({'ERROR'}, "No baked colors found. Run 'Bake' first.")
            return {'CANCELLED'}
        
        for name, color_list in utils.baked_colors.items():
            path = os.path.join(folder, f"drone-{name}.csv")
            if not os.path.exists(path): continue
            
            lines = [l.rstrip('\n') for l in open(path)]
            out = []
            for idx, line in enumerate(lines):
                cols = line.split('\t')
                f = start + idx
                
                # Safe List Access (New Baking format is a List)
                if 0 <= idx < len(color_list):
                    rgb = color_list[idx]
                    if len(cols) < 7: cols += [''] * (7 - len(cols))
                    cols[-3:] = [str(c) for c in rgb]
                
                out.append('\t'.join(cols))
            
            with open(path, 'w') as f: f.write('\n'.join(out))
            
        self.report({'INFO'}, "CSV colors updated")
        return {'FINISHED'}

class LIGHTINGMOD_OT_export_color_transfer(bpy.types.Operator):
    bl_idname = "lightingmod.export_color_transfer"
    bl_label  = "Export Colour Transfer"
    bl_description = "Export F-Curve colors to JSON (Color Transfer format)"

    def execute(self, context):
        sc = context.scene
        folder = bpy.path.abspath(sc.export_folder)
        
        if not os.path.exists(folder):
            self.report({'ERROR'}, f"Export folder not found: {folder}")
            return {'CANCELLED'}

        # We export based on Objects, not the bake cache, 
        # because F-Curves contain the optimized (RDP) sparse keyframes.
        
        # Identify Drones
        objs = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects

        drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH']
        if not drones:
            self.report({'WARNING'}, "No drones selected to export")
            return {'CANCELLED'}

        data = {}
        
        for obj in drones:
            # 1. Determine ID (Try md_empty "1E" format, else Object Name)
            # Matches behavior of old Color_Transfer.py
            drone_id = obj.name
            if "md_empty" in obj:
                # e.g. "1E" -> "1"
                raw = obj["md_empty"]
                if isinstance(raw, str) and 'E' in raw:
                    drone_id = raw.split('E')[0]
                else:
                    drone_id = str(raw)
            
            # 2. Get Animation Data
            if not obj.animation_data or not obj.animation_data.action:
                continue
                
            action = obj.animation_data.action
            # Find the "color" curves created by our Baker
            fcurves = [fc for fc in action.fcurves if fc.data_path == "color" and fc.array_index < 3]
            
            if not fcurves: continue
            
            # 3. Find all unique keyframe times across R,G,B
            # (RDP might have removed keys at different times for different channels)
            frames = set()
            for fc in fcurves:
                for kp in fc.keyframe_points:
                    frames.add(int(kp.co[0]))
            
            sorted_frames = sorted(list(frames))
            
            drone_entry = {}
            for f in sorted_frames:
                # Evaluate all channels at this frame to ensure sync
                # .evaluate() handles interpolation between disparate keys
                r = action.fcurves.find("color", index=0).evaluate(f)
                g = action.fcurves.find("color", index=1).evaluate(f)
                b = action.fcurves.find("color", index=2).evaluate(f)
                
                # Format: [r, g, b, a]
                # JSON keys must be strings
                drone_entry[str(f)] = [r, g, b, 1.0]
                
            data[drone_id] = drone_entry

        # Write to file
        out_path = os.path.join(folder, "color_transfer.txt")
        try:
            with open(out_path, 'w') as f:
                json.dump(data, f, indent=1)
            self.report({'INFO'}, f"Exported: {out_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Write Error: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

classes = (
    LIGHTINGMOD_OT_swap_batch_colors,
    LIGHTINGMOD_OT_batch_color_keyframe,
    LIGHTINGMOD_OT_batch_color,
    LIGHTINGMOD_OT_keyframe_current,
    LIGHTINGMOD_OT_undo_last_edit,
    LIGHTINGMOD_OT_export_csv_colors,
    LIGHTINGMOD_OT_export_color_transfer, # <--- Registered
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)