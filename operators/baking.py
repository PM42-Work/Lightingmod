import bpy
import concurrent.futures
import multiprocessing
import numpy as np
import re
from .. import utils
from bpy.props import FloatProperty

# --- CLOCK OPERATORS ---
class ADVLIGHTING_OT_set_bake_start(bpy.types.Operator):
    bl_idname="advlighting.set_bake_start"; bl_label=""
    def execute(self, context):
        context.scene.adv_bake_start = context.scene.frame_current
        return{'FINISHED'}

class ADVLIGHTING_OT_set_bake_end(bpy.types.Operator):
    bl_idname="advlighting.set_bake_end"; bl_label=""
    def execute(self, context):
        context.scene.adv_bake_end = context.scene.frame_current
        return{'FINISHED'}

# --- COLOR BAKING OPERATOR (VECTORIZED ENGINE) ---
class ADVLIGHTING_OT_bake_colors(bpy.types.Operator):
    bl_idname = "advlighting.bake_colors"
    bl_label  = "Bake Colors"
    bl_description = "Ultra-fast Vectorized color baking engine with safe timeline splicing"
    bl_options = {'REGISTER', 'UNDO'}
    
    tolerance: FloatProperty(name="Tolerance", default=0.02, min=0.0, max=1.0)

    def execute(self, context):
        sc = context.scene
        start, end = sc.adv_bake_start, sc.adv_bake_end
        frames = list(range(start, end + 1))
        num_frames = len(frames)
        utils.baked_colors.clear()
        
        # 1. Pre-Cache Phase
        obj_fcurves = {}
        for o in bpy.data.objects:
            if not (o.get("md_sphere") and o.type == 'MESH'): continue
            fc_map = {}
            if o.animation_data and o.animation_data.action:
                for fc in o.animation_data.action.fcurves:
                    m = re.match(r'\["Layer_(\d+)"\]', fc.data_path)
                    if m and fc.array_index in {0,1,2}:
                        fc_map.setdefault(int(m.group(1)), {})[fc.array_index] = fc
            
            initial_vals = {}
            for i, layer in enumerate(sc.adv_layers):
                val = o.get(f"Layer_{i+1}", [0.0, 0.0, 0.0])
                try:
                    lst = list(val)
                    initial_vals[i+1] = (lst + [0.0]*3)[:3]
                except TypeError:
                    initial_vals[i+1] = [float(val)] * 3
            obj_fcurves[o.name] = {'fc_map': fc_map, 'initials': initial_vals}

        opacity_fcurves = {}
        if sc.animation_data and sc.animation_data.action:
            for fc in sc.animation_data.action.fcurves:
                m = re.match(r'adv_layers\[(\d+)\]\.opacity', fc.data_path)
                if m: opacity_fcurves[int(m.group(1))] = fc

        layer_configs = []
        for i, layer in enumerate(sc.adv_layers):
            ops = [opacity_fcurves[i].evaluate(f) for f in frames] if i in opacity_fcurves else [layer.opacity] * num_frames
            layer_configs.append({'idx': i, 'mute': layer.mute, 'solo': layer.solo, 'blend': layer.blend_mode, 'opacities': ops})

        any_solo = any(l['solo'] for l in layer_configs)

        # 2. Vectorized Math Worker
        def bake_worker(obj_name, data_pack):
            fc_map, initials = data_pack['fc_map'], data_pack['initials']
            
            def get_layer_data(lnum):
                data = np.zeros((num_frames, 3), dtype=np.float32)
                for ch in range(3):
                    if lnum in fc_map and ch in fc_map[lnum]:
                        data[:, ch] = [fc_map[lnum][ch].evaluate(f) for f in frames]
                    else:
                        data[:, ch] = initials[lnum][ch]
                return data
                
            if not layer_configs:
                return obj_name, np.zeros((num_frames, 3), dtype=np.float32)
                
            l0 = layer_configs[0]
            enabled0 = (not l0['mute']) and (l0['solo'] or not any_solo)
            if enabled0:
                base_col = get_layer_data(1)
            else:
                base_col = np.zeros((num_frames, 3), dtype=np.float32)

            for l_cfg in layer_configs[1:]:
                if not ((not l_cfg['mute']) and (l_cfg['solo'] or not any_solo)): continue
                
                fac = np.array(l_cfg['opacities'], dtype=np.float32)
                if np.max(fac) <= 0.0001: continue
                
                top_col = get_layer_data(l_cfg['idx'] + 1)
                
                b = np.clip(base_col, 0.0, 1.0)
                t = np.clip(top_col, 0.0, 1.0)
                fac_expanded = fac[:, np.newaxis]
                mode = l_cfg['blend']
                
                if mode == 'REPLACE':
                    alpha = np.clip(np.max(t, axis=1, keepdims=True), 0.0, 1.0)
                    out = b * (1.0 - alpha) + t * alpha
                elif mode == 'ADD':      out = np.clip(b + t, 0.0, 1.0)
                elif mode == 'SUBTRACT': out = np.clip(b - t, 0.0, 1.0)
                elif mode == 'MULTIPLY': out = b * t
                elif mode == 'LIGHTEN':  out = np.maximum(b, t)
                elif mode == 'DARKEN':   out = np.minimum(b, t)
                elif mode == 'SCREEN':   out = 1.0 - (1.0 - b) * (1.0 - t)
                else:                    out = t
                
                base_col = b * (1.0 - fac_expanded) + out * fac_expanded
            
            return obj_name, np.clip(base_col, 0.0, 1.0)

        # 3. Multithreading Dispatch
        wm = context.window_manager
        wm.progress_begin(0, len(obj_fcurves))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(1, len(obj_fcurves)), multiprocessing.cpu_count())) as executor:
            futures = [executor.submit(bake_worker, name, data) for name, data in obj_fcurves.items()]
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                name, data = future.result()
                utils.baked_colors[name] = data
                if i % 10 == 0: wm.progress_update(i)
        wm.progress_end()
        
        # 4. RDP & Splicing 
        wm.progress_begin(0, len(utils.baked_colors))
        frames_arr = np.array(frames, dtype=np.float32)
        
        for i, (obj_name, col_arr) in enumerate(utils.baked_colors.items()):
            o = bpy.data.objects.get(obj_name)
            if not o: continue
            
            if "md_layer_1" not in o: o["md_layer_1"] = [0.0, 0.0, 0.0, 1.0]
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: o.animation_data.action = bpy.data.actions.new(name=f"{obj_name}_color")
            action = o.animation_data.action
                
            if self.tolerance > 0.0:
                critical_idx = utils.find_critical_indices(col_arr)
                final_f_list, final_v_list = [], []
                for k in range(len(critical_idx) - 1):
                    start_i, end_i = critical_idx[k], critical_idx[k+1]
                    sf, sv = utils.rdp_simplify(frames_arr[start_i:end_i+1], col_arr[start_i:end_i+1], self.tolerance)
                    if k > 0:
                        final_f_list.extend(sf[1:])
                        final_v_list.append(sv[1:])
                    else:
                        final_f_list.extend(sf)
                        final_v_list.append(sv)
                final_frames = np.array(final_f_list) if final_v_list else frames_arr
                final_vals = np.vstack(final_v_list) if final_v_list else col_arr
            else:
                final_frames, final_vals = frames_arr, col_arr
            
            for target_path in ['["md_layer_1"]', 'color']:
                for channel in range(3):
                    fc = action.fcurves.find(data_path=target_path, index=channel)
                    if not fc: 
                        fc = action.fcurves.new(data_path=target_path, index=channel)
                        existing_pts = np.empty((0, 2), dtype=np.float32)
                    else:
                        num_existing = len(fc.keyframe_points)
                        if num_existing > 0:
                            coords = np.zeros(num_existing * 2, dtype=np.float32)
                            fc.keyframe_points.foreach_get('co', coords)
                            existing_pts = coords.reshape((num_existing, 2))
                            
                            mask = (existing_pts[:, 0] < start) | (existing_pts[:, 0] > end)
                            existing_pts = existing_pts[mask]
                        else:
                            existing_pts = np.empty((0, 2), dtype=np.float32)
                    
                    new_pts = np.column_stack((final_frames, final_vals[:, channel]))
                    combined_pts = np.vstack((existing_pts, new_pts))
                    combined_pts = combined_pts[combined_pts[:, 0].argsort()]
                    
                    fc.keyframe_points.clear() 
                    num_points = len(combined_pts)
                    fc.keyframe_points.add(num_points)
                    fc.keyframe_points.foreach_set('co', combined_pts.flatten())
                    fc.update()
                
            if i % 50 == 0: wm.progress_update(i)

        wm.progress_end()
        self.report({'INFO'}, "Master Mix baked to md_layer_1 & Viewport Color")
        return {'FINISHED'}


# --- SMART BOUNDS POSITION BAKING ---
class ADVLIGHTING_OT_bake_positions(bpy.types.Operator):
    bl_idname = "advlighting.bake_positions"
    bl_label  = "Bake Positions"
    bl_description = "Calculates absolute flight paths into 'Absolute_Position'"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        drones = [o for o in bpy.data.objects if o.get("md_sphere") and o.type=='MESH']
        if not drones: return {'CANCELLED'}

        prop_name = "Absolute_Position" 
        data_path = f'["{prop_name}"]'

        drone_configs = []
        for d in drones:
            if prop_name not in d:
                d[prop_name] = [0.0, 0.0, 0.0]
                ui = d.id_properties_ui(prop_name)
                ui.update(subtype='TRANSLATION')
            
            cons = sorted([c for c in d.constraints if c.type == 'COPY_LOCATION' and c.name.lower().startswith('copy done')], key=lambda c: c.name)
            drone_configs.append((d, cons))

        frames_to_bake = set(range(sc.adv_bake_start, sc.adv_bake_end + 1))
        for d in drones:
            if d.animation_data and d.animation_data.action:
                for fc in d.animation_data.action.fcurves:
                    if 'constraints' in fc.data_path:
                        for kp in fc.keyframe_points:
                            frames_to_bake.add(int(kp.co[0]))
                            
        sorted_frames = sorted(list(frames_to_bake))[::5]
        sampled_data = {d.name: [] for d in drones}

        wm = context.window_manager
        wm.progress_begin(0, len(sorted_frames))

        for p_idx, f in enumerate(sorted_frames):
            sc.frame_set(f)
            for d, cons in drone_configs:
                active_idxs = [i for i, c in enumerate(cons) if getattr(c, "influence", 0.0) > 1e-6]

                if not active_idxs:
                    p = d.matrix_world.translation
                    sampled_data[d.name].append((f, p.x, p.y, p.z))
                    continue

                curr_idx = max(active_idxs)
                c_curr = cons[curr_idx]
                inf_curr = getattr(c_curr, "influence", 0.0)

                if inf_curr >= 1.0 - 1e-6:
                    tgt = getattr(c_curr, "target", None)
                    p = d.matrix_world.translation 
                    
                    if tgt and tgt.type == 'EMPTY':
                        if tgt.parent and tgt.parent_type == 'VERTEX' and tgt.parent.type == 'MESH':
                            v_idx = tgt.parent_vertices[0]
                            v_local_co = tgt.parent.data.vertices[v_idx].co
                            p = tgt.parent.matrix_world @ v_local_co
                        else:
                            p = tgt.matrix_world.translation
                            
                    sampled_data[d.name].append((f, p.x, p.y, p.z))

            if p_idx % 10 == 0: wm.progress_update(p_idx)

        for d_name, data in sampled_data.items():
            if not data: continue
            d = bpy.data.objects.get(d_name)
            
            if not d.animation_data: d.animation_data_create()
            if not d.animation_data.action: d.animation_data.action = bpy.data.actions.new(name=f"{d.name}Action")
            act = d.animation_data.action
            
            data_np = np.array(data, dtype=np.float32)
            frames_arr = data_np[:, 0]
            
            for i in range(3):
                fc = act.fcurves.find(data_path=data_path, index=i)
                if not fc: fc = act.fcurves.new(data_path=data_path, index=i)
                fc.keyframe_points.clear()
                
                pts = np.column_stack((frames_arr, data_np[:, i+1]))
                fc.keyframe_points.add(len(pts))
                fc.keyframe_points.foreach_set('co', pts.flatten())
                
                bool_arr = [False] * len(pts)
                fc.keyframe_points.foreach_set('select_control_point', bool_arr)
                fc.keyframe_points.foreach_set('select_left_handle', bool_arr)
                fc.keyframe_points.foreach_set('select_right_handle', bool_arr)

                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
                    
                fc.update()

        wm.progress_end()
        self.report({'INFO'}, "Smart Linear Positions Baked Successfully!")
        return {'FINISHED'}


classes = (
    ADVLIGHTING_OT_set_bake_start, 
    ADVLIGHTING_OT_set_bake_end,
    ADVLIGHTING_OT_bake_colors, 
    ADVLIGHTING_OT_bake_positions
)

def register():
    for cls in classes: bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)