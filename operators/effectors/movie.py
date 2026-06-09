import bpy
import numpy as np
import os
import mathutils
import bpy_extras
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty


try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

class ADVLIGHTING_OT_load_movie_clip(bpy.types.Operator, ImportHelper):
    bl_idname = "advlighting.load_movie_clip"
    bl_label = "Import Video"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Restrict the file browser to common video formats
    filter_glob: StringProperty(
        default="*.mp4;*.avi;*.mov;*.mkv;*.webm", 
        options={'HIDDEN'}, 
        maxlen=255
    )

    def execute(self, context):
        sc = context.scene
        if os.path.exists(self.filepath):
            # Load the file into Blender's MovieClip data block
            clip = bpy.data.movieclips.load(self.filepath)
            sc.adv_movie_clip = clip
            self.report({'INFO'}, f"Loaded Video: {clip.name}")
        return {'FINISHED'}

class ADVLIGHTING_OT_spawn_movie_camera(bpy.types.Operator):
    bl_idname = "advlighting.spawn_movie_camera"
    bl_label = "Spawn Movie Camera"
    
    def execute(self, context):
        sc = context.scene
        if not sc.adv_movie_clip:
            self.report({'ERROR'}, "Select or Open a Video Clip first!")
            return {'CANCELLED'}
            
        cam_data = bpy.data.cameras.new(name="Movie_Cam_Data")
        cam_data.show_background_images = True
        bg = cam_data.background_images.new()
        
        # Assign the Movie Clip so it plays in the viewport
        bg.source = 'MOVIE_CLIP'
        bg.clip = sc.adv_movie_clip
        bg.alpha = 0.8  
        bg.display_depth = 'FRONT'
        bg.frame_method = 'FIT'
        
        cam_obj = bpy.data.objects.new("Movie_Projector", cam_data)
        cam_obj["is_adv_movie_cam"] = True 
        
        context.scene.collection.objects.link(cam_obj)
        
        if context.region_data and context.area.type == 'VIEW_3D':
            cam_obj.matrix_world = context.region_data.view_matrix.inverted()
            context.space_data.camera = cam_obj
            context.region_data.view_perspective = 'CAMERA'
            
        sc.adv_movie_camera = cam_obj
        self.report({'INFO'}, "Movie Camera spawned! Align it to target your drones.")
        return {'FINISHED'}


class ADVLIGHTING_OT_remove_movie_cameras(bpy.types.Operator):
    bl_idname = "advlighting.remove_movie_cameras"
    bl_label = "Clear All Movie Cameras"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        count = 0
        for obj in list(bpy.data.objects):
            if "is_adv_movie_cam" in obj:
                cam_data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if cam_data:
                    bpy.data.cameras.remove(cam_data, do_unlink=True)
                count += 1
                
        context.scene.adv_movie_camera = None
        self.report({'INFO'}, f"Deleted {count} Movie Cameras")
        return {'FINISHED'}


class ADVLIGHTING_OT_movie_sampler(bpy.types.Operator):
    bl_idname = "advlighting.movie_sampler"
    bl_label = "Apply Movie Projector"

    def execute(self, context):
        if not HAS_OPENCV:
            self.report({'ERROR'}, "OpenCV not found. Run dependencies setup.")
            return {'CANCELLED'}

        sc = context.scene
        cam_obj = sc.adv_movie_camera
        clip_data = sc.adv_movie_clip
        
        if not cam_obj or not clip_data:
            self.report({'ERROR'}, "Missing Movie Camera or Video Clip.")
            return {'CANCELLED'}
            
        path = bpy.path.abspath(clip_data.filepath)
        if not os.path.exists(path):
            self.report({'ERROR'}, "Video file missing from disk.")
            return {'CANCELLED'}
            
        # Initialize OpenCV Video Reader
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self.report({'ERROR'}, "Failed to open video file with OpenCV.")
            return {'CANCELLED'}
            
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        start, end = sc.adv_effector_start, sc.adv_effector_end
        frames = list(range(start, end + 1))
        prop_name = f"Layer_{int(sc.adv_effector_target_layer)+1}"
        
        # Gather Drones
        objs = []
        if sc.adv_effector_selection_mode == 'GROUP' and sc.adv_drone_formations:
             if sc.adv_drone_formations[sc.adv_drone_formations_index].groups:
                 g = sc.adv_drone_formations[sc.adv_drone_formations_index].groups[sc.adv_drone_formations[sc.adv_drone_formations_index].groups_index]
                 objs = [bpy.data.objects.get(d.object_name) for d in g.drones if bpy.data.objects.get(d.object_name)]
        else:
             objs = context.selected_objects

        drones = [o for o in objs if o.get("md_sphere") and o.type=='MESH' and "Absolute_Position" in o.keys()]
        if not drones:
            self.report({'ERROR'}, "No valid drones found.")
            return {'CANCELLED'}
        
        drone_paths = {}
        for d in drones:
            px, py, pz = d["Absolute_Position"]
            anim = getattr(d, "animation_data", None)
            fcurves = [anim.action.fcurves.find('["Absolute_Position"]', index=i) if anim and anim.action else None for i in range(3)]
            
            drone_paths[d.name] = {}
            for f in frames:
                x = fcurves[0].evaluate(f) if fcurves[0] else px
                y = fcurves[1].evaluate(f) if fcurves[1] else py
                z = fcurves[2].evaluate(f) if fcurves[2] else pz
                drone_paths[d.name][f] = mathutils.Vector((x,y,z))
                
        px_coords = np.zeros((len(frames), len(drones), 2), dtype=np.int32)
        valid_mask = np.zeros((len(frames), len(drones)), dtype=bool)
        
        # Dynamic Aspect Ratio Correction
        render = sc.render
        cam_aspect = (render.resolution_x * render.pixel_aspect_x) / max(1.0, (render.resolution_y * render.pixel_aspect_y))
        img_aspect = w / max(1.0, h)
        
        wm = context.window_manager
        wm.progress_begin(0, len(frames) * 2) # 2 phases: Matrix calc, then Video extraction
        
        # Phase 1: 3D to 2D Projection
        for f_idx, f in enumerate(frames):
            sc.frame_set(f) 
            for d_idx, d in enumerate(drones):
                p = drone_paths[d.name][f]
                co2d = bpy_extras.object_utils.world_to_camera_view(sc, cam_obj, p)
                
                if co2d.z > 0: 
                    u = co2d.x
                    v = co2d.y
                    
                    if cam_aspect > img_aspect:
                        u = (u - 0.5) * (cam_aspect / img_aspect) + 0.5
                    else:
                        v = (v - 0.5) * (img_aspect / cam_aspect) + 0.5
                        
                    if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                        ix = int(u * (w - 1))
                        iy = int((1.0 - v) * (h - 1)) 
                        if 0 <= ix < w and 0 <= iy < h:
                            px_coords[f_idx, d_idx, 0] = ix
                            px_coords[f_idx, d_idx, 1] = iy
                            valid_mask[f_idx, d_idx] = True
            wm.progress_update(f_idx)
            
        # Phase 2: OpenCV Pixel Extraction
        sampled_rgb = np.zeros((len(frames), len(drones), 3), dtype=np.float32)
        
        for f_idx, f in enumerate(frames):
            # Calculate which frame to pull from the video (Loops automatically if too short)
            vid_frame = (f - start) % total_video_frames
            cap.set(cv2.CAP_PROP_POS_FRAMES, vid_frame)
            
            ret, frame = cap.read()
            if not ret: continue
            
            mask = valid_mask[f_idx, :]
            if np.any(mask):
                xc, yc = px_coords[f_idx, mask, 0], px_coords[f_idx, mask, 1]
                # OpenCV uses BGR. We extract the pixels and slice [::-1] to flip to RGB!
                bgr_pixels = frame[yc, xc]
                rgb_pixels = bgr_pixels[:, ::-1] / 255.0
                sampled_rgb[f_idx, mask] = rgb_pixels
                
            wm.progress_update(len(frames) + f_idx)
            
        cap.release()
        wm.progress_end()
        
        # Gamma Correction: Convert sRGB video to Blender's Linear color space
        linear_rgb = np.where(sampled_rgb <= 0.04045, sampled_rgb / 12.92, ((sampled_rgb + 0.055) / 1.055) ** 2.4)
        
        data_path = f'["{prop_name}"]'
        frames_np = np.array(frames, dtype=np.float32)
        
        # Phase 3: Splicing Keyframes safely
        for d_idx, d in enumerate(drones):
            if prop_name not in d.keys(): d[prop_name] = [0.0, 0.0, 0.0, 1.0]
            if not d.animation_data: d.animation_data_create()
            if not d.animation_data.action: d.animation_data.action = bpy.data.actions.new(name=f"{d.name}_Anim")
            action = d.animation_data.action
            
            for i in range(3):
                fc = action.fcurves.find(data_path=data_path, index=i)
                if not fc: 
                    fc = action.fcurves.new(data_path=data_path, index=i)
                    existing_pts = np.empty((0, 2), dtype=np.float32)
                else:
                    num_existing = len(fc.keyframe_points)
                    if num_existing > 0:
                        coords = np.zeros(num_existing * 2, dtype=np.float32)
                        fc.keyframe_points.foreach_get('co', coords)
                        existing_pts = coords.reshape((num_existing, 2))
                        
                        # Preserve data outside of start/end range
                        mask = (existing_pts[:, 0] < start) | (existing_pts[:, 0] > end)
                        existing_pts = existing_pts[mask]
                    else:
                        existing_pts = np.empty((0, 2), dtype=np.float32)
                
                col_arr = linear_rgb[:, d_idx, :]
                new_pts = np.column_stack((frames_np, col_arr[:, i]))
                
                combined_pts = np.vstack((existing_pts, new_pts))
                combined_pts = combined_pts[combined_pts[:, 0].argsort()]
                
                fc.keyframe_points.clear() 
                num_points = len(combined_pts)
                fc.keyframe_points.add(num_points)
                fc.keyframe_points.foreach_set('co', combined_pts.flatten())
                fc.update()
                
                bool_arr = [False] * num_points
                fc.keyframe_points.foreach_set('select_control_point', bool_arr)
                fc.keyframe_points.foreach_set('select_left_handle', bool_arr)
                fc.keyframe_points.foreach_set('select_right_handle', bool_arr)
                
        self.report({'INFO'}, "Movie Projection Baked Successfully!")
        return {'FINISHED'}