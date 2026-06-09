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

# --- COLOR BAKING OPERATOR ---
class ADVLIGHTING_OT_bake_colors(bpy.types.Operator):
    bl_idname = "advlighting.bake_colors"
    bl_label  = "Bake Colors"
    bl_description = "Calculates all layers and bakes the final mix directly to md_layer_1"
    bl_options = {'REGISTER', 'UNDO'}
    
    tolerance: FloatProperty(name="Tolerance", default=0.02, min=0.0, max=1.0)

    def execute(self, context):
        sc = context.scene
        start, end = sc.adv_bake_start, sc.adv_bake_end
        frames = list(range(start, end + 1))
        utils.baked_colors.clear()
        
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
            ops = [opacity_fcurves[i].evaluate(f) for f in frames] if i in opacity_fcurves else [layer.opacity] * len(frames)
            layer_configs.append({'idx': i, 'mute': layer.mute, 'solo': layer.solo, 'blend': layer.blend_mode, 'opacities': ops})

        any_solo = any(l['solo'] for l in layer_configs)

        def bake_worker(obj_name, data_pack):
            final_colors = []
            fc_map, initials = data_pack['fc_map'], data_pack['initials']
            
            for f_idx, f in enumerate(frames):
                if not layer_configs:
                    final_colors.append((0,0,0))
                    continue
                
                l0 = layer_configs[0]
                enabled0 = (not l0['mute']) and (l0['solo'] or not any_solo)
                base_col = [fc_map[1][ch].evaluate(f) if (1 in fc_map and ch in fc_map[1]) else initials[1][ch] for ch in range(3)] if enabled0 else [0.0]*3

                for l_cfg in layer_configs[1:]:
                    if not ((not l_cfg['mute']) and (l_cfg['solo'] or not any_solo)): continue
                    fac = l_cfg['opacities'][f_idx]
                    if fac <= 0.0001: continue
                    
                    lnum = l_cfg['idx'] + 1
                    top = [fc_map[lnum][ch].evaluate(f) if (lnum in fc_map and ch in fc_map[lnum]) else initials[lnum][ch] for ch in range(3)]
                    base_col = utils.blend_colors(base_col, top, l_cfg['blend'], fac)
                
                final_colors.append(tuple(int(c * 255) for c in base_col))
            return obj_name, final_colors

        wm = context.window_manager
        wm.progress_begin(0, len(obj_fcurves))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max(1, len(obj_fcurves)), multiprocessing.cpu_count())) as executor:
            futures = [executor.submit(bake_worker, name, data) for name, data in obj_fcurves.items()]
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                name, data = future.result()
                utils.baked_colors[name] = data
                if i % 10 == 0: wm.progress_update(i)
        wm.progress_end()
        
        wm.progress_begin(0, len(utils.baked_colors))
        frames_arr = np.array(frames, dtype=np.float32)
        
        for i, (obj_name, color_data) in enumerate(utils.baked_colors.items()):
            o = bpy.data.objects.get(obj_name)
            if not o: continue
            
            # Ensure target property exists
            if "md_layer_1" not in o: o["md_layer_1"] = [0.0, 0.0, 0.0, 1.0]
            
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: o.animation_data.action = bpy.data.actions.new(name=f"{obj_name}_color")
            action = o.animation_data.action
            
            # Remove old fcurves from md_layer_1
            for fc in [fc for fc in action.fcurves if fc.data_path == '["md_layer_1"]']: action.fcurves.remove(fc)
            col_arr = np.array(color_data, dtype=np.float32) / 255.0
                
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
            
            for channel in range(3):
                fc = action.fcurves.new(data_path='["md_layer_1"]', index=channel)
                final_data = np.column_stack((final_frames, final_vals[:, channel]))
                fc.keyframe_points.add(len(final_data))
                fc.keyframe_points.foreach_set('co', final_data.flatten())
                fc.update()
            if i % 50 == 0: wm.progress_update(i)

        wm.progress_end()
        self.report({'INFO'}, "Master Mix baked to md_layer_1")
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

        # --- OPTIMIZATION: Pre-Cache Constraint Lookups ---
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

                # Condition A: No active constraints (Takes location keyframes as is)
                if not active_idxs:
                    p = d.matrix_world.translation
                    sampled_data[d.name].append((f, p.x, p.y, p.z))
                    continue

                curr_idx = max(active_idxs)
                c_curr = cons[curr_idx]
                inf_curr = getattr(c_curr, "influence", 0.0)

                # Condition B: 100% Influence
                if inf_curr >= 1.0 - 1e-6:
                    tgt = getattr(c_curr, "target", None)
                    p = d.matrix_world.translation # Fallback
                    
                    if tgt and tgt.type == 'EMPTY':
                        # Extract the exact World Matrix of the Vertex if parented to a Mesh Vertex
                        if tgt.parent and tgt.parent_type == 'VERTEX' and tgt.parent.type == 'MESH':
                            v_idx = tgt.parent_vertices[0]
                            v_local_co = tgt.parent.data.vertices[v_idx].co
                            p = tgt.parent.matrix_world @ v_local_co
                        else:
                            p = tgt.matrix_world.translation
                            
                    sampled_data[d.name].append((f, p.x, p.y, p.z))
                    
                # Condition C: Crossfading (0 < influence < 1)
                else:
                    pass # DO NOTHING. No keyframes are recorded.

            if p_idx % 10 == 0: wm.progress_update(p_idx)

        # Write Keyframes & Force LINEAR
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
                
                # Condition D: Force all keyframes to be LINEAR and unselected
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