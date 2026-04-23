import bpy
import random
from ... import utils

def interp(a, b, t): return a*(1-t) + b*t
def smoothstep(x): return x * x * (3 - 2 * x)

def apply_sparkle_effect(context, is_temporal=False):
    sc = context.scene
    start, end = sc.effector_start, sc.effector_end
    prop = f"Layer_{int(sc.effector_target_layer)+1}"

    # 1. Gather Objects
    drones = []
    if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
         if sc.drone_formations[sc.drone_formations_index].groups:
             g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
             drones = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
    else:
         drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
    
    if not drones: return {'CANCELLED'}

    total = len(drones)
    cooldowns = {}
    stages = list(sc.temporal_stages)
    profiles = list(sc.spark_profiles)

    # Safety checks
    if is_temporal and len(stages) < 2: return 'CANCELLED_NO_STAGES'
    if not is_temporal and not profiles: return 'CANCELLED_NO_PROFILES'

    # --- NEW: Filter profiles if the UI is in Simple Mode ---
    if not is_temporal and not getattr(sc, "use_advanced_spark_profiles", False):
        profiles = [profiles[0]] # Force execution of only the first profile

    # Normalization math (calculate total weight of valid profiles)
    total_weight = sum(p.weight for p in profiles if len(p.colors) > 0) if not is_temporal else 1.0
    
    # 2. Main Timeline Engine
    for f in range(start, end + 1):
        current_infl = sc.effector_influence
        
        if is_temporal:
            progress = smoothstep((f - start) / max(1, end - start))
            idx = min(len(stages) - 2, int(progress * (len(stages) - 1)))
            alpha = (progress * (len(stages) - 1)) - idx
            
            s0, s1 = stages[idx], stages[idx+1]
            current_trans = interp(s0.transition, s1.transition, alpha)
            current_infl  = interp(s0.influence, s1.influence, alpha)
            
            c0s = [c.color for c in s0.colors]
            c1s = [c.color for c in s1.colors]
            
            pool = []
            common_len = min(len(c0s), len(c1s))
            for k in range(common_len):
                pool.append([interp(c0s[k][j], c1s[k][j], alpha) for j in range(3)])
            if not pool: pool = [c[:3] for c in (c0s or c1s)]
            if not pool: continue
            
            t_val = max(1, int(current_trans))
        else:
            if total_weight <= 0: continue
            # The global transition slider is now purely used to determine global density/cooldowns
            t_val = max(1, int(sc.effector_transition))

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
                newcol = random.choice(pool)
                envelope = sc.sparkle_style
                lifespan = t_val
            else:
                # The Dice Roll: Normalization in action!
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