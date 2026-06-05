import bpy
import mathutils
import concurrent.futures

# --- THE PURE MATH WORKER (Runs safely on multiple threads) ---
def process_drone_math(task_data):
    (drone_idx, num_frames, start, end, scale, dir_v, speed, contrast, 
     noise_type, fade_in, fade_out, positions, base_start, base_end, color_lut) = task_data

    r_data = [0.0] * (num_frames * 2)
    g_data = [0.0] * (num_frames * 2)
    b_data = [0.0] * (num_frames * 2)

    for frame_idx, f in enumerate(range(start, end + 1)):
        px, py, pz = positions[frame_idx]
        
        # Flow math
        time_offset = dir_v * speed * (f / 24.0)
        sample_coord = (mathutils.Vector((px, py, pz)) + time_offset) * scale 
        
        # Noise generation
        if noise_type == 'PERLIN':
            noise_val = (mathutils.noise.noise(sample_coord) + 1.0) / 2.0 
        elif noise_type == 'VORONOI':
            distances, _ = mathutils.noise.voronoi(sample_coord)
            noise_val = distances[0] 
        
        # Contrast
        if contrast > 0:
            mid = 0.5; factor = 1.0 + (contrast * 10.0)
            noise_val = max(0.0, min(1.0, mid + (noise_val - mid) * factor))
        else:
            noise_val = max(0.0, min(1.0, noise_val))
        
        # LUT Lookup
        ramp_color = color_lut[int(noise_val * 999)]
        
        # Fading
        a_in = (f - start) / fade_in if fade_in > 0 and f < start + fade_in else 1.0
        a_out = (end - f) / fade_out if fade_out > 0 and f > end - fade_out else 1.0
        smooth_alpha = max(0.0, min(1.0, min(a_in, a_out))) ** 2 * (3.0 - 2.0 * max(0.0, min(1.0, min(a_in, a_out))))
        
        if smooth_alpha < 1.0:
            mask_offset = (smooth_alpha * 2.0) - 1.0
            growth_mask = max(0.0, min(1.0, noise_val + mask_offset))
            base = base_start if f < start + fade_in else base_end
            final_color = [base[i] * (1.0 - growth_mask) + ramp_color[i] * growth_mask for i in range(3)]
        else:
            final_color = ramp_color
            
        data_idx = frame_idx * 2
        r_data[data_idx] = f; r_data[data_idx + 1] = final_color[0]
        g_data[data_idx] = f; g_data[data_idx + 1] = final_color[1]
        b_data[data_idx] = f; b_data[data_idx + 1] = final_color[2]

    return drone_idx, r_data, g_data, b_data


class LIGHTINGMOD_OT_noise_effector(bpy.types.Operator):
    bl_idname = "lightingmod.noise_effector"
    bl_label = "Apply Noise"
    
    def execute(self, context):
        sc = context.scene
        start, end = sc.effector_start, sc.effector_end
        prop_name = f"Layer_{int(sc.effector_target_layer)+1}"
        num_frames = (end - start) + 1
        
        # 1. Gather Drones
        drones = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 drones = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
             
        valid_drones = [o for o in drones if "Absolute_Position" in o.keys()]
        if not valid_drones:
            self.report({'ERROR'}, "Positions not baked!")
            return {'CANCELLED'}

        # LUT Setup
        ng = bpy.data.node_groups.get("LightingModNoiseRamp")
        if not ng or "Ramp" not in ng.nodes: return {'CANCELLED'}
        color_lut = [list(ng.nodes["Ramp"].color_ramp.evaluate(i / 999.0))[:3] for i in range(1000)]

        # Cache UI Params
        scale = sc.noise_scale; dir_v = mathutils.Vector(sc.noise_direction)
        speed = sc.noise_speed; contrast = sc.noise_contrast
        noise_type = sc.noise_type; fade_in = sc.noise_fade_in; fade_out = sc.noise_fade_out

        wm = context.window_manager
        wm.progress_begin(0, len(valid_drones))

        # --- PHASE 1: DATA EXTRACTION (Main Thread) ---
        tasks = []
        for drone_idx, o in enumerate(valid_drones):
            wm.progress_update(drone_idx) 
            
            base_start = list(o.get(prop_name, [0,0,0,1]))[:3]
            base_end = list(o.get(prop_name, [0,0,0,1]))[:3]
            
            positions = []
            px, py, pz = o["Absolute_Position"]
            anim = getattr(o, "animation_data", None)
            pos_fcurves = [None, None, None]
            if anim and anim.action:
                pos_fcurves = [anim.action.fcurves.find('["Absolute_Position"]', index=i) for i in range(3)]
                
            for f in range(start, end + 1):
                cur_px = pos_fcurves[0].evaluate(f) if pos_fcurves[0] else px
                cur_py = pos_fcurves[1].evaluate(f) if pos_fcurves[1] else py
                cur_pz = pos_fcurves[2].evaluate(f) if pos_fcurves[2] else pz
                positions.append((cur_px, cur_py, cur_pz))
                
            tasks.append((
                drone_idx, num_frames, start, end, scale, dir_v, speed, contrast, 
                noise_type, fade_in, fade_out, positions, base_start, base_end, color_lut
            ))

        # --- PHASE 2: PARALLEL COMPUTATION (Worker Threads) ---
        results = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for result in executor.map(process_drone_math, tasks):
                results.append(result)

        # --- PHASE 3: BULLETPROOF C-LEVEL INJECTION (Main Thread) ---
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
                # 1. Extract existing curve data into a fast Dictionary
                curve_data = {p.co[0]: p.co[1] for p in fc.keyframe_points}
                
                # 2. Merge our newly calculated noise frames into the dictionary
                new_data = r_data if i == 0 else (g_data if i == 1 else b_data)
                for j in range(num_frames):
                    curve_data[new_data[j * 2]] = new_data[j * 2 + 1]
                    
                # 3. Create a perfectly sized flat array for foreach_set
                sorted_frames = sorted(curve_data.keys())
                flat_data = [0.0] * (len(sorted_frames) * 2)
                for j, f in enumerate(sorted_frames):
                    flat_data[j * 2] = f
                    flat_data[j * 2 + 1] = curve_data[f]
                    
                # 4. Wipe the old curve and cleanly inject the flawless C-Array
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(sorted_frames))
                fc.keyframe_points.foreach_set('co', flat_data)
                fc.update()

        wm.progress_end()
        self.report({'INFO'}, "Parallelized Noise Baked Successfully!")
        return {'FINISHED'}