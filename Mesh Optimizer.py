import bpy
import bmesh
import time

bl_info = {
    "name": "mesh optimizer",
    "author": "Eleeter",
    "version": (1, 2, 0),
    "blender": (4, 1, 0),
    "location": "view3d > sidebar > optimizer",
    "category": "mesh",
}

build_version = "industrial_stable_build"
debug_mode = False
log_prefix = "[heavy_opt]"

def log_debug(msg):
    if debug_mode:
        print(f"{log_prefix} {msg}")

def set_object_mode():
    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except:
        pass

def set_edit_mode():
    try:
        bpy.ops.object.mode_set(mode='EDIT')
    except:
        pass

def fetch_active_mesh(context):
    obj = context.active_object
    return obj if obj and obj.type == 'MESH' else None

def get_time():
    return time.time()

def run_weld_cleanup(obj, distance=0.0001):
    set_edit_mode()
    bm = bmesh.from_edit_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=distance)
    bmesh.update_edit_mesh(obj.data)
    set_object_mode()

def run_decimation(obj, ratio):
    mod = obj.modifiers.new(name="heavy_dec", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    if obj.data.uv_layers.active:
        mod.delimit = {'UV'}
    bpy.ops.object.modifier_apply(modifier=mod.name)

def run_shade_smooth(obj):
    bpy.ops.object.shade_smooth()

def run_angle_shading(obj):
    try:
        mod = obj.modifiers.new(name="smooth_angle", type='NODES')
        group = bpy.data.node_groups.get("Smooth by Angle")
        if not group:
            bpy.ops.object.modifier_add_node_group(
                asset_library_type='ESSENTIALS', 
                asset_identifier="Smooth by Angle"
            )
        else:
            mod.node_group = group
    except Exception as e:
        log_debug(f"shading skipped: {e}")

def get_mesh_health(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    health = {
        'non_manifold': len([e for e in bm.edges if not e.is_manifold]),
        'isolated_verts': len([v for v in bm.verts if not v.link_edges]),
        'zero_area': len([f for f in bm.faces if f.calc_area() <= 0.0])
    }
    bm.free()
    return health

class MESH_OT_heavy_repair(bpy.types.Operator):
    bl_idname = "mesh.heavy_repair"
    bl_label = "repair topology"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        set_edit_mode()
        bm = bmesh.from_edit_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        isolated = [v for v in bm.verts if not v.link_edges]
        bmesh.ops.delete(bm, geom=isolated, context='VERTS')
        zeros = [f for f in bm.faces if f.calc_area() <= 0.0]
        bmesh.ops.dissolve_faces(bm, faces=zeros)
        bmesh.update_edit_mesh(obj.data)
        set_object_mode()
        return {'FINISHED'}

class mesh_ot_optimizer_core(bpy.types.Operator):
    bl_idname = "mesh.heavy_optimize_final"
    bl_label = "optimize mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        start_mark = get_time()
        target = fetch_active_mesh(context)
        if not target:
            self.report({'ERROR'}, "no mesh selected")
            return {'CANCELLED'}

        set_object_mode()
        target_ratio = context.scene.heavy_opt_ratio
        run_weld_cleanup(target)
        if target_ratio < 1.0:
            run_decimation(target, target_ratio)
        run_shade_smooth(target)
        run_angle_shading(target)

        elapsed = round(get_time() - start_mark, 2)
        self.report({'INFO'}, f"done: {elapsed}s")
        return {'FINISHED'}

class view3d_pt_optimizer_ui(bpy.types.Panel):
    bl_label = "Mesh Optimizer"
    bl_idname = "VIEW3D_PT_optimizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Optimizer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        target = context.active_object

        if target and target.type == 'MESH':
            
           
            box = layout.box()
            split = box.split(factor=0.5)
            col = split.column()
            col.label(text="Verts:", icon='VERTEXSEL')
            col.label(text="Tris:", icon='FACESEL')
            col.label(text="Polys:", icon='MESH_DATA')
            
            col = split.column()
            col.label(text=f"{len(target.data.vertices):,}")
            col.label(text=f"{sum(len(p.vertices) - 2 for p in target.data.polygons):,}")
            col.label(text=f"{len(target.data.polygons):,}")
            
            layout.separator()
            
            
            health = get_mesh_health(target)
            bad_news = health['non_manifold'] + health['isolated_verts'] + health['zero_area']
            
            diag = layout.box().column(align=True)
            diag.label(text="Mesh integrity", icon='GHOST_ENABLED')
            diag.separator()
            
            if bad_news == 0:
                diag.label(text="status: clean", icon='CHECKMARK')
            else:
                if health['non_manifold'] > 0:
                    diag.label(text=f"Non-manifold: {health['non_manifold']}", icon='ERROR')
                if health['isolated_verts'] > 0:
                    diag.label(text=f"isolated verts: {health['isolated_verts']}", icon='DOT')
                
                diag.separator()
                diag.operator("mesh.heavy_repair", text="fix topology", icon='TOOL_SETTINGS')

            # settings
            engine = layout.box().column(align=True)
            engine.label(text="Optimization Settings", icon='SETTINGS')
            engine.separator()
            
            engine.prop(scene, "heavy_opt_ratio", text="density", slider=True)
            
            curr = len(target.data.polygons)
            proj = int(curr * scene.heavy_opt_ratio)
            row = engine.row(align=True)
            row.label(text=f"Target: {proj:,} p", icon='DOT')
            row.label(text=f"Saving: {curr-proj:,}", icon='REMOVE')
            
            
            view = layout.column(align=True)
            view.label(text="Viewport Overlays", icon='VIEW3D')
            row = view.row(align=True)
            row.prop(context.space_data.overlay, "show_wireframes", text="Wire", toggle=True)
            row.prop(context.space_data.overlay, "show_face_orientation", text="Face Orientation", toggle=True)
            
            layout.separator()
            
            
            row = layout.row()
            row.scale_y = 2.0
            row.operator("mesh.heavy_optimize_final", text="Run Optimizer", icon='MODIFIER_ON')
        else:
            layout.label(text="select a mesh", icon='ERROR')

classes = (
    MESH_OT_heavy_repair,
    mesh_ot_optimizer_core,
    view3d_pt_optimizer_ui,
)

def register():
    bpy.types.Scene.heavy_opt_ratio = bpy.props.FloatProperty(
        name="ratio", default=0.2, min=0.001, max=1.0
    )
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.heavy_opt_ratio

if __name__ == "__main__":
    register()