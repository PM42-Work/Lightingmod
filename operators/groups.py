import bpy
from bpy.props import BoolProperty

class LIGHTINGMOD_OT_formation_add(bpy.types.Operator):
    bl_idname = "lightingmod.formation_add"
    bl_label = "Add Formation"
    def execute(self, context):
        sc = context.scene
        f = sc.drone_formations.add()
        f.name = f"Formation {len(sc.drone_formations) + 1}"
        sc.drone_formations_index = len(sc.drone_formations)-1
        return {'FINISHED'}

class LIGHTINGMOD_OT_formation_remove(bpy.types.Operator):
    bl_idname = "lightingmod.formation_remove"
    bl_label = "Remove Formation"
    def execute(self, context):
        sc = context.scene
        i = sc.drone_formations_index
        if 0 <= i < len(sc.drone_formations):
            sc.drone_formations.remove(i)
            sc.drone_formations_index = max(0, i-1)
        return {'FINISHED'}

class LIGHTINGMOD_OT_group_add(bpy.types.Operator):
    bl_idname = "lightingmod.group_add"
    bl_label = "Add Group"
    def execute(self, context):
        sc = context.scene
        if not sc.drone_formations: return {'CANCELLED'}
        f = sc.drone_formations[sc.drone_formations_index]
        g = f.groups.add()
        g.name = f"Group {len(f.groups) + 1}"
        f.groups_index = len(f.groups)-1
        return {'FINISHED'}

class LIGHTINGMOD_OT_group_remove(bpy.types.Operator):
    bl_idname = "lightingmod.group_remove"
    bl_label = "Remove Group"
    def execute(self, context):
        sc = context.scene
        if not sc.drone_formations: return {'CANCELLED'}
        f = sc.drone_formations[sc.drone_formations_index]
        i = f.groups_index
        if 0 <= i < len(f.groups):
            f.groups.remove(i)
            f.groups_index = max(0, i-1)
        return {'FINISHED'}

class LIGHTINGMOD_OT_group_add_selected(bpy.types.Operator):
    bl_idname = "lightingmod.group_add_selected"
    bl_label = "Add Selected"
    bl_description = "Add selected md_sphere objects to the active group"
    def execute(self, context):
        sc = context.scene
        if not sc.drone_formations: return {'CANCELLED'}
        f = sc.drone_formations[sc.drone_formations_index]
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

class LIGHTINGMOD_OT_group_remove_selected(bpy.types.Operator):
    bl_idname = "lightingmod.group_remove_selected"
    bl_label = "Remove Selected"
    def execute(self, context):
        sc = context.scene
        if not sc.drone_formations: return {'CANCELLED'}
        f = sc.drone_formations[sc.drone_formations_index]
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

class LIGHTINGMOD_OT_group_select(bpy.types.Operator):
    bl_idname = "lightingmod.group_select"
    bl_label = "Select Group"
    additive: BoolProperty(default=False)
    def execute(self, context):
        sc = context.scene
        if not sc.drone_formations: return {'CANCELLED'}
        f = sc.drone_formations[sc.drone_formations_index]
        if not f.groups: return {'CANCELLED'}
        g = f.groups[f.groups_index]
        
        if not self.additive:
            bpy.ops.object.select_all(action='DESELECT')
            
        for ref in g.drones:
            obj = bpy.data.objects.get(ref.object_name)
            if obj:
                obj.select_set(True)
        return {'FINISHED'}

# --- REGISTRATION ---
classes = (
    LIGHTINGMOD_OT_formation_add,
    LIGHTINGMOD_OT_formation_remove,
    LIGHTINGMOD_OT_group_add,
    LIGHTINGMOD_OT_group_remove,
    LIGHTINGMOD_OT_group_add_selected,
    LIGHTINGMOD_OT_group_remove_selected,
    LIGHTINGMOD_OT_group_select,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)