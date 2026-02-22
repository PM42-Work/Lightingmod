import bpy
import concurrent.futures
import multiprocessing
import numpy as np
import re
from .. import utils
from bpy.props import FloatProperty

# --- 1. Find Critical Points (3D Vector Edition) ---
def find_critical_indices(values):
    """
    Identifies indices where the direction of change flips in ANY color channel.
    values expected shape: (N, 3) for RGB.
    """
    n = len(values)
    if n < 3:
        return np.arange(n)

    # Calculate differences between consecutive frames for all channels
    diffs = np.diff(values, axis=0) # Shape: (N-1, 3)
    
    # Get signs (-1, 0, 1)
    signs = np.sign(diffs)
    
    # Where does the sign change? (Shape: N-2, 3)
    sign_change = signs[:-1] != signs[1:]
    
    # A point is critical if ANY of the 3 channels has a sign change
    any_sign_change = np.any(sign_change, axis=1)
    
    # Get indices. Shift +1 because diff index i describes interval (i, i+1)
    turning_points = np.where(any_sign_change)[0] + 1
    
    # Always include Start (0) and End (n-1)
    critical = np.concatenate(([0], turning_points, [n-1]))
    return np.unique(critical)

# --- 2. RDP Simplification (3D Color Distance Metric) ---
def rdp_simplify(frames, values, epsilon):
    """
    Reduces points using Ramer-Douglas-Peucker with Euclidean Color Distance.
    frames: (N,)
    values: (N, 3)
    """
    if len(frames) < 3:
        return frames, values

    start_f, end_f = frames[0], frames[-1]
    start_v, end_v = values[0], values[-1]
    
    dx = end_f - start_f
    if dx == 0:
        dists = np.zeros(len(frames))
    else:
        # Calculate normalized time 't' for each frame (0.0 to 1.0)
        t = (frames - start_f) / dx
        
        # Expected RGB: linearly interpolate between start and end values
        # t is (N,), start_v is (3,), end_v is (3,)
        expected_v = start_v + t[:, np.newaxis] * (end_v - start_v)
        
        # Calculate Euclidean distance in RGB color space
        dists = np.linalg.norm(values - expected_v, axis=1)

    dmax = dists.max()
    index = dists.argmax()

    if dmax > epsilon:
        res1_f, res1_v = rdp_simplify(frames[:index+1], values[:index+1], epsilon)
        res2_f, res2_v = rdp_simplify(frames[index:],   values[index:],   epsilon)
        
        # Concatenate results, avoiding duplicating the shared point
        return np.concatenate((res1_f[:-1], res2_f)), np.vstack((res1_v[:-1], res2_v))
    else:
        return np.array([start_f, end_f]), np.vstack((start_v, end_v))

class LIGHTINGMOD_OT_bake_colors(bpy.types.Operator):
    bl_idname = "lightingmod.bake_colors"
    bl_label  = "Bake"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Default 5/255 ≈ 0.02
    tolerance: FloatProperty(
        name="Compression Tolerance",
        description="Max error allowed (0.02 ~= 5/255 levels)",
        default=0.02, 
        min=0.0, max=1.0, precision=4
    )

    def execute(self, context):
        sc = context.scene
        start, end = sc.frame_start, sc.frame_end
        frames = list(range(start, end + 1))
        
        utils.baked_colors.clear()
        
        # 1. IDENTIFY OBJECTS & DATA
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
            
            # Robust Type Conversion
            initial_vals = {}
            for i, layer in enumerate(sc.ly_layers):
                val = o.get(f"Layer_{i+1}", [0.0, 0.0, 0.0])
                try:
                    lst = list(val)
                    if len(lst) < 3: lst = lst + [0.0]*(3-len(lst))
                    initial_vals[i+1] = lst[:3]
                except TypeError:
                    initial_vals[i+1] = [float(val)] * 3
                
            obj_fcurves[o.name] = {'fc_map': fc_map, 'initials': initial_vals}

        # 2. PREPARE SCENE DATA
        opacity_fcurves = {}
        if sc.animation_data and sc.animation_data.action:
            for fc in sc.animation_data.action.fcurves:
                m = re.match(r'ly_layers\[(\d+)\]\.opacity', fc.data_path)
                if m: opacity_fcurves[int(m.group(1))] = fc

        layer_configs = []
        for i, layer in enumerate(sc.ly_layers):
            if i in opacity_fcurves:
                ops = [opacity_fcurves[i].evaluate(f) for f in frames]
            else:
                ops = [layer.opacity] * len(frames)
            
            layer_configs.append({
                'idx': i,
                'mute': layer.mute,
                'solo': layer.solo,
                'blend': layer.blend_mode,
                'opacities': ops
            })

        any_solo = any(l['solo'] for l in layer_configs)

        # 3. WORKER FUNCTION
        def bake_worker(obj_name, data_pack):
            final_colors = []
            fc_map = data_pack['fc_map'] 
            initials = data_pack['initials']
            
            for f_idx, f in enumerate(frames):
                # Base Layer
                l0 = layer_configs[0]
                enabled0 = (not l0['mute']) and (l0['solo'] or not any_solo)
                
                base_col = [0.0, 0.0, 0.0]
                if enabled0:
                    for ch in range(3):
                        if 1 in fc_map and ch in fc_map[1]:
                            base_col[ch] = fc_map[1][ch].evaluate(f)
                        else:
                            base_col[ch] = initials[1][ch]

                # Blend Layers
                for l_cfg in layer_configs[1:]:
                    enabled = (not l_cfg['mute']) and (l_cfg['solo'] or not any_solo)
                    if not enabled: continue
                    
                    fac = l_cfg['opacities'][f_idx]
                    if fac <= 0.0001: continue
                    
                    layer_num = l_cfg['idx'] + 1
                    top = [0.0, 0.0, 0.0]
                    for ch in range(3):
                        if layer_num in fc_map and ch in fc_map[layer_num]:
                            top[ch] = fc_map[layer_num][ch].evaluate(f)
                        else:
                            top[ch] = initials[layer_num][ch]
                    
                    base_col = utils.blend_colors(base_col, top, l_cfg['blend'], fac)
                
                # Store as 0-255 int for consistent storage
                final_colors.append(tuple(int(c * 255) for c in base_col))
                
            return obj_name, final_colors

        # 4. RUN THREADS
        wm = context.window_manager
        wm.progress_begin(0, len(obj_fcurves))
        
        max_workers = min(len(obj_fcurves), multiprocessing.cpu_count())
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(bake_worker, name, data) for name, data in obj_fcurves.items()]
            
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                name, data = future.result()
                utils.baked_colors[name] = data
                if i % 10 == 0: wm.progress_update(i)
        
        wm.progress_end()
        
        # 5. BULK WRITE KEYFRAMES (With 3D Vector Compression)
        print(f"Writing keyframes to F-Curves (Tolerance: {self.tolerance})...")
        wm.progress_begin(0, len(utils.baked_colors))
        
        frames_arr = np.array(frames, dtype=np.float32)
        
        for i, (obj_name, color_data) in enumerate(utils.baked_colors.items()):
            o = bpy.data.objects.get(obj_name)
            if not o: continue
            
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: 
                o.animation_data.action = bpy.data.actions.new(name=f"{obj_name}_color")
            
            action = o.animation_data.action
            
            # Remove existing color curves
            existing_curves = [fc for fc in action.fcurves if fc.data_path == "color"]
            for fc in existing_curves: action.fcurves.remove(fc)

            # Convert to float 0.0-1.0 (Shape: N, 3)
            col_arr = np.array(color_data, dtype=np.float32) / 255.0
                
            # --- TWO-PASS COMPRESSION (VECTOR BASED) ---
            if self.tolerance > 0.0:
                # Pass 1: Find Critical Points across ALL channels
                critical_idx = find_critical_indices(col_arr)
                
                final_frames_list = []
                final_vals_list = []
                
                # Pass 2: Run RDP on segments BETWEEN critical points
                for k in range(len(critical_idx) - 1):
                    idx_start = critical_idx[k]
                    idx_end   = critical_idx[k+1]
                    
                    seg_frames = frames_arr[idx_start : idx_end + 1]
                    seg_vals   = col_arr[idx_start : idx_end + 1]
                    
                    # Compress monotonic segment (3D distance)
                    sf, sv = rdp_simplify(seg_frames, seg_vals, self.tolerance)
                    
                    if k > 0:
                        final_frames_list.extend(sf[1:])
                        final_vals_list.append(sv[1:])
                    else:
                        final_frames_list.extend(sf)
                        final_vals_list.append(sv)
                
                if final_vals_list:
                    final_frames = np.array(final_frames_list)
                    final_vals = np.vstack(final_vals_list)
                else:
                    final_frames = frames_arr
                    final_vals = col_arr
                
            else:
                final_frames = frames_arr
                final_vals = col_arr
            
            # --- WRITE SYNCHRONIZED KEYFRAMES ---
            for channel in range(3):
                fc = action.fcurves.new(data_path="color", index=channel)
                
                channel_vals = final_vals[:, channel]
                final_data = np.column_stack((final_frames, channel_vals))
                
                fc.keyframe_points.add(len(final_data))
                fc.keyframe_points.foreach_set('co', final_data.flatten())
                fc.update()
            
            if i % 50 == 0: wm.progress_update(i)

        wm.progress_end()
        self.report({'INFO'}, "Bake Complete")
        return {'FINISHED'}

classes = (LIGHTINGMOD_OT_bake_colors,)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)