import bpy
import concurrent.futures
import multiprocessing
import numpy as np
import re
from .. import utils
from bpy.props import FloatProperty

# --- 1. Find Critical Points (Peaks, Valleys, Plateaus) ---
def find_critical_indices(values):
    """
    Identifies indices where the direction of change flips (slope sign change).
    These points are mandatory to preserve strobe timing and intensity.
    """
    n = len(values)
    if n < 3:
        return np.arange(n) # Keep all if too small

    # Calculate differences between consecutive frames
    diffs = np.diff(values) # Length n-1
    
    # Get signs (-1, 0, 1). 
    signs = np.sign(diffs)
    
    # Where does the sign change? 
    sign_change = signs[:-1] != signs[1:]
    
    # Get indices. Shift +1 because diff index i describes interval (i, i+1)
    turning_points = np.where(sign_change)[0] + 1
    
    # Always include Start (0) and End (n-1)
    critical = np.concatenate(([0], turning_points, [n-1]))
    return np.unique(critical)

# --- 2. RDP Simplification (Vertical Error Metric) ---
def rdp_simplify(frames, values, epsilon):
    """
    Reduces points using Ramer-Douglas-Peucker with Vertical Distance error.
    """
    points = np.column_stack((frames, values))
    
    if len(points) < 3:
        return points

    start = points[0]
    end = points[-1]
    
    dx = end[0] - start[0]
    if dx == 0:
        dists = np.zeros(len(points))
    else:
        # Line Eq: y = mx + c
        m = (end[1] - start[1]) / dx
        c = start[1] - m * start[0]
        
        # Expected Y vs Actual Y
        expected_y = m * points[:, 0] + c
        dists = np.abs(points[:, 1] - expected_y)

    dmax = dists.max()
    index = dists.argmax()

    if dmax > epsilon:
        res1 = rdp_simplify(frames[:index+1], values[:index+1], epsilon)
        res2 = rdp_simplify(frames[index:],   values[index:],   epsilon)
        return np.vstack((res1[:-1], res2))
    else:
        return np.array([start, end])

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
            
            # --- FIX: Robust Type Conversion ---
            initial_vals = {}
            for i, layer in enumerate(sc.ly_layers):
                val = o.get(f"Layer_{i+1}", [0.0, 0.0, 0.0])
                try:
                    # Force conversion to Python list of floats
                    # This handles IDPropertyArray correctly even if hasattr fails
                    lst = list(val)
                    # Ensure at least 3 components (RGB)
                    if len(lst) < 3: lst = lst + [0.0]*(3-len(lst))
                    initial_vals[i+1] = lst[:3]
                except TypeError:
                    # If val is a single float/int (not iterable), broadcast it
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
                
                # Store as 0-255 int
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
        
        # 5. BULK WRITE KEYFRAMES (With Two-Pass Compression)
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
            
            # Convert to float 0-1
            col_arr = np.array(color_data, dtype=np.float32) / 255.0
            
            # Remove existing color curves
            existing_curves = [fc for fc in action.fcurves if fc.data_path == "color"]
            for fc in existing_curves: action.fcurves.remove(fc)
                
            for channel in range(3):
                fc = action.fcurves.new(data_path="color", index=channel)
                
                channel_vals = col_arr[:, channel]
                
                # --- TWO-PASS COMPRESSION ---
                if self.tolerance > 0.0:
                    # Pass 1: Find Critical Points (Slope Changes)
                    critical_idx = find_critical_indices(channel_vals)
                    
                    simplified_segments = []
                    
                    # Pass 2: Run RDP on segments BETWEEN critical points
                    for k in range(len(critical_idx) - 1):
                        idx_start = critical_idx[k]
                        idx_end   = critical_idx[k+1]
                        
                        seg_frames = frames_arr[idx_start : idx_end + 1]
                        seg_vals   = channel_vals[idx_start : idx_end + 1]
                        
                        # Compress monotonic segment
                        seg_res = rdp_simplify(seg_frames, seg_vals, self.tolerance)
                        
                        if k > 0:
                            simplified_segments.append(seg_res[1:])
                        else:
                            simplified_segments.append(seg_res)
                    
                    if simplified_segments:
                        final_data = np.vstack(simplified_segments)
                    else:
                        final_data = np.column_stack((frames_arr, channel_vals))
                    
                else:
                    final_data = np.column_stack((frames_arr, channel_vals))
                
                # Write
                fc.keyframe_points.add(len(final_data))
                fc.keyframe_points.foreach_set('co', final_data.flatten())
            
            if i % 50 == 0: wm.progress_update(i)

        wm.progress_end()
        self.report({'INFO'}, "Bake Complete")
        return {'FINISHED'}

classes = (LIGHTINGMOD_OT_bake_colors,)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)