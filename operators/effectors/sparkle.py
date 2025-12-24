import bpy
import random
from ... import utils

class LIGHTINGMOD_OT_sparkle_effector(bpy.types.Operator):
    bl_idname="lightingmod.sparkle"; bl_label="Sparkle"
    def execute(self, context):
        sc=context.scene; start=sc.effector_start; end=sc.effector_end
        trans=sc.effector_transition; infl=sc.effector_influence
        drones=[o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
        total=len(drones); count = max(1, round(total * infl / (trans*2)))
        cooldowns={}
        
        prop=f"Layer_{int(sc.effector_target_layer)+1}"
        
        for f in range(start,end+1):
            elig=[o for o in drones if f>=cooldowns.get(o.name,start)]
            if not elig: continue
            lit=random.sample(elig,min(count,len(elig)))
            for o in lit:
                if prop not in o.keys(): continue
                base=o[prop][:]
                if not sc.effector_colors: continue
                ci=random.choice(sc.effector_colors)
                newcol=list(ci.color)[:3]
                
                o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]',frame=f)
                o[prop]=newcol; o.keyframe_insert(data_path=f'["{prop}"]',frame=f+trans)
                o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]',frame=f+2*trans)
                cooldowns[o.name]=f+2*trans+1
        return{'FINISHED'}
