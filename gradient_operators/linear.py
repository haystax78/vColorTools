"""
Linear gradient operator for vColGradient addon
Applies a linear gradient to vertex colors or sculpt mask
"""

import bpy
import gpu
import numpy as np
import time
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras import view3d_utils
from .. import utils

class VGRADIENT_OT_linear(bpy.types.Operator):
    """Apply a linear gradient to vertex colors between two points"""
    bl_idname = "vgradient.linear"
    bl_label = "Linear"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a linear gradient to vertex colors or sculpt mask. Hold Alt to apply as sculpt mask"
    
    # Class variables for drawing state
    _handle = None
    _draw_start_point = None
    _draw_screen_start = None
    _draw_end_point = None
    _draw_screen_end = None
    _draw_current_point = None
    _draw_preview_color = (1, 1, 1, 1)
    _draw_area = None
    _last_event = None
    _alt_pressed = False  # Track Alt key state at class level
    _gradient_reversed = False  # Track if gradient direction is reversed
    
    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)
        self._last_event = None
    
    @classmethod
    def cleanup(cls, context=None):
        """Remove draw handler and reset state"""
        try:
            if cls._handle is not None:
                bpy.types.SpaceView3D.draw_handler_remove(cls._handle, 'WINDOW')
        except:
            pass
        finally:
            cls._handle = None
            cls._draw_start_point = None
            cls._draw_screen_start = None
            cls._draw_end_point = None
            cls._draw_screen_end = None
            cls._draw_current_point = None
            cls._draw_preview_color = (1, 1, 1, 1)
            cls._draw_area = None
            cls._last_event = None  # Reset the event
            cls._gradient_reversed = False  # Reset gradient direction
            if context:
                try:
                    context.workspace.status_text_set(None)
                    context.area.tag_redraw()
                except:
                    pass
    
    @classmethod
    def draw_callback_px(cls, *args):
        """Draw the preview line and points"""
        try:
            # Get current context
            context = bpy.context
            if not cls._draw_area or context.area != cls._draw_area:
                return
                
            gpu.state.line_width_set(2)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            
            # Draw start point if we have one
            if cls._draw_screen_start:
                # Draw crosshair at start point
                shader.uniform_float("color", (1, 1, 1, 1))
                x, y = cls._draw_screen_start
                size = 10
                gpu.state.blend_set('ALPHA')
                batch = batch_for_shader(shader, 'LINES', {"pos": [
                    (x - size, y), (x + size, y),
                    (x, y - size), (x, y + size)
                ]})
                batch.draw(shader)
                
                # Draw line between start and current/end point
                if cls._draw_screen_end or cls._draw_current_point:
                    # Get the end point (either final end point or current mouse position)
                    if cls._draw_screen_end:
                        x2, y2 = cls._draw_screen_end
                    else:
                        x2, y2 = cls._draw_current_point
                    
                    # Get UI scale factor for consistent line thickness
                    ui_scale = utils.get_ui_scale(context)
                    
                    # Calculate direction vector for the line
                    dx = x2 - x
                    dy = y2 - y
                    length = math.sqrt(dx*dx + dy*dy)
                    
                    # Get perpendicular vector for thickness
                    if length > 0:
                        # Normalize and get perpendicular vector
                        dx, dy = dx/length, dy/length
                        # Perpendicular vector
                        px, py = -dy, dx
                    else:
                        px, py = 0, 1
                    
                    # Thickness of the line (in pixels)
                    thickness = 10 * ui_scale
                    
                    # Check if we're in mask mode
                    use_mask_mode = context.mode == 'SCULPT' and cls._alt_pressed
                    
                    if use_mask_mode:
                        # For mask mode, show a black-to-white gradient
                        # Create points along the line
                        num_segments = 20  # Number of segments to divide the line into
                        
                        # Create points along the line
                        line_points = []
                        for i in range(num_segments + 1):
                            t = i / num_segments
                            line_points.append((
                                x + t * (x2 - x),
                                y + t * (y2 - y)
                            ))
                        
                        # Draw each segment with its appropriate grayscale value
                        for i in range(len(line_points) - 1):
                            # Calculate the factor (0-1) for this segment
                            t = i / num_segments
                            
                            # For mask mode, invert the gradient direction (white to black)
                            # Then apply the gradient reversal if needed
                            t = 1.0 - t  # Invert for mask mode (white to black)
                            
                            # Reverse the factor if needed
                            if cls._gradient_reversed:
                                t = 1.0 - t
                            
                            # Create grayscale color
                            gray_value = t
                            mask_color = (gray_value, gray_value, gray_value, 0.8)
                            
                            # Set the color
                            shader.uniform_float("color", mask_color)
                            
                            p1 = line_points[i]
                            p2 = line_points[i + 1]
                            
                            # Create quad vertices for this segment
                            quad_verts = [
                                (p1[0] + px * thickness, p1[1] + py * thickness),
                                (p2[0] + px * thickness, p2[1] + py * thickness),
                                (p2[0] - px * thickness, p2[1] - py * thickness),
                                (p1[0] - px * thickness, p1[1] - py * thickness)
                            ]
                            
                            # Draw filled quad
                            batch = batch_for_shader(shader, 'TRI_FAN', {"pos": quad_verts})
                            batch.draw(shader)
                    else:
                        # Get the active gradient
                        gradient = utils.get_active_gradient(context)
                        
                        if gradient and len(gradient.colors) > 0:
                            # For gradient mode, we'll create a series of segments to show the gradient
                            num_segments = 20  # Number of segments to divide the line into
                            
                            # Create points along the line
                            line_points = []
                            for i in range(num_segments + 1):
                                t = i / num_segments
                                line_points.append((
                                    x + t * (x2 - x),
                                    y + t * (y2 - y)
                                ))
                            
                            # Draw each segment with its appropriate color
                            for i in range(len(line_points) - 1):
                                # Calculate the factor (0-1) for this segment
                                t = i / num_segments
                                
                                # Reverse the factor if needed
                                if cls._gradient_reversed:
                                    t = 1.0 - t
                                
                                # Get color from gradient (in linear space)
                                linear_color = utils.interpolate_gradient_color(gradient, t)
                                
                                # Convert from linear to sRGB for display
                                display_color = (utils.linear_to_srgb(linear_color[0]), 
                                               utils.linear_to_srgb(linear_color[1]), 
                                               utils.linear_to_srgb(linear_color[2]), 
                                               linear_color[3])
                                
                                # Set the color
                                shader.uniform_float("color", display_color)
                                
                                p1 = line_points[i]
                                p2 = line_points[i + 1]
                                
                                # Create quad vertices for this segment
                                quad_verts = [
                                    (p1[0] + px * thickness, p1[1] + py * thickness),
                                    (p2[0] + px * thickness, p2[1] + py * thickness),
                                    (p2[0] - px * thickness, p2[1] - py * thickness),
                                    (p1[0] - px * thickness, p1[1] - py * thickness)
                                ]
                                
                                # Draw filled quad
                                batch = batch_for_shader(shader, 'TRI_FAN', {"pos": quad_verts})
                                batch.draw(shader)
                    
            # Draw color preview circle
            if cls._draw_current_point:
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                
                # Get current mouse position
                x, y = cls._draw_current_point
                
                # Check if we're in mask mode using the class-level Alt state
                use_mask_mode = context.mode == 'SCULPT' and cls._alt_pressed
                
                if use_mask_mode:
                    # Draw split circle - white on top, black on bottom
                    radius = 10
                    segments = 32
                    half_segments = segments // 2
                    
                    # Create vertices for top (white) half
                    top_verts = [(x, y)]  # Center point
                    top_verts.extend([(x + radius * np.cos(angle), y + radius * np.sin(angle)) 
                                    for angle in [i * np.pi / half_segments for i in range(half_segments + 1)]])
                    
                    # Create vertices for bottom (black) half
                    bottom_verts = [(x, y)]  # Center point
                    bottom_verts.extend([(x + radius * np.cos(angle), y + radius * np.sin(angle)) 
                                       for angle in [i * np.pi / half_segments + np.pi for i in range(half_segments + 1)]])
                    
                    gpu.state.blend_set('ALPHA')
                    
                    # Draw white top half
                    shader.uniform_float("color", (1, 1, 1, 0.8))
                    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": top_verts})
                    batch.draw(shader)
                    
                    # Draw black bottom half
                    shader.uniform_float("color", (0, 0, 0, 0.8))
                    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": bottom_verts})
                    batch.draw(shader)
                    
                    # Draw circle outline
                    shader.uniform_float("color", (1, 1, 1, 1))
                    circle_verts = [(x + radius * np.cos(angle), y + radius * np.sin(angle)) 
                                   for angle in [i * 2 * np.pi / segments for i in range(segments)]]
                    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": circle_verts})
                    batch.draw(shader)
                else:
                    # Draw normal preview circle
                    shader.uniform_float("color", cls._draw_preview_color)
                    
                    # Draw filled circle
                    radius = 10
                    segments = 32
                    circle_verts = [(x + radius * np.cos(angle), y + radius * np.sin(angle)) 
                                   for angle in [i * 2 * np.pi / segments for i in range(segments)]]
                    
                    gpu.state.blend_set('ALPHA')
                    batch = batch_for_shader(shader, 'TRI_FAN', {
                        "pos": [(x, y)] + circle_verts
                    })
                    batch.draw(shader)
                    
                    # Draw circle outline
                    shader.uniform_float("color", (1, 1, 1, 1))
                    batch = batch_for_shader(shader, 'LINE_LOOP', {
                        "pos": circle_verts
                    })
                    batch.draw(shader)
                
                gpu.state.blend_set('NONE')
                gpu.state.line_width_set(1)
        except:
            cls.cleanup()
            return
    
    def get_surface_point(self, context, event):
        """Get the 3D point and normal on the surface under the mouse, or create a point in 3D space"""
        # Get the context arguments
        scene = context.scene
        region = context.region
        rv3d = context.region_data
        coord = event.mouse_region_x, event.mouse_region_y

        # Get the ray from the viewport and mouse
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray_target = ray_origin + view_vector
        
        # Do ray cast to find the hit point
        depsgraph = context.evaluated_depsgraph_get()
        result = scene.ray_cast(depsgraph, ray_origin, view_vector)
        
        if result[0]:  # Hit something
            return result[1], result[2]  # Return location and normal
        else:
            # If we didn't hit anything, create a point at a fixed distance from the camera
            # This allows placing points in empty space
            point = ray_origin + view_vector * 10.0  # 10 units from camera
            # Use a default normal facing the camera
            normal = -view_vector.normalized()
            return point, normal
    
    def get_snapped_point(self, context, event):
        """Get point snapped to 15 degree increments if Ctrl is held"""
        # Get the surface point under the mouse
        hit_point, hit_normal = self.get_surface_point(context, event)
        
        # If we don't have a start point yet or Ctrl is not held, return the point as is
        if not hasattr(self, 'start_point') or not event.ctrl:
            return hit_point, hit_normal
        
        # Get the region and region_data for screen space calculations
        region = context.region
        rv3d = context.region_data
        
        # Project points to screen space
        start_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.start_point)
        current_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, hit_point)
        
        if not start_2d or not current_2d:
            return hit_point, hit_normal
        
        # Calculate angle and distance in screen space
        delta = current_2d - start_2d
        distance = delta.length
        
        # Get current angle in degrees
        angle = np.degrees(np.arctan2(delta.y, delta.x))
        
        # Snap to nearest 15 degrees
        snapped_angle = round(angle / 15.0) * 15.0
        
        # Convert back to radians and calculate new screen point
        rad = np.radians(snapped_angle)
        x = start_2d.x + distance * np.cos(rad)
        y = start_2d.y + distance * np.sin(rad)
        snapped_2d = Vector((x, y))
        
        # Convert back to 3D space
        # First get the depth of the original hit point
        depth = view3d_utils.region_2d_to_vector_3d(region, rv3d, (current_2d.x, current_2d.y)).normalized()
        # Then use the new 2D coordinates with the same depth
        snapped_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, snapped_2d, depth)
        
        return snapped_3d, hit_normal

    def apply_gradient(self, context):
        """Apply the linear gradient based on projection onto line"""
        start_time = time.time()
        total_start = time.time()
        
        # Get list of objects to process
        objects = []
        if context.mode == 'SCULPT':
            objects = [context.active_object]
        elif context.mode == 'EDIT_MESH':
            # In Edit mode, only process the active object
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        else:  # Object mode
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
            
        if not objects:
            self.report({'WARNING'}, "No valid objects found")
            return {'CANCELLED'}
            
        # Create a custom event-like object with the alt state from class variable
        event_data = type('EventData', (), {'alt': self.__class__._alt_pressed})()
        
        # Check if we should use mask mode
        use_mask_mode, gradient = utils.apply_mask_mode(context, event_data)
        if not gradient:
            return
        
        # Get screen space option (with fallback for older files)
        use_screen_space = True  # Default to screen space for compatibility
        if hasattr(gradient, 'use_screen_space'):
            use_screen_space = gradient.use_screen_space
        
        # Process each object
        for obj in objects:
            mesh = obj.data
            
            # Handle either vertex colors or sculpt mask
            if use_mask_mode:
                # Ensure we're in sculpt mode
                if context.mode != 'SCULPT':
                    self.report({'WARNING'}, "Mask mode only works in sculpt mode")
                    return {'CANCELLED'}
                    
                # Initialize sculpt mask if needed
                if not obj.data.attributes.get(".sculpt_mask"):
                    mask_layer = obj.data.attributes.new(name=".sculpt_mask", type='FLOAT', domain='POINT')
                    # Initialize mask values to 0
                    mask_values = np.zeros(len(obj.data.vertices), dtype=np.float32)
                    mask_layer.data.foreach_set("value", mask_values)
                    obj.data.update()
                
                target_attribute = obj.data.attributes[".sculpt_mask"]
            else:
                # Get active vertex colors
                target_attribute = utils.ensure_vertex_color_attribute(obj)
                if not target_attribute:
                    self.report({'WARNING'}, f"Could not create or find a color attribute for object {obj.name}")
                    continue
                
                # Make sure the color attribute is active
                obj.data.attributes.active_color = target_attribute
            
            # Debug gradient colors - commented out
            # print(f"\nProcessing object: {obj.name}")
            # print("Gradient Debug:")
            # for i, color in enumerate(gradient.colors):
            #     print(f"Color {i}: {color.color}")
                
            # Get vertex positions and mask
            num_verts = len(mesh.vertices)
            verts = np.empty(num_verts * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", verts)
            verts = verts.reshape(-1, 3)
            
            # Transform to world space using optimized matrix multiplication
            matrix = np.array(obj.matrix_world)
            rotation = matrix[:3, :3]
            translation = matrix[:3, 3]
            verts = np.dot(verts, rotation.T) + translation
            
            # Debug information commented out
            # print("\nVertex Space Debug:")
            # print(f"Number of vertices: {len(verts)}")
            # print(f"Start point (world space): {self.start_point}")
            # print(f"End point (world space): {self.end_point}")
            # print(f"First vertex (world space): {verts[0]}")
            # print(f"Last vertex (world space): {verts[-1]}")
            
            # utils.print_timing(start_time, f"Get vertex positions for {obj.name}")
            start_time = time.time()
            
            # Get mask values if in sculpt mode and not in mask mode
            use_existing_mask = False
            mask_data = None
            if context.mode == 'SCULPT' and not use_mask_mode:
                # First try vertex paint mask
                if hasattr(obj.data, 'vertex_paint_mask') and obj.data.vertex_paint_mask is not None:
                    mask = obj.data.vertex_paint_mask
                    if hasattr(mask, 'data'):
                        use_existing_mask = True
                        mask_data = np.empty(num_verts, dtype=np.float32)
                        mask.data.foreach_get('value', mask_data)
                
                # Try attribute mask if vertex paint mask not available
                if not use_existing_mask:
                    mask = obj.data.attributes.get("mask")
                    if mask and hasattr(mask, 'data'):
                        use_existing_mask = True
                        mask_data = np.empty(num_verts, dtype=np.float32)
                        mask.data.foreach_get('value', mask_data)
                        
            # utils.print_timing(start_time, f"Get mask values for {obj.name}")
            start_time = time.time()
            
            # Get selected vertices in Edit mode
            selected_verts = None
            if context.mode == 'EDIT_MESH':
                selected_verts = utils.get_selected_vertices(obj)
                
            # Process vertices in chunks for better memory usage
            chunk_size = 100000  # Adjust based on available memory
            num_chunks = (num_verts + chunk_size - 1) // chunk_size
            
            # Pre-allocate output array
            if use_mask_mode:
                final_values = np.empty(num_verts, dtype=np.float32)
                # Get current mask values
                target_attribute.data.foreach_get('value', final_values)
            else:
                final_values = np.empty((num_verts, 4), dtype=np.float32)
            
            # Get global opacity and blend mode for blending
            opacity = context.scene.vgradient_global_opacity
            blend_mode = context.scene.vgradient_blend_mode
            
            # Always get current colors to ensure alpha values are respected
            # This is critical for proper blending with color stop alpha values
            need_current_values = use_existing_mask or \
                                not use_mask_mode or \
                                selected_verts is not None
            
            # Always initialize current_values to ensure it's defined
            if use_mask_mode:
                current_values = np.empty(num_verts, dtype=np.float32)
                if need_current_values:
                    target_attribute.data.foreach_get('value', current_values)
            else:
                current_values = np.ones((num_verts, 4), dtype=np.float32)
                if need_current_values:
                    # In Edit mode, we need to use BMesh to get colors with proper color space conversion
                    if obj.mode == 'EDIT':
                        current_values = utils.get_vertex_colors_from_bmesh(obj, num_verts)
                    else:
                        # In Object mode, we can use foreach_get
                        temp_values = np.empty(num_verts * 4, dtype=np.float32)
                        target_attribute.data.foreach_get('color', temp_values)
                        current_values = temp_values.reshape(-1, 4)
            
            # Get line direction and length
            start = np.array(self.start_point)
            end = np.array(self.end_point)
            line_vec = end - start
            line_length = np.linalg.norm(line_vec)
            
            # If screen space is enabled, we need to project vertices to screen space
            if use_screen_space:
                # Get the view matrix
                region = context.region
                rv3d = context.region_data
                
                # Project start and end points to screen space
                start_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.start_point)
                end_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.end_point)
                
                if start_2d and end_2d:
                    # Convert to numpy arrays for vectorized operations
                    start_2d = np.array([start_2d.x, start_2d.y])
                    end_2d = np.array([end_2d.x, end_2d.y])
                    line_vec_2d = end_2d - start_2d
                    line_length_2d = np.linalg.norm(line_vec_2d)
                    line_dir_2d = line_vec_2d / line_length_2d if line_length_2d > 0 else np.array([1.0, 0.0])
                    
                    # If line length is too small, use 3D space instead
                    if line_length_2d < 1.0:
                        use_screen_space = False
                        print("Line too short in screen space, falling back to 3D space")
        
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * chunk_size
                end_idx = min(start_idx + chunk_size, num_verts)
                
                # Check if we need to process this chunk based on selection
                process_chunk = True
                
                # If in Edit mode with a selection, check if any vertices in this chunk are selected
                if selected_verts is not None:
                    # Find which vertices in this chunk are selected
                    chunk_indices = np.arange(start_idx, end_idx)
                    mask = np.isin(chunk_indices, selected_verts)
                    process_chunk = np.any(mask)
                
                # Skip this chunk if no vertices are selected
                if not process_chunk:
                    continue
                    
                # Calculate factors for this chunk
                chunk_verts = verts[start_idx:end_idx]
                
                if use_screen_space and start_2d is not None and end_2d is not None:
                    # Project vertices to screen space using batch operation
                    screen_coords = utils.world_to_screen_batch(chunk_verts, region, rv3d)
                    
                    # Calculate projection onto line in screen space
                    if line_length_2d > 0:
                        # Calculate vector from start to each vertex
                        vert_vec = screen_coords - start_2d
                        
                        # Project onto line direction using dot product
                        proj_length = np.dot(vert_vec, line_dir_2d)
                        
                        # Convert to factor (0 to 1)
                        factors = np.clip(proj_length / line_length_2d, 0, 1)
                        
                        # Reverse factors if gradient is reversed
                        if self.__class__._gradient_reversed:
                            factors = 1.0 - factors
                    else:
                        # If line is too short, use distance from start
                        factors = np.zeros(len(chunk_verts))
                else:
                    # 3D space projection
                    if line_length > 0:
                        # Calculate vector from start to each vertex
                        vert_vec = chunk_verts - start
                        
                        # Project onto line direction
                        line_dir = line_vec / line_length
                        proj_length = np.sum(vert_vec * line_dir, axis=1)
                        
                        # Convert to factor (0 to 1)
                        factors = np.clip(proj_length / line_length, 0, 1)
                        
                        # Reverse factors if gradient is reversed
                        if self.__class__._gradient_reversed:
                            factors = 1.0 - factors
                    else:
                        # If line is too short, use distance from start
                        factors = np.zeros(len(chunk_verts))
                
                # Symmetry code removed - will be replaced with new optimized implementation
                
                # Interpolate colors for this chunk
                if use_mask_mode:
                    # For mask mode, we just use the factor directly
                    new_values = factors
                    
                    # Combine with existing mask using maximum value
                    chunk_current = final_values[start_idx:end_idx]
                    final_values[start_idx:end_idx] = np.maximum(chunk_current, new_values)
                else:
                    # For vertex colors, interpolate through the gradient
                    new_colors = utils.interpolate_gradient_colors_batch(gradient, factors)
                    
                    # Get chunk of current colors if needed
                    chunk_current = None
                    if need_current_values:
                        chunk_current = current_values[start_idx:end_idx]
                    
                    # Always apply the selected blend mode to ensure alpha values are respected
                    # Ensure chunk_current is initialized if it's None
                    if chunk_current is None:
                        chunk_current = current_values[start_idx:end_idx]
                        
                    opacity_blended_colors = utils.apply_blend_mode(
                        chunk_current, 
                        new_colors, 
                        blend_mode, 
                        opacity
                        )
                    
                    # Apply mask if in sculpt mode and mask exists
                    if use_existing_mask:
                        # Get the mask values for this chunk
                        chunk_mask = mask_data[start_idx:end_idx]
                        # Blend between current and opacity-blended colors based on mask (0=unmasked, 1=masked)
                        final_values[start_idx:end_idx] = chunk_current * chunk_mask[:, np.newaxis] + opacity_blended_colors * (1 - chunk_mask[:, np.newaxis])
                    elif selected_verts is not None:
                        # In Edit mode with selection, only apply to selected vertices
                        chunk_indices = np.arange(start_idx, end_idx)
                        mask = np.isin(chunk_indices, selected_verts)
                        
                        # Create a mask for broadcasting with colors
                        broadcast_mask = mask[:, np.newaxis]
                        
                        # Get current colors for this chunk
                        # Make sure we have current_values before trying to access it
                        chunk_current = current_values[start_idx:end_idx] if 'current_values' in locals() else np.zeros((end_idx - start_idx, 4), dtype=np.float32)
                        
                        # Apply colors only to selected vertices
                        # For unselected vertices, keep their current values
                        final_values[start_idx:end_idx] = np.where(broadcast_mask, opacity_blended_colors, chunk_current)
                    else:
                        # If no mask or selection, just apply the opacity-blended colors
                        final_values[start_idx:end_idx] = opacity_blended_colors
        
            # Update color attribute or mask
            if use_mask_mode:
                target_attribute.data.foreach_set("value", final_values)
                
                # Ensure the mask is updated in the viewport
                mesh.update()
                if hasattr(context, 'sculpt_object'):
                    context.sculpt_object.use_mesh_mirror_x = context.sculpt_object.use_mesh_mirror_x
            else:
                # Use the utility function to update color attribute (handles Edit mode correctly)
                utils.update_color_attribute(obj, target_attribute, final_values, selected_verts)
        
        # total_time = (time.time() - total_start) * 1000
        # print(f"Total gradient application time: {total_time:.2f}ms")
        
    def update_draw_state(self, context, event):
        """Update the drawing state with current operator state"""
        # Update current mouse position for preview
        self.__class__._draw_current_point = Vector((event.mouse_region_x, event.mouse_region_y))
        self.__class__._draw_area = context.area
        
        # Update start point if we have one
        if hasattr(self, 'start_point'):
            region = context.region
            rv3d = context.region_data
            screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, self.start_point)
            if screen_pos:
                self.__class__._draw_screen_start = Vector((screen_pos.x, screen_pos.y))
                self.__class__._draw_start_point = self.start_point
        
        # Update end point if we have one
        if hasattr(self, 'end_point'):
            region = context.region
            rv3d = context.region_data
            screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, self.end_point)
            if screen_pos:
                self.__class__._draw_screen_end = Vector((screen_pos.x, screen_pos.y))
                self.__class__._draw_end_point = self.end_point
        
        # Check if we're in mask mode using the class-level Alt state
        use_mask_mode = context.mode == 'SCULPT' and self.__class__._alt_pressed
        
        if not use_mask_mode:
            # Only update preview color if not in mask mode
            gradient = utils.get_active_gradient(context)
            if gradient and len(gradient.colors) > 0:
                # Default color in case we don't calculate one below
                # Choose appropriate color based on gradient direction
                color_index = -1 if self.__class__._gradient_reversed else 0
                color = gradient.colors[color_index].color
                
                # If we have a start point and a current mouse position, sample the color at the cursor position
                if hasattr(self, 'start_point') and self.__class__._draw_current_point:
                    # Calculate factor based on projection of current point onto line
                    if hasattr(self, 'end_point') or hasattr(self, 'preview_end_point'):
                        # We have both start and end points (or preview end point)
                        if hasattr(self, 'end_point'):
                            line_start = self.start_point
                            line_end = self.end_point
                        else:
                            line_start = self.start_point
                            line_end = self.preview_end_point
                            
                        # Get current mouse position in 3D
                        current_point = None
                        if hasattr(self, 'preview_end_point'):
                            current_point = self.preview_end_point
                        
                        if current_point is not None:
                            # Calculate vector from start to end
                            line_vec = Vector(line_end) - Vector(line_start)
                            line_len = line_vec.length
                            
                            if line_len > 0:
                                # Normalize line vector
                                line_dir = line_vec / line_len
                                
                                # Calculate vector from start to current point
                                current_vec = Vector(current_point) - Vector(line_start)
                                
                                # Project onto line direction
                                proj_length = current_vec.dot(line_dir)
                                
                                # Convert to factor (0 to 1)
                                t = max(0, min(1, proj_length / line_len))
                                
                                # Reverse the factor if needed
                                if self.__class__._gradient_reversed:
                                    t = 1.0 - t
                                
                                # Get color from gradient
                                color = utils.interpolate_gradient_color(gradient, t)
                    else:
                        # Only have start point, use default color based on gradient direction
                        color_index = -1 if self.__class__._gradient_reversed else 0
                        color = gradient.colors[color_index].color
                # If we don't have enough points to calculate a position, use endpoint colors
                else:
                    # Choose color based on state
                    if hasattr(self, 'start_point') and not hasattr(self, 'end_point'):
                        # After first click, show the last color in the gradient
                        if len(gradient.colors) > 1:
                            # Get the index based on gradient direction
                            color_index = 0 if self.__class__._gradient_reversed else -1
                            color = gradient.colors[color_index].color
                        else:
                            color = gradient.colors[0].color
                    else:
                        # Before first click or after second click, show the first color
                        # Get the index based on gradient direction
                        color_index = -1 if self.__class__._gradient_reversed else 0
                        color = gradient.colors[color_index].color
            else:
                color = (1, 1, 1, 1)
                
            # Apply gamma correction
            if len(color) == 3:
                preview_color = (utils.gamma_correct(color[0]), 
                               utils.gamma_correct(color[1]), 
                               utils.gamma_correct(color[2]), 
                               1.0)
            else:
                preview_color = (utils.gamma_correct(color[0]), 
                               utils.gamma_correct(color[1]), 
                               utils.gamma_correct(color[2]), 
                               color[3])
                               
            self.__class__._draw_preview_color = preview_color
    
    def modal(self, context, event):
        """Handle modal events"""
        context.area.tag_redraw()
        
        # Store the event for use in apply_gradient
        self._last_event = event
        self.__class__._last_event = event
        
        # Track Alt key state at class level for consistent access
        self.__class__._alt_pressed = event.alt  # Store in class for draw callback
        
        # Handle X key press to reverse gradient direction
        if event.type == 'X' and event.value == 'PRESS':
            self.__class__._gradient_reversed = not self.__class__._gradient_reversed
            context.area.tag_redraw()
            # Update status text to indicate the gradient direction
            direction_text = "reversed" if self.__class__._gradient_reversed else "normal"
            context.workspace.status_text_set(
                f"Gradient direction: {direction_text}. Click to set end point. X to toggle direction. Right click/Esc to cancel")
            return {'RUNNING_MODAL'}
        
        # Update draw state
        self.update_draw_state(context, event)
        
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cleanup(context)
            return {'CANCELLED'}
            
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if not hasattr(self, 'start_point'):
                    # First click - get surface point for start
                    hit_point, hit_normal = self.get_surface_point(context, event)
                    # We'll always get a point now, even in empty space
                    self.start_point = hit_point
                    self.start_normal = hit_normal
                    self.update_draw_state(context, event)
                    context.workspace.status_text_set(
                        "Click to set end point. Hold Ctrl to snap to 15° increments. Press X to reverse gradient. Right click/Esc to cancel")
                    return {'RUNNING_MODAL'}
                else:
                    # Second click - get end point and apply
                    hit_point, hit_normal = self.get_snapped_point(context, event)
                    # We'll always get a point now, even in empty space
                    self.end_point = hit_point
                    self.end_normal = hit_normal
                    self.update_draw_state(context, event)
                    self.apply_gradient(context)
                    self.cleanup(context)
                    return {'FINISHED'}
                    
        if event.type == 'MOUSEMOVE':
            # If we have a start point, update the preview with snapped position if Ctrl is held
            if hasattr(self, 'start_point'):
                # Get the snapped point for preview
                hit_point, hit_normal = self.get_snapped_point(context, event)
                
                # Store temporarily for drawing
                self.preview_end_point = hit_point
                
                # Update region coordinates for drawing
                region = context.region
                rv3d = context.region_data
                screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, hit_point)
                if screen_pos:
                    self.__class__._draw_current_point = Vector((screen_pos.x, screen_pos.y))
                    if hasattr(self, 'start_point'):
                        self.__class__._draw_screen_end = Vector((screen_pos.x, screen_pos.y))
            else:
                self.update_draw_state(context, event)
            return {'RUNNING_MODAL'}
            
        return {'RUNNING_MODAL'}
        
    def invoke(self, context, event):
        """Start the operator"""
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
            
        if context.mode == 'SCULPT':
            if not context.active_object or context.active_object.type != 'MESH':
                self.report({'WARNING'}, "No active mesh object in sculpt mode")
                return {'CANCELLED'}
        elif context.mode == 'EDIT_MESH':
            if not context.active_object or context.active_object.type != 'MESH':
                self.report({'WARNING'}, "No active mesh object in edit mode")
                return {'CANCELLED'}
        else:  # Object mode
            valid_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
            if not valid_objects:
                self.report({'WARNING'}, "No mesh objects selected")
                return {'CANCELLED'}
            
        # Add draw handler
        args = ()
        self.__class__._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
        
        # Initialize draw state
        self.update_draw_state(context, event)
        
        context.workspace.status_text_set("Click on surface to set gradient start point. Hold Ctrl to snap to 15° increments. Right click/Esc to cancel")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
