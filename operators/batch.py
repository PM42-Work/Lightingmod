import bpy
import os
import json
from .. import utils

# Define your custom property names
METADATA_SPHERE = "md_sphere"
METADATA_EMPTY = "md_empty"

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
    bl_description = "Export Object Color to JSON (1:1 ID Mapping)"

    def execute(self, context):
        data = {}
        
        # 1. Start with Selected Empties
        selected_empties = [o for o in context.selected_objects]
        if not selected_empties:
            self.report({'ERROR'}, 'Please select the Empties')
            return {'CANCELLED'}
        
        # 2. Build Lookup Table
        prefetch = {}
        all_meshes = [o for o in bpy.data.objects if o.type == 'MESH']
        for obj in all_meshes:
            if METADATA_SPHERE in obj:
                prefetch[obj[METADATA_SPHERE]] = obj

        print(f"--- Exporting Color Transfer ({len(selected_empties)} empties) ---")

        for obj in selected_empties:
            
            # 3. Check for Empty Metadata
            if METADATA_EMPTY not in obj:
                continue

            # 4. Find Drone
            raw_drone_val = obj.get('drone')
            if raw_drone_val is None:
                print(f"Skipping {obj.name}: Missing 'drone' property")
                continue
                
            drone_lookup_name = str(raw_drone_val) + 'S'
            drone = prefetch.get(drone_lookup_name)
            
            if not drone:
                print(f"Skipping {obj.name}: Target drone '{drone_lookup_name}' not found")
                continue

            # 5. Extract Output Key (1:1 Mapping)
            # "1E" -> "1"
            # "25E" -> "25"
            empty_name = str(obj[METADATA_EMPTY]).split('E')[0]

            # 6. Extract Animation Data
            if not drone.animation_data or not drone.animation_data.action:
                continue
            
            action = drone.animation_data.action
            
            fcurves = [fc for fc in action.fcurves if fc.data_path == "color"]
            
            if fcurves:
                unique_frames = set()
                for fc in fcurves:
                    for kp in fc.keyframe_points:
                        unique_frames.add(int(kp.co[0]))
                
                frames_sorted = sorted(list(unique_frames))
                
                for f in frames_sorted:
                    r = 0.0; g = 0.0; b = 0.0
                    for fc in fcurves:
                        val = fc.evaluate(f)
                        if fc.array_index == 0: r = val
                        elif fc.array_index == 1: g = val
                        elif fc.array_index == 2: b = val
                    
                    data.setdefault(empty_name, {})[f] = [r, g, b, 1.0]

        if not data:
            self.report({'WARNING'}, "Export empty. Check System Console.")
            return {'CANCELLED'}

        # Write File
        sc = context.scene
        folder = bpy.path.abspath(sc.export_folder)
        if not os.path.exists(folder):
            self.report({'ERROR'}, f"Export folder not found: {folder}")
            return {'CANCELLED'}
        
        # --- FILENAME LOGIC ---
        filename = sc.export_filename.strip()
        if not filename: filename = "color_transfer"
        if not filename.lower().endswith(".txt"): filename += ".txt"
            
        export_path = os.path.join(folder, filename)
        
        try:
            with open(export_path, "w") as f:
                json.dump(data, f, indent=1)
            self.report({'INFO'}, f"Exported: {export_path}")
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
    LIGHTINGMOD_OT_export_color_transfer,
)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)