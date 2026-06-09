import bpy
import mathutils
import concurrent.futures
import math
import numpy as np

# --- THE PURE MATH WORKER ---
def process_drone_math(task_data):
    (drone_idx, num_frames, start, end, sx, sy, sz, dir_v, speed, 
     rot_axis, rot_speed, contrast, noise_type, wave_dist, mus_det, mus_rough,
     fade_in, fade_out, fade_in_mode, fade_out_mode, 
     positions, swarm_centers, base_start, base_end, color_lut) = task_data

    raw_colors = []
    
    rot_axis_vec = mathutils.Vector(rot_axis)
    if rot_axis_vec.length > 0: rot_axis_vec.normalize()
    else: rot_axis_vec = mathutils.Vector((0,0,1))
    
    frame_range = max(1, end - start)

    for frame_idx, f in enumerate(range(start, end + 1)):
        px, py, pz = positions[frame_idx]
        cx, cy, cz = swarm_centers[frame_idx]
        
        # --- 1. Base Plate & Local Swarm Centering ---
        t_frame = (f - start) / frame_range
        current_base = [
            base_start[0] * (1.0 - t_frame) + base_end[0] * t_frame,
            base_start[1] * (1.0 - t_frame) + base_end[1] * t_frame,
            base_start[2] * (1.0 - t_frame) + base_end[2] * t_frame
        ]
        
        local_pos = mathutils.Vector((px - cx, py - cy, pz - cz))
        
        # --- 2. Swarm Rotation & Translation ---
        if rot_speed != 0.0:
            angle = rot_speed * (f / 24.0)
            quat = mathutils.Quaternion(rot_axis_vec, angle)
            local_pos = quat @ local_pos
            
        world_pos = local_pos + mathutils.Vector((cx, cy, cz))
        time_offset = dir_v * speed * (f / 24.0)
        
        sample_x = (world_pos.x + time_offset.x) * sx
        sample_y = (world_pos.y + time_offset.y) * sy
        sample_z = (world_pos.z + time_offset.z) * sz
        sample_coord = mathutils.Vector((sample_x, sample_y, sample_z))
        
        # --- 3. Noise Generations ---
        if noise_type == 'PERLIN':
            noise_val = (mathutils.noise.noise(sample_coord) + 1.0) / 2.0 
        elif noise_type == 'VORONOI':
            distances, _ = mathutils.noise.voronoi(sample_coord)
            noise_val = distances[0] 
        elif noise_type == 'CELL':
            noise_val = mathutils.noise.cell(sample_coord)
        elif noise_type == 'WAVE':
            if wave_dist > 0.0:
                dist_val = mathutils.noise.noise(sample_coord) * wave_dist
                sample_coord.x += dist_val
                sample_coord.y += dist_val
                sample_coord.z += dist_val
            noise_val = (math.sin(sample_coord.x * 10.0) + 1.0) / 2.0
        elif noise_type == 'MUSGRAVE':
            val = mathutils.noise.hetero_terrain(sample_coord, 1.0, mus_rough, mus_det, 1.0)
            noise_val = max(0.0, min(1.0, val / 2.0))
        
        if contrast > 0:
            mid = 0.5; factor = 1.0 + (contrast * 10.0)
            noise_val = max(0.0, min(1.0, mid + (noise_val - mid) * factor))
        else:
            noise_val = max(0.0, min(1.0, noise_val))
        
        # --- 4. Exact Replacement & Fade Masking ---
        offset = 0.0
        if fade_in > 0 and f <= start + fade_in:
            t = (f - start) / fade_in
            smooth_t = t * t * (3.0 - 2.0 * t)
            offset = (smooth_t - 1.0) if fade_in_mode == 'BLACK' else (1.0 - smooth_t)
        elif fade_out > 0 and f >= end - fade_out:
            t = (end - f) / fade_out
            smooth_t = t * t * (3.0 - 2.0 * t)
            offset = (smooth_t - 1.0) if fade_out_mode == 'BLACK' else (1.0 - smooth_t)
                
        noise_val = max(0.0, min(1.0, noise_val + offset))
        final_color = color_lut[int(noise_val * 999)]
        raw_colors.append(final_color)

    # --- 5. RDP Simplification ---
    from ... import utils
    frames_arr = np.array(list(range(start, end + 1)), dtype=np.float32)
    col_arr = np.array(raw_colors, dtype=np.float32)
    
    # OPTIMIZATION: Loosened tolerance from 0.01 to 0.05 to prevent extreme recursive recursion on noisy curves
    critical_idx = utils.find_critical_indices(col_arr)
    final_f_list, final_v_list = [], []
    for k in range(len(critical_idx) - 1):
        start_i, end_i = critical_idx[k], critical_idx[k+1]
        sf, sv = utils.rdp_simplify(frames_arr[start_i:end_i+1], col_arr[start_i:end_i+1], 0.05)
        if k > 0:
            final_f_list.extend(sf[1:])
            final_v_list.append(sv[1:])
        else:
            final_f_list.extend(sf)
            final_v_list.append(sv)
            
    final_frames = np.array(final_f_list) if final_v_list else frames_arr
    final_vals = np.vstack(final_v_list) if final_v_list else col_arr
    
    return drone_idx, final_frames.tolist(), final_vals.tolist()


class ADVLIGHTING_OT_noise_effector(bpy.types.Operator):
    bl_idname = "advlighting.noise_effector"
    bl_label = "Apply Noise"
    
    def execute(self, context):
        sc = context.scene
        start, end = sc.adv_effector_start, sc.adv_effector_end
        prop_name = f"Layer_{int(sc.adv_effector_target_layer)+1}"
        num_frames = (end - start) + 1
        
        drones = []
        if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
             if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
                 g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
                 drones = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
             
        valid_drones = [o for o in drones if "Absolute_Position" in o.keys()]
        if not valid_drones:
            self.report({'ERROR'}, "Positions not baked!")
            return {'CANCELLED'}

        ng = bpy.data.node_groups.get("AdvLightingNoiseRamp")
        if not ng or "Ramp" not in ng.nodes: return {'CANCELLED'}
        color_lut = [list(ng.nodes["Ramp"].color_ramp.evaluate(i / 999.0))[:3] for i in range(1000)]

        if sc.adv_noise_scale_linked: sx = sy = sz = sc.adv_noise_scale_master
        else: sx, sy, sz = sc.adv_noise_scale_xyz

        dir_v = mathutils.Vector(sc.adv_noise_direction)
        speed = sc.adv_noise_speed; contrast = sc.adv_noise_contrast
        noise_type = sc.adv_noise_type; fade_in = sc.adv_noise_fade_in; fade_out = sc.adv_noise_fade_out
        
        wave_dist = sc.adv_noise_wave_distortion
        mus_det = sc.adv_noise_musgrave_detail
        mus_rough = sc.adv_noise_musgrave_roughness
        rot_axis = sc.adv_noise_rotation_axis
        rot_speed = sc.adv_noise_rotation_speed

        wm = context.window_manager
        wm.progress_begin(0, len(valid_drones))
        
        # --- OPTIMIZATION: Ultra-fast Numpy Swarm Centering ---
        drone_positions = []
        for o in valid_drones:
            px, py, pz = o["Absolute_Position"]
            anim = getattr(o, "animation_data", None)
            pos_fc = [anim.action.fcurves.find('["Absolute_Position"]', index=i) if anim and anim.action else None for i in range(3)]
            
            pts = []
            for f in range(start, end + 1):
                x = pos_fc[0].evaluate(f) if pos_fc[0] else px
                y = pos_fc[1].evaluate(f) if pos_fc[1] else py
                z = pos_fc[2].evaluate(f) if pos_fc[2] else pz
                pts.append((x,y,z))
            drone_positions.append(pts)

        # Replaced the slow python loop with C-compiled Numpy averaging
        dp_np = np.array(drone_positions, dtype=np.float32)
        swarm_centers = np.mean(dp_np, axis=0).tolist() if len(dp_np) > 0 else [[0.0, 0.0, 0.0]] * num_frames

        # --- Dispatch Tasks ---
        tasks = []
        for drone_idx, o in enumerate(valid_drones):
            anim = getattr(o, "animation_data", None)
            col_fcurves = [None, None, None]
            if anim and anim.action:
                col_fcurves = [anim.action.fcurves.find(f'["{prop_name}"]', index=i) for i in range(3)]
                
            default_col = list(o.get(prop_name, [0.0, 0.0, 0.0, 1.0]))[:3]
            base_start = [col_fcurves[i].evaluate(start) if col_fcurves[i] else default_col[i] for i in range(3)]
            base_end = [col_fcurves[i].evaluate(end) if col_fcurves[i] else default_col[i] for i in range(3)]
                
            tasks.append((
                drone_idx, num_frames, start, end, sx, sy, sz, dir_v, speed, 
                rot_axis, rot_speed, contrast, noise_type, wave_dist, mus_det, mus_rough, 
                fade_in, fade_out, sc.adv_noise_fade_in_mode, sc.adv_noise_fade_out_mode, 
                drone_positions[drone_idx], swarm_centers, base_start, base_end, color_lut
            ))

        results = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for result in executor.map(process_drone_math, tasks):
                results.append(result)

        # --- Write Simplified RDP Keyframes ---
        for drone_idx, final_frames, final_vals in results:
            wm.progress_update(drone_idx)
            o = valid_drones[drone_idx]
            
            if prop_name not in o.keys(): o[prop_name] = [0.0, 0.0, 0.0, 1.0]
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: o.animation_data.action = bpy.data.actions.new(name=f"{o.name}_Anim")
            
            for i in range(3):
                fc = o.animation_data.action.fcurves.find(f'["{prop_name}"]', index=i)
                if not fc: 
                    fc = o.animation_data.action.fcurves.new(f'["{prop_name}"]', index=i)
                    existing_pts = np.empty((0, 2), dtype=np.float32)
                else:
                    num_existing = len(fc.keyframe_points)
                    if num_existing > 0:
                        coords = np.zeros(num_existing * 2, dtype=np.float32)
                        fc.keyframe_points.foreach_get('co', coords)
                        existing_pts = coords.reshape((num_existing, 2))
                        
                        # SMART FILTER: Keep keyframes OUTSIDE the current target range
                        mask = (existing_pts[:, 0] < start) | (existing_pts[:, 0] > end)
                        existing_pts = existing_pts[mask]
                    else:
                        existing_pts = np.empty((0, 2), dtype=np.float32)
                
                # Our new baked points
                new_pts = np.column_stack((final_frames, np.array(final_vals)[:, i]))
                
                # Stitch them together and sort chronologically
                combined_pts = np.vstack((existing_pts, new_pts))
                combined_pts = combined_pts[combined_pts[:, 0].argsort()]
                
                # Instantly clear and overwrite with the combined array
                fc.keyframe_points.clear() 
                num_points = len(combined_pts)
                fc.keyframe_points.add(num_points)
                fc.keyframe_points.foreach_set('co', combined_pts.flatten())
                fc.update()
                
                # Keep Graph Editor Clean
                bool_arr = [False] * num_points
                fc.keyframe_points.foreach_set('select_control_point', bool_arr)
                fc.keyframe_points.foreach_set('select_left_handle', bool_arr)
                fc.keyframe_points.foreach_set('select_right_handle', bool_arr)

        wm.progress_end()
        self.report({'INFO'}, "Organic Smart-Rotated Noise Baked Successfully!")
        return {'FINISHED'}