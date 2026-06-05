import bpy
import random
from ... import utils

def interp(a, b, t): return a*(1-t) + b*t
def smoothstep(x): return x * x * (3 - 2 * x)

def apply_sparkle_effect(context, is_temporal=False):
    sc = context.scene
    start, end = sc.adv_effector_start, sc.adv_effector_end
    prop = f"Layer_{int(sc.adv_effector_target_layer)+1}"

    # 1. Gather Objects
    drones = []
    if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
         if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
             g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
             drones = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
    else:
         drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
    
    if not drones: return {'CANCELLED'}

    total = len(drones)
    cooldowns = {}
    stages = list(sc.adv_temporal_stages)
    profiles = list(sc.adv_spark_profiles)

    # Safety checks
    if is_temporal and len(stages) < 2: return 'CANCELLED_NO_STAGES'
    if not is_temporal and sc.adv_color_source == 'PALETTE' and not profiles: return 'CANCELLED_NO_PROFILES'

    if not is_temporal and not getattr(sc, "adv_use_advanced_spark_profiles", False):
        if profiles: profiles = [profiles[0]]

    total_weight = sum(p.weight for p in profiles if len(p.colors) > 0) if not is_temporal else 1.0
    sampled_dict = {c.name: list(c.color) for c in sc.adv_sampled_colors} if sc.adv_color_source == 'SAMPLED' else None
    
    # 2. Main Timeline Engine
    for f in range(start, end + 1):
        current_infl = sc.adv_effector_influence
        
        if is_temporal:
            progress = smoothstep((f - start) / max(1, end - start))
            idx = min(len(stages) - 2, int(progress * (len(stages) - 1)))
            alpha = (progress * (len(stages) - 1)) - idx
            
            s0, s1 = stages[idx], stages[idx+1]
            current_trans = interp(s0.transition, s1.transition, alpha)
            current_infl  = interp(s0.influence, s1.influence, alpha)
            
            c0_sampled = {c.name: list(c.color) for c in s0.sampled_colors} if s0.color_source == 'SAMPLED' else None
            c1_sampled = {c.name: list(c.color) for c in s1.sampled_colors} if s1.color_source == 'SAMPLED' else None
            c0_palette = [list(c.color)[:3] for c in s0.colors]
            c1_palette = [list(c.color)[:3] for c in s1.colors]
            
            t_val = max(1, int(current_trans))
        else:
            if sc.adv_color_source == 'PALETTE' and total_weight <= 0: continue
            t_val = max(1, int(sc.adv_effector_transition))

        # Distribution
        count = max(1, round(total * current_infl / (t_val * 2)))
        elig = [o for o in drones if f >= cooldowns.get(o.name, start)]
        if not elig: continue
        
        chosen = random.sample(elig, min(count, len(elig)))
        
        # Assignment
        for o in chosen:
            if prop not in o.keys(): continue
            base = o[prop][:]

            if is_temporal:
                if s0.color_source == 'SAMPLED': c_start = c0_sampled.get(o.name, [1.0, 1.0, 1.0])
                else: c_start = random.choice(c0_palette) if c0_palette else [1.0, 1.0, 1.0]
                    
                if s1.color_source == 'SAMPLED': c_end = c1_sampled.get(o.name, [1.0, 1.0, 1.0])
                else: c_end = random.choice(c1_palette) if c1_palette else [1.0, 1.0, 1.0]
                    
                # --- NEW: OKLCH Blending ---
                newcol = utils.interpolate_oklch(c_start, c_end, alpha)
                envelope = sc.adv_sparkle_style
                lifespan = t_val
            else:
                if sc.adv_color_source == 'SAMPLED':
                    newcol = sampled_dict.get(o.name, [1.0, 1.0, 1.0])
                    envelope = sc.adv_sparkle_style
                    lifespan = t_val
                else:
                    rand_val = random.uniform(0, total_weight)
                    current_weight = 0.0
                    selected_profile = None
                    for p in profiles:
                        if len(p.colors) == 0: continue
                        current_weight += p.weight
                        if rand_val <= current_weight:
                            selected_profile = p
                            break
                    if not selected_profile: continue 
                    newcol = random.choice([list(c.color)[:3] for c in selected_profile.colors])
                    envelope = selected_profile.style
                    lifespan = max(1, selected_profile.lifespan)

            # Execution
            if envelope == 'PULSE':
                o[prop] = base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f)
                o[prop] = newcol; o.keyframe_insert(data_path=f'["{prop}"]', frame=f + lifespan)
                o[prop] = base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f + 2 * lifespan)
                cooldowns[o.name] = f + 2 * lifespan + 1
            elif envelope == 'TWINKLE':
                o[prop] = base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f)
                o[prop] = newcol; o.keyframe_insert(data_path=f'["{prop}"]', frame=f + 1)
                o[prop] = base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f + 2 * lifespan)
                cooldowns[o.name] = f + 2 * lifespan + 1

    return {'FINISHED'}