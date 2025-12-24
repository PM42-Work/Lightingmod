import bpy
import mathutils
from bpy_extras import view3d_utils

class EffectorEvaluator:
    """
    Centralized logic for calculating 't' (0.0-1.0)
    Supports: Linear, Split Linear, Radial 2D/3D, and Curves.
    """
    def __init__(self, context, mode, p0, p1, curve_obj=None, curve_radius=0.5, curve_mode='PER_CURVE'):
        self.mode = mode
        self.context = context
        self.p0 = mathutils.Vector(p0)
        self.p1 = mathutils.Vector(p1)
        self.vec = self.p1 - self.p0
        self.length = self.vec.length
        
        # Linear/Split: Pre-calculate Denominator
        self.denom = self.vec.dot(self.vec)
        if self.denom == 0.0: self.denom = 1.0
        
        # Curve Data
        self.curve_obj = curve_obj
        self.curve_radius = curve_radius
        self.curve_mode = curve_mode

        # Radial 2D: Pre-calculate View Data
        self.co0_2d = None
        self.radius_2d = 1.0
        if self.mode == 'RADIAL_2D':
            region = context.region
            rv3d = context.region_data
            if region and rv3d:
                self.co0_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.p0)
                co1_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.p1)
                if self.co0_2d and co1_2d:
                    self.radius_2d = (co1_2d - self.co0_2d).length
                if self.radius_2d == 0.0: self.radius_2d = 1.0

    def get_t(self, world_pos):
        """
        Returns (t, valid). 
        t is clamped 0.0-1.0. 
        valid is False if point is outside curve radius (only used in CURVE mode).
        """
        t = 0.0
        valid = True

        if self.mode == 'LINEAR':
            # Project vector onto line
            t = (world_pos - self.p0).dot(self.vec) / self.denom
            
        elif self.mode == 'SPLIT':
            # Symmetrical gradient from center (p0)
            proj = (world_pos - self.p0).dot(self.vec) / self.denom
            t = abs(proj)
            
        elif self.mode == 'RADIAL_2D':
            if self.co0_2d:
                co_obj = view3d_utils.location_3d_to_region_2d(
                    self.context.region, self.context.region_data, world_pos
                )
                if co_obj:
                    t = (co_obj - self.co0_2d).length / self.radius_2d
                    
        elif self.mode == 'CURVE':
            t, valid = self._evaluate_curve(world_pos)
            
        else: # RADIAL_3D (Explicit)
            dist = (world_pos - self.p0).length
            max_dist = self.length if self.length > 0 else 1.0
            t = dist / max_dist
            
        return max(0.0, min(1.0, t)), valid

    def _evaluate_curve(self, pos):
        """Helper to find closest point on curve and return t"""
        if not self.curve_obj or self.curve_obj.type != 'CURVE': 
            return 0.0, False
            
        deps = self.context.evaluated_depsgraph_get()
        eval_obj = self.curve_obj.evaluated_get(deps)
        mesh = eval_obj.to_mesh()
        mw = eval_obj.matrix_world
        verts = [mw @ v.co for v in mesh.vertices]
        edges = mesh.edges
        
        # Build connected paths
        paths = []
        visited = set()
        for e in edges:
            if e.index in visited: continue
            path = [verts[e.vertices[0]], verts[e.vertices[1]]]
            visited.add(e.index)
            growing = True
            while growing:
                growing = False
                for e2 in edges:
                    if e2.index in visited: continue
                    v0, v1 = e2.vertices
                    if (path[-1]-verts[v0]).length < 1e-6:
                        path.append(verts[v1]); visited.add(e2.index); growing=True
                    elif (path[-1]-verts[v1]).length < 1e-6:
                        path.append(verts[v0]); visited.add(e2.index); growing=True
            paths.append(path)
            
        eval_obj.to_mesh_clear()
        if not paths: return 0.0, False

        # Find closest point on all paths
        best_t, min_dist = 0.0, None
        total_len = sum(sum((p[i+1]-p[i]).length for i in range(len(p)-1)) for p in paths) or 1.0
        acc_len_total = 0.0
        
        for path in paths:
            curve_len = sum((path[i+1]-path[i]).length for i in range(len(path)-1))
            if curve_len == 0: continue
            acc_len_curve = 0.0
            for i in range(len(path)-1):
                a, b = path[i], path[i+1]
                ab = b-a
                ab_len2 = ab.length_squared
                if ab_len2 == 0: continue
                
                # Project point onto segment
                t_line = max(0.0, min(1.0, (pos-a).dot(ab)/ab_len2))
                dist = (a + t_line*ab - pos).length
                
                if dist <= self.curve_radius and (min_dist is None or dist < min_dist):
                    min_dist = dist
                    local_t = (acc_len_curve + t_line*ab.length) / curve_len
                    
                    if self.curve_mode == 'PER_CURVE':
                        best_t = local_t
                    else: # GLOBAL
                        best_t = (acc_len_total + t_line*ab.length) / total_len
                        
                acc_len_curve += ab.length
            acc_len_total += curve_len
            
        return best_t, (min_dist is not None)