import bpy
import mathutils
from ... import utils

class LIGHTINGMOD_OT_domain_effector(bpy.types.Operator):
    bl_idname="lightingmod.domain"; bl_label="Domain"
    def execute(self, context):
        sc=context.scene; start=sc.effector_start; end=sc.effector_end; trans=sc.effector_transition
        dom=sc.domain_object; drones=[o for o in context.selected_objects if o.get("md_sphere") and o.type=='MESH']
        if not dom: return {'CANCELLED'}
        
        bbox=[dom.matrix_world @ mathutils.Vector(c) for c in dom.bound_box]
        xs=[v.x for v in bbox]; ys=[v.y for v in bbox]; zs=[v.z for v in bbox]
        minx,maxx=min(xs),max(xs); miny,maxy=min(ys),max(ys); minz,maxz=min(zs),max(zs)
        
        prop=f"Layer_{int(sc.effector_target_layer)+1}"
        
        for o in drones:
            if prop not in o.keys(): continue
            prev=False; base=o[prop][:]
            for f in range(start,end+1):
                sc.frame_set(f)
                x,y,z=o.matrix_world.to_translation()
                inside=(minx<=x<=maxx and miny<=y<=maxy and minz<=z<=maxz)
                if inside and not prev:
                    r,g,b,_=sc.effector_colors[0].color if sc.effector_colors else (1,1,1,1)
                    o[prop]=[r,g,b]; o.keyframe_insert(data_path=f'["{prop}"]',frame=f)
                    o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]',frame=f+trans)
                elif not inside and prev:
                    r,g,b,_=sc.effector_colors[0].color if sc.effector_colors else (1,1,1,1)
                    o[prop]=[r,g,b]; o.keyframe_insert(data_path=f'["{prop}"]',frame=f-1)
                    o[prop]=base;   o.keyframe_insert(data_path=f'["{prop}"]',frame=f-1+trans)
                prev=inside
        return{'FINISHED'}
