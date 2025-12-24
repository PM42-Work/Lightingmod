import bpy
import mathutils
from bpy_extras import view3d_utils

class EffectorEvaluator:
    """
    Centralized logic for calculating a factor 't' (0.0 to 1.0)
    based on spatial modes (Linear, Radial 2D, Radial 3D).
    """
    def __init__(self, context, mode, p0, p1):
        self.mode = mode
        self.context = context
        self.p0 = mathutils.Vector(p0)
        self.p1 = mathutils.Vector(p1)
        self.vec = self.p1 - self.p0
        self.length = self.vec.length
        
        # Linear: Pre-calculate Denominator
        self.denom = self.vec.dot(self.vec)
        if self.denom == 0.0: self.denom = 1.0
        
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
        """Returns t clamped between 0.0 and 1.0 based on object position"""
        t = 0.0
        
        if self.mode == 'LINEAR':
            # Project vector onto line
            t = (world_pos - self.p0).dot(self.vec) / self.denom
            
        elif self.mode == 'RADIAL_2D':
            if self.co0_2d:
                co_obj = view3d_utils.location_3d_to_region_2d(
                    self.context.region, self.context.region_data, world_pos
                )
                if co_obj:
                    t = (co_obj - self.co0_2d).length / self.radius_2d
                    
        else: # RADIAL_3D (Default)
            dist = (world_pos - self.p0).length
            max_dist = self.length if self.length > 0 else 1.0
            t = dist / max_dist
            
        return max(0.0, min(1.0, t))