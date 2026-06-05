import bpy
import mathutils
import concurrent.futures

# --- THE PURE MATH WORKER ---
def process_drone_math(task_data):
    (drone_idx, num_frames, start, end, sx, sy, sz, dir_v, speed, contrast, 
     noise_type, fade_in, fade_out, fade_in_mode, fade_out_mode, positions, color_lut) = task_data

    r_data = [0.0] * (num_frames * 2)
    g_data = [0.0] * (num_frames * 2)
    b_data = [0.0] * (num_frames * 2)

    for frame_idx, f in enumerate(range(start, end + 1)):
        px, py, pz = positions[frame_idx]
        
        # --- 1. Calculate Noise Coordinates (with XYZ Scaling) ---
        time_offset = dir_v * speed * (f / 24.0)
        cx = (px + time_offset.x) * sx
        cy = (py + time_offset.y) * sy
        cz = (pz + time_offset.z) * sz
        sample_coord = mathutils.Vector((cx, cy, cz))
        
        if noise_type == 'PERLIN':
            noise_val = (mathutils.noise.noise(sample_coord) + 1.0) / 2.0 
        elif noise_type == 'VORONOI':
            distances, _ = mathutils.noise.voronoi(sample_coord)
            noise_val = distances[0] 
        
        if contrast > 0:
            mid = 0.5; factor = 1.0 + (contrast * 10.0)
            noise_val = max(0.0, min(1.0, mid + (noise_val - mid) * factor))
        else:
            noise_val = max(0.0, min(1.0, noise_val))
        
        # --- 2. Temporal Mask Offset ---
        offset = 0.0
        if fade_in > 0 and f <= start + fade_in:
            t = (f - start) / fade_in
            smooth_t = t * t * (3.0 - 2.0 * t)
            if fade_in_mode == 'BLACK':
                offset = smooth_t - 1.0
            else: # WHITE
                offset = 1.0 - smooth_t
        elif fade_out > 0 and f >= end - fade_out:
            t = (end - f) / fade_out
            smooth_t = t * t * (3.0 - 2.0 * t)
            if fade_out_mode == 'BLACK':
                offset = smooth_t - 1.0
            else: # WHITE
                offset = 1.0 - smooth_t
                
        noise_val = max(0.0, min(1.0, noise_val + offset))
        
        # --- 3. LUT Lookup & Exact Replacement ---
        final_color = color_lut[int(noise_val * 999)]
            
        data_idx = frame_idx * 2
        r_data[data_idx] = f; r_data[data_idx + 1] = final_color[0]
        g_data[data_idx] = f; g_data[data_idx + 1] = final_color[1]
        b_data[data_idx] = f; b_data[data_idx + 1] = final_color[2]

    return drone_idx, r_data, g_data, b_data


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

        # --- Resolve Vector Scaling ---
        if sc.adv_noise_scale_linked:
            sx = sy = sz = sc.adv_noise_scale_master
        else:
            sx, sy, sz = sc.adv_noise_scale_xyz

        dir_v = mathutils.Vector(sc.adv_noise_direction)
        speed = sc.adv_noise_speed; contrast = sc.adv_noise_contrast
        noise_type = sc.adv_noise_type; fade_in = sc.adv_noise_fade_in; fade_out = sc.adv_noise_fade_out

        wm = context.window_manager
        wm.progress_begin(0, len(valid_drones))

        tasks = []
        for drone_idx, o in enumerate(valid_drones):
            wm.progress_update(drone_idx) 
            
            anim = getattr(o, "animation_data", None)
            
            # --- EXTRACT POSITIONS ---
            positions = []
            px, py, pz = o["Absolute_Position"]
            pos_fcurves = [None, None, None]
            if anim and anim.action:
                pos_fcurves = [anim.action.fcurves.find('["Absolute_Position"]', index=i) for i in range(3)]
                
            for f in range(start, end + 1):
                cur_px = pos_fcurves[0].evaluate(f) if pos_fcurves[0] else px
                cur_py = pos_fcurves[1].evaluate(f) if pos_fcurves[1] else py
                cur_pz = pos_fcurves[2].evaluate(f) if pos_fcurves[2] else pz
                positions.append((cur_px, cur_py, cur_pz))
                
            tasks.append((
                drone_idx, num_frames, start, end, sx, sy, sz, dir_v, speed, contrast, 
                noise_type, fade_in, fade_out, sc.adv_noise_fade_in_mode, sc.adv_noise_fade_out_mode, positions, color_lut
            ))

        results = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for result in executor.map(process_drone_math, tasks):
                results.append(result)

        wm.progress_begin(0, len(valid_drones)) 
        for drone_idx, r_data, g_data, b_data in results:
            wm.progress_update(drone_idx)
            o = valid_drones[drone_idx]
            
            if prop_name not in o.keys(): o[prop_name] = [0.0, 0.0, 0.0, 1.0]
            if not o.animation_data: o.animation_data_create()
            if not o.animation_data.action: o.animation_data.action = bpy.data.actions.new(name=f"{o.name}_Anim")
            
            fcurves = []
            for i in range(3):
                fc = o.animation_data.action.fcurves.find(f'["{prop_name}"]', index=i)
                if not fc: fc = o.animation_data.action.fcurves.new(f'["{prop_name}"]', index=i)
                fcurves.append(fc)

            for i, fc in enumerate(fcurves):
                curve_data = {p.co[0]: p.co[1] for p in fc.keyframe_points}
                new_data = r_data if i == 0 else (g_data if i == 1 else b_data)
                for j in range(num_frames):
                    curve_data[new_data[j * 2]] = new_data[j * 2 + 1]
                    
                sorted_frames = sorted(curve_data.keys())
                flat_data = [0.0] * (len(sorted_frames) * 2)
                for j, f in enumerate(sorted_frames):
                    flat_data[j * 2] = f; flat_data[j * 2 + 1] = curve_data[f]
                    
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(sorted_frames))
                fc.keyframe_points.foreach_set('co', flat_data)
                fc.update()

        wm.progress_end()
        self.report({'INFO'}, "Absolute Overwrite Noise Baked Successfully!")
        return {'FINISHED'}