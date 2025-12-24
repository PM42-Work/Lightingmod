import bpy
import concurrent.futures
import multiprocessing
import re
from .. import utils

class LIGHTINGMOD_OT_bake_colors(bpy.types.Operator):
    bl_idname = "lightingmod.bake_colors"
    bl_label  = "Bake"

    def execute(self, context):
        sc = context.scene
        start, end = sc.frame_start, sc.frame_end
        frames = list(range(start, end + 1))
        
        utils.baked_colors.clear()
        
        obj_fcurves = {}
        for o in bpy.data.objects:
            if not (o.get("md_sphere") and o.type == 'MESH'):
                continue
            fc_map = {}
            if o.animation_data and o.animation_data.action:
                for fc in o.animation_data.action.fcurves:
                    m = re.match(r'\["Layer_(\d+)"\]', fc.data_path)
                    if m and fc.array_index in {0,1,2}:
                        idx = int(m.group(1))
                        fc_map.setdefault(idx, {})[fc.array_index] = fc
            obj_fcurves[o] = fc_map

        opacity_fcurves = {}
        if sc.animation_data and sc.animation_data.action:
            for fc in sc.animation_data.action.fcurves:
                m = re.match(r'ly_layers\[(\d+)\]\.opacity', fc.data_path)
                if m:
                    opacity_fcurves[int(m.group(1))] = fc
        
        n_objs = len(obj_fcurves)
        wm = context.window_manager
        if n_objs > 0: wm.progress_begin(0, n_objs)

        # We need to capture state to pass to thread (avoid context access in thread)
        ly_layers_data = []
        for l in sc.ly_layers:
            ly_layers_data.append({'mute':l.mute, 'solo':l.solo, 'opacity':l.opacity, 'blend_mode':l.blend_mode})
        
        def bake_for_object(obj_name, fc_map, initial_layer_1):
            baked = {}
            any_solo = any(l['solo'] for l in ly_layers_data)
            
            for f in frames:
                # Base Layer (idx 0 in list, Layer_1 in props)
                base_l = ly_layers_data[0]
                base_enabled = (not base_l['mute']) and (base_l['solo'] or not any_solo)
                
                if base_enabled:
                    col = [
                        fc_map.get(1, {}).get(j).evaluate(f)
                        if fc_map.get(1, {}).get(j) else initial_layer_1[j]
                        for j in range(3)
                    ]
                else:
                    col = [0.0, 0.0, 0.0]

                # Other layers
                for idx, layer_data in enumerate(ly_layers_data[1:], start=2):
                    # Default value if no curve
                    # Since we can't access obj in thread easily if we passed obj_name, 
                    # we assume 0,0,0 if curve missing? Or we should have passed initial values.
                    # Simplified: We rely on fcurves. If no keyframe, it evaluates to 0? 
                    # Actually standard behavior is to hold constant. 
                    # For robust threading we should pre-fetch constants. 
                    # For now, let's assume objects have their props set or fcurves.
                    # Warning: evaluate() on fcurve works, but obj.get() is not thread safe if modifying.
                    # Reading is mostly okay.
                    
                    # To be strictly safe, we passed obj reference in previous script, which works in ThreadPool 
                    # because it is shared memory (GIL prevents true parallel python exec but allows io/C-tasks).
                    # Evaluate is C-side.
                    pass 
            return {} # Placeholder for actual logic below
        
        # Re-implementing the loop cleanly without helper function for clarity in this generator
        # Note: In Blender Python, simple ThreadPool works for API calls like evaluate()
        
        def bake_worker(obj, fc_map):
            baked = {}
            any_solo = any(l.solo for l in sc.ly_layers)
            for f in frames:
                # Base
                if (not sc.ly_layers[0].mute) and (sc.ly_layers[0].solo or not any_solo):
                    col = [
                        fc_map.get(1, {}).get(j).evaluate(f)
                        if fc_map.get(1, {}).get(j) else obj.get("Layer_1", [0,0,0])[j]
                        for j in range(3)
                    ]
                else:
                    col = [0.0, 0.0, 0.0]
                
                # Layers
                for idx, layer in enumerate(sc.ly_layers[1:], start=2):
                    top = [
                        fc_map.get(idx, {}).get(j).evaluate(f)
                        if fc_map.get(idx, {}).get(j) else obj.get(f"Layer_{idx}", [0,0,0])[j]
                        for j in range(3)
                    ]
                    fac = (opacity_fcurves[idx].evaluate(f) if idx in opacity_fcurves else layer.opacity)
                    enabled = (not layer.mute) and (layer.solo or not any_solo)
                    fac = fac * (1.0 if enabled else 0.0)
                    col = utils.blend_colors(col, top, layer.blend_mode, fac)
                baked[f] = tuple(int(c * 255) for c in col)
            return obj.name, baked

        max_workers = min(len(obj_fcurves), multiprocessing.cpu_count())
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(bake_worker, o, fc_map) for o, fc_map in obj_fcurves.items()]
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                name, data = future.result()
                utils.baked_colors[name] = data
                if n_objs > 0: wm.progress_update(i)
        
        if n_objs > 0: wm.progress_end()
        
        # Writing curves
        total = len(frames)
        if total > 0: wm.progress_begin(0, total)
        
        # Pre-clear
        for obj_name in utils.baked_colors:
            o = bpy.data.objects.get(obj_name)
            if not o: continue
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: o.animation_data.action = bpy.data.actions.new(name=f"{obj_name}_color")
            act = o.animation_data.action
            for fc in [fc for fc in act.fcurves if fc.data_path=="color"]:
                act.fcurves.remove(fc)
            
            fcurves = [act.fcurves.new(data_path="color", index=i) for i in range(4)]
            # Add points
            for fc in fcurves: fc.keyframe_points.add(len(frames))
            
            for idx_frame, f in enumerate(frames):
                vals = utils.baked_colors[obj_name][f]
                rgba = (vals[0]/255, vals[1]/255, vals[2]/255, 1.0)
                for idx_fc, fc in enumerate(fcurves):
                    kp = fc.keyframe_points[idx_frame]
                    kp.co = (f, rgba[idx_fc])
            
            for fc in fcurves: fc.update()
            
        if total > 0: wm.progress_end()
        return {'FINISHED'}

classes = (LIGHTINGMOD_OT_bake_colors,)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
