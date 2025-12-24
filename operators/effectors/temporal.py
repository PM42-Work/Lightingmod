import bpy
import random
from ... import utils

class LIGHTINGMOD_OT_temporal_sparkle(bpy.types.Operator):
    bl_idname = "lightingmod.temporal_sparkle"
    bl_label = "Temporal Sparkle"
    
    def execute(self, context):
        sc = context.scene
        stages = list(sc.temporal_stages)
        if len(stages) < 2:
            self.report({'WARNING'}, "Need at least 2 stages")
            return {'CANCELLED'}

        start, end = sc.effector_start, sc.effector_end
        prop = f"Layer_{int(sc.effector_target_layer)+1}"
        
        # Gather Objects
        drones = []
        if sc.effector_selection_mode == 'GROUP' and sc.drone_formations:
             if sc.drone_formations and sc.drone_formations[sc.drone_formations_index].groups:
                 g = sc.drone_formations[sc.drone_formations_index].groups[sc.drone_formations[sc.drone_formations_index].groups_index]
                 drones = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             drones = [o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']

        total = len(drones)
        cooldowns = {}

        def interp(a, b, t): return a*(1-t) + b*t
        def smoothstep(x): return x * x * (3 - 2 * x)

        for f in range(start, end + 1):
            progress = smoothstep((f - start) / max(1, end - start))
            # Find active stage segment
            idx = min(len(stages) - 2, int(progress * (len(stages) - 1)))
            alpha = (progress * (len(stages) - 1)) - idx
            
            s0, s1 = stages[idx], stages[idx+1]
            trans = interp(s0.transition, s1.transition, alpha)
            infl  = interp(s0.influence, s1.influence, alpha)
            
            # Blend Color Palettes
            c0s = [c.color for c in s0.colors]
            c1s = [c.color for c in s1.colors]
            pool = []
            
            # Interpolate matching indices
            common_len = min(len(c0s), len(c1s))
            for k in range(common_len):
                pool.append([interp(c0s[k][j], c1s[k][j], alpha) for j in range(3)])
            
            # If lists uneven, fallback to the remaining colors of the active stage
            if not pool:
                pool = [c[:3] for c in (c0s or c1s)]
            
            if not pool: continue 

            count = max(1, round(total * infl / max(1, int(trans) * 2)))
            elig = [o for o in drones if f >= cooldowns.get(o.name, start)]
            if not elig: continue
            
            chosen = random.sample(elig, min(count, len(elig)))
            for o in chosen:
                if prop not in o.keys(): continue
                base = o[prop][:]
                newcol = random.choice(pool)
                
                # Keyframe: Base -> Color -> Base
                o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f)
                o[prop]=newcol; o.keyframe_insert(data_path=f'["{prop}"]', frame=f+int(trans))
                o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]', frame=f+2*int(trans))
                
                cooldowns[o.name] = f + 2*int(trans) + 1
                
        return {'FINISHED'}

class LIGHTINGMOD_OT_stage_add(bpy.types.Operator):
    bl_idname = "lightingmod.stage_add"
    bl_label = "Add Stage"
    def execute(self, context):
        sc = context.scene
        st = sc.temporal_stages.add()
        st.name = f"Stage {len(sc.temporal_stages)}"
        return {'FINISHED'}

class LIGHTINGMOD_OT_stage_remove(bpy.types.Operator):
    bl_idname = "lightingmod.stage_remove"
    bl_label = "Remove Stage"
    def execute(self, context):
        sc = context.scene
        if sc.temporal_stages:
            sc.temporal_stages.remove(sc.temporal_stages_index)
            sc.temporal_stages_index = max(0, sc.temporal_stages_index - 1)
        return {'FINISHED'}