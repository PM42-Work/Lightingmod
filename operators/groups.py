import bpy
import json
import os
from bpy.props import BoolProperty

class ADVLIGHTING_OT_formation_add(bpy.types.Operator):
    bl_idname = "advlighting.formation_add"
    bl_label = "Add Formation"
    def execute(self, context):
        sc = context.scene
        f = sc.adv_drone_formations.add()
        f.name = f"Formation {len(sc.adv_drone_formations) + 1}"
        sc.adv_drone_formations_index = len(sc.adv_drone_formations)-1
        return {'FINISHED'}

class ADVLIGHTING_OT_formation_remove(bpy.types.Operator):
    bl_idname = "advlighting.formation_remove"
    bl_label = "Remove Formation"
    def execute(self, context):
        sc = context.scene
        i = sc.adv_drone_formations_index
        if 0 <= i < len(sc.adv_drone_formations):
            sc.adv_drone_formations.remove(i)
            sc.adv_drone_formations_index = max(0, i-1)
        return {'FINISHED'}

class ADVLIGHTING_OT_group_add(bpy.types.Operator):
    bl_idname = "advlighting.group_add"
    bl_label = "Add Group"
    def execute(self, context):
        sc = context.scene
        if not sc.adv_drone_formations: return {'CANCELLED'}
        f = sc.adv_drone_formations[sc.adv_drone_formations_index]
        g = f.groups.add()
        g.name = f"Group {len(f.groups) + 1}"
        f.groups_index = len(f.groups)-1
        return {'FINISHED'}

class ADVLIGHTING_OT_group_remove(bpy.types.Operator):
    bl_idname = "advlighting.group_remove"
    bl_label = "Remove Group"
    def execute(self, context):
        sc = context.scene
        if not sc.adv_drone_formations: return {'CANCELLED'}
        f = sc.adv_drone_formations[sc.adv_drone_formations_index]
        i = f.groups_index
        if 0 <= i < len(f.groups):
            f.groups.remove(i)
            f.groups_index = max(0, i-1)
        return {'FINISHED'}

class ADVLIGHTING_OT_group_add_selected(bpy.types.Operator):
    bl_idname = "advlighting.group_add_selected"
    bl_label = "Add Selected"
    bl_description = "Add selected md_sphere objects to the active group"
    def execute(self, context):
        sc = context.scene
        if not sc.adv_drone_formations: return {'CANCELLED'}
        f = sc.adv_drone_formations[sc.adv_drone_formations_index]
        if not f.groups: return {'CANCELLED'}
        g = f.groups[f.groups_index]
        
        existing = {d.object_name for d in g.drones}
        added = 0
        for o in context.selected_objects:
            if o.type == 'MESH' and o.get("md_sphere") and o.name not in existing:
                ref = g.drones.add()
                ref.object_name = o.name
                added += 1
        
        if added > 0: self.report({'INFO'}, f"Added {added} drones")
        return {'FINISHED'}

class ADVLIGHTING_OT_group_remove_selected(bpy.types.Operator):
    bl_idname = "advlighting.group_remove_selected"
    bl_label = "Remove Selected"
    def execute(self, context):
        sc = context.scene
        if not sc.adv_drone_formations: return {'CANCELLED'}
        f = sc.adv_drone_formations[sc.adv_drone_formations_index]
        if not f.groups: return {'CANCELLED'}
        g = f.groups[f.groups_index]
        
        selected = {o.name for o in context.selected_objects}
        removed = 0
        for i in range(len(g.drones) - 1, -1, -1):
            if g.drones[i].object_name in selected:
                g.drones.remove(i)
                removed += 1
        
        if removed > 0: self.report({'INFO'}, f"Removed {removed} drones")
        return {'FINISHED'}

class ADVLIGHTING_OT_group_select(bpy.types.Operator):
    bl_idname = "advlighting.group_select"
    bl_label = "Select Group"
    additive: BoolProperty(default=False)
    def execute(self, context):
        sc = context.scene
        if not sc.adv_drone_formations: return {'CANCELLED'}
        f = sc.adv_drone_formations[sc.adv_drone_formations_index]
        if not f.groups: return {'CANCELLED'}
        g = f.groups[f.groups_index]
        
        if not self.additive:
            bpy.ops.object.select_all(action='DESELECT')
            
        for ref in g.drones:
            obj = bpy.data.objects.get(ref.object_name)
            if obj:
                obj.select_set(True)
        return {'FINISHED'}
    
class ADVLIGHTING_OT_write_groups_to_mesh(bpy.types.Operator):
    bl_idname = "advlighting.write_groups_to_mesh"
    bl_label = "Write Groups to Mesh"
    bl_description = "Agnostically saves Formation JSON data to the Formation Meshes"
    
    def execute(self, context):
        sc = context.scene
        mesh_data_payloads = {} 
        
        # --- GET FILE PREFIX ---
        blend_filename = bpy.path.basename(bpy.data.filepath)
        prefix = os.path.splitext(blend_filename)[0] if blend_filename else "Untitled"
        
        # 1. Look at UI and Trace Constraint Hierarchy
        for f in sc.adv_drone_formations:
            # Prevent double-prefixing if the user re-exports from a master file
            form_key = f.name if f.name.startswith(f"{prefix}_") else f"{prefix}_{f.name}"
            
            for g in f.groups:
                for d_ref in g.drones:
                    drone = bpy.data.objects.get(d_ref.object_name)
                    if not drone: continue
                    
                    for c in drone.constraints:
                        if c.type == 'COPY_LOCATION' and getattr(c, 'target', None):
                            tgt = c.target
                            
                            if tgt.type == 'EMPTY':
                                formation_obj = None
                                
                                if tgt.parent and tgt.parent.type == 'MESH':
                                    formation_obj = tgt.parent
                                else:
                                    for ec in tgt.constraints:
                                        if getattr(ec, 'target', None) and ec.target.type == 'MESH':
                                            formation_obj = ec.target
                                            break
                                
                                if formation_obj:
                                    if formation_obj not in mesh_data_payloads: mesh_data_payloads[formation_obj] = {}
                                    if form_key not in mesh_data_payloads[formation_obj]: mesh_data_payloads[formation_obj][form_key] = {}
                                    if g.name not in mesh_data_payloads[formation_obj][form_key]: mesh_data_payloads[formation_obj][form_key][g.name] = []
                                        
                                    if tgt.name not in mesh_data_payloads[formation_obj][form_key][g.name]:
                                        mesh_data_payloads[formation_obj][form_key][g.name].append(tgt.name)
                                
        # 2. Package JSON to Custom Properties
        for obj, payload in mesh_data_payloads.items():
            existing = {}
            if "adv_group_metadata" in obj:
                try: existing = json.loads(obj["adv_group_metadata"])
                except: pass
            existing.update(payload)
            obj["adv_group_metadata"] = json.dumps(existing)
            
        self.report({'INFO'}, f"Wrote group JSON metadata to {len(mesh_data_payloads)} Formation Meshes.")
        return {'FINISHED'}


class ADVLIGHTING_OT_rebuild_groups_from_mesh(bpy.types.Operator):
    bl_idname = "advlighting.rebuild_groups_from_mesh"
    bl_label = "Rebuild Groups from Meshes"
    bl_description = "Agnostically reads JSON metadata and timeline influence to reconstruct the UI"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        sc = context.scene
        drones = [o for o in bpy.data.objects if o.get("md_sphere") and o.type=='MESH']
        
        formation_triggers = {} 
        formation_payloads = {} 
        
        # 1. Reverse Lookup & Chronological Check
        for d in drones:
            for c in d.constraints:
                if c.type == 'COPY_LOCATION' and getattr(c, 'target', None):
                    tgt = c.target
                    
                    if tgt.type == 'EMPTY':
                        formation_obj = None
                        
                        # Apply the same Empty-to-Mesh detective logic
                        if tgt.parent and tgt.parent.type == 'MESH':
                            formation_obj = tgt.parent
                        else:
                            for ec in tgt.constraints:
                                if getattr(ec, 'target', None) and ec.target.type == 'MESH':
                                    formation_obj = ec.target
                                    break
                        
                        if formation_obj and "adv_group_metadata" in formation_obj:
                            try: meta = json.loads(formation_obj["adv_group_metadata"])
                            except: continue
                                
                            trigger_frame = 999999
                            if d.animation_data and d.animation_data.action:
                                # --- FIXED: Strictly use the correct data path ---
                                fc = d.animation_data.action.fcurves.find(f'constraints["{c.name}"].influence')
                                if fc:
                                    for kp in fc.keyframe_points:
                                        if kp.co[1] > 0.99:
                                            trigger_frame = min(trigger_frame, int(kp.co[0]))
                                            
                            for form_name, groups in meta.items():
                                if form_name not in formation_triggers: formation_triggers[form_name] = trigger_frame
                                else: formation_triggers[form_name] = min(formation_triggers[form_name], trigger_frame)
                                    
                                if form_name not in formation_payloads: formation_payloads[form_name] = {}
                                    
                                for grp_name, empties in groups.items():
                                    if tgt.name in empties:
                                        if grp_name not in formation_payloads[form_name]:
                                            formation_payloads[form_name][grp_name] = []
                                        if d.name not in formation_payloads[form_name][grp_name]:
                                            formation_payloads[form_name][grp_name].append(d.name)
        
        # 2. Rebuild the UI 
        sorted_forms = sorted(formation_payloads.keys(), key=lambda k: formation_triggers.get(k, 999999))
        
        for form_name in sorted_forms:
            existing_f = next((f for f in sc.adv_drone_formations if f.name == form_name), None)
            if not existing_f:
                existing_f = sc.adv_drone_formations.add()
                existing_f.name = form_name
                
            payload_groups = formation_payloads[form_name]
            for grp_name, drone_names in payload_groups.items():
                existing_g = next((g for g in existing_f.groups if g.name == grp_name), None)
                if not existing_g:
                    existing_g = existing_f.groups.add()
                    existing_g.name = grp_name
                    
                for d_name in drone_names:
                    if not any(d.object_name == d_name for d in existing_g.drones):
                        d_item = existing_g.drones.add()
                        d_item.object_name = d_name
                        
        self.report({'INFO'}, f"Successfully recovered and sorted {len(sorted_forms)} Formations!")
        return {'FINISHED'}
    
    
classes = (
    ADVLIGHTING_OT_formation_add, ADVLIGHTING_OT_formation_remove,
    ADVLIGHTING_OT_group_add, ADVLIGHTING_OT_group_remove,
    ADVLIGHTING_OT_group_add_selected, ADVLIGHTING_OT_group_remove_selected,
    ADVLIGHTING_OT_group_select, ADVLIGHTING_OT_write_groups_to_mesh, ADVLIGHTING_OT_rebuild_groups_from_mesh,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)