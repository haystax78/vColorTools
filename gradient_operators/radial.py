"""
Radial gradient operator for vColGradient addon
Applies a radial gradient to vertex colors or sculpt mask
"""

import bpy
import gpu
import numpy as np
import time
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras import view3d_utils
from .. import utils

class VGRADIENT_OT_radial(bpy.types.Operator):
    """Apply a radial gradient to vertex colors based on distance from center"""
    bl_idname = "vgradient.radial"
    bl_label = "Radial"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a radial gradient to vertex colors or sculpt mask. Hold Alt to apply as sculpt mask"
    
    # Class variables for drawing state
    _handle = None
    _draw_center_point = None
    _draw_screen_center = None
    _draw_current_point = None
    _draw_preview_color = (1, 1, 1, 1)
    _draw_area = None
    _draw_radius = 0
    _last_event = None
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
            cls._draw_center_point = None
            cls._draw_screen_center = None
            cls._draw_current_point = None
            cls._draw_preview_color = (1, 1, 1, 1)
            cls._draw_area = None
            cls._draw_radius = 0
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
        """Draw the preview circle and radius"""
        try:
            # Get current context
            context = bpy.context
            if not cls._draw_area or context.area != cls._draw_area:
                return
                
            # Draw center point and radius circle if we have a center
            if cls._draw_screen_center:
                gpu.state.line_width_set(2)
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                
                # Get center coordinates
                x, y = cls._draw_screen_center
                
                # Get UI scale factor for consistent line thickness
                ui_scale = utils.get_ui_scale(context)
                
                # Get the active gradient
                gradient = utils.get_active_gradient(context)
                
                # Check if we're in mask mode
                use_mask_mode = context.mode == 'SCULPT' and cls._last_event and cls._last_event.alt
                
                # Draw filled circle at center with appropriate gradient color
                if not use_mask_mode and gradient and utils.get_gradient_color_count(gradient) > 0:
                    # Get the appropriate color from gradient based on direction
                    if cls._gradient_reversed:
                        # If reversed, use the last color for the center
                        linear_color = utils.get_gradient_last_color(gradient)
                    else:
                        # Otherwise use the first color for the center
                        linear_color = utils.get_gradient_first_color(gradient)
                    
                    # Convert from linear to sRGB for display
                    display_color = (utils.linear_to_srgb(linear_color[0]), 
                                   utils.linear_to_srgb(linear_color[1]), 
                                   utils.linear_to_srgb(linear_color[2]), 
                                   linear_color[3])
                    
                    # Draw filled circle with appropriate gradient color
                    shader.uniform_float("color", display_color)
                    center_radius = 10 * ui_scale
                    segments = 32
                    center_verts = [(x + center_radius * np.cos(angle), y + center_radius * np.sin(angle)) 
                                   for angle in [i * 2 * np.pi / segments for i in range(segments)]]
                    
                    gpu.state.blend_set('ALPHA')
                    batch = batch_for_shader(shader, 'TRI_FAN', {
                        "pos": [(x, y)] + center_verts
                    })
                    batch.draw(shader)
                else:
                    # Draw crosshair at center
                    shader.uniform_float("color", (1, 1, 1, 1))
                    size = 10
                    gpu.state.blend_set('ALPHA')
                    batch = batch_for_shader(shader, 'LINES', {"pos": [
                        (x - size, y), (x + size, y),
                        (x, y - size), (x, y + size)
                    ]})
                    batch.draw(shader)
                
                # If we have a radius, draw the circle and radius line
                if cls._draw_radius > 0 and not use_mask_mode and gradient and utils.get_gradient_color_count(gradient) > 0:
                    # Thickness of the line (in pixels)
                    thickness = 10 * ui_scale
                    segments = 32
                    
                    # Get the appropriate color for the perimeter based on direction
                    if cls._gradient_reversed:
                        # If reversed, use the first color for the perimeter
                        perimeter_factor = 0.0
                    else:
                        # Otherwise use the last color for the perimeter
                        perimeter_factor = 1.0
                    
                    # Get color from gradient (in linear space)
                    linear_color = utils.interpolate_gradient_color(gradient, perimeter_factor)
                    
                    # Convert from linear to sRGB for display
                    perimeter_color = (utils.linear_to_srgb(linear_color[0]), 
                                     utils.linear_to_srgb(linear_color[1]), 
                                     utils.linear_to_srgb(linear_color[2]), 
                                     linear_color[3])
                    
                    # Draw the outer circle with thick line and appropriate color
                    shader.uniform_float("color", perimeter_color)
                    
                    # Create vertices for the perimeter circle
                    circle_angles = [i * 2 * np.pi / segments for i in range(segments)]
                    circle_verts = [(x + cls._draw_radius * np.cos(angle), y + cls._draw_radius * np.sin(angle)) 
                                   for angle in circle_angles]
                    
                    # Draw the perimeter as a series of thick line segments
                    for i in range(segments):
                        # Get the current and next vertex
                        v1 = circle_verts[i]
                        v2 = circle_verts[(i + 1) % segments]
                        
                        # Calculate direction and perpendicular vectors
                        dx = v2[0] - v1[0]
                        dy = v2[1] - v1[1]
                        length = np.sqrt(dx*dx + dy*dy)
                        
                        if length > 0:
                            # Normalize and get perpendicular vector
                            dx, dy = dx/length, dy/length
                            # Perpendicular vector
                            px, py = -dy, dx
                        else:
                            px, py = 0, 1
                        
                        # Create quad vertices for this segment
                        quad_verts = [
                            (v1[0] + px * thickness/2, v1[1] + py * thickness/2),
                            (v2[0] + px * thickness/2, v2[1] + py * thickness/2),
                            (v2[0] - px * thickness/2, v2[1] - py * thickness/2),
                            (v1[0] - px * thickness/2, v1[1] - py * thickness/2)
                        ]
                        
                        # Draw filled quad
                        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": quad_verts})
                        batch.draw(shader)
                    
                    # Draw radius line with gradient
                    # Calculate angle to current mouse position if available
                    angle = 0
                    if cls._draw_current_point:
                        mx, my = cls._draw_current_point
                        dx, dy = mx - x, my - y
                        angle = np.arctan2(dy, dx)
                    
                    # Calculate direction vector for the line
                    dx = np.cos(angle)
                    dy = np.sin(angle)
                    
                    # Get perpendicular vector for thickness
                    px, py = -dy, dx
                    
                    # Create points along the line
                    num_segments = 20  # Number of segments to divide the line into
                    line_points = []
                    for i in range(num_segments + 1):
                        t = i / num_segments
                        radius = t * cls._draw_radius
                        line_points.append((
                            x + radius * dx,
                            y + radius * dy
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
                elif cls._draw_radius > 0 and use_mask_mode:
                    # For mask mode, show a black-to-white gradient
                    thickness = 10 * ui_scale
                    segments = 32
                    
                    # Draw the outer circle with color based on gradient direction
                    # Create vertices for the perimeter circle
                    circle_angles = [i * 2 * np.pi / segments for i in range(segments)]
                    circle_verts = [(x + cls._draw_radius * np.cos(angle), y + cls._draw_radius * np.sin(angle)) 
                                   for angle in circle_angles]
                    
                    # Draw the perimeter with color based on gradient direction
                    # For mask mode: black when flipped, white when not flipped
                    if cls._gradient_reversed:
                        perimeter_color = (0.0, 0.0, 0.0, 0.8)  # Black when flipped
                    else:
                        perimeter_color = (1.0, 1.0, 1.0, 0.8)  # White when not flipped
                    shader.uniform_float("color", perimeter_color)
                    for i in range(segments):
                        # Get the current and next vertex
                        v1 = circle_verts[i]
                        v2 = circle_verts[(i + 1) % segments]
                        
                        # Calculate direction and perpendicular vectors
                        dx = v2[0] - v1[0]
                        dy = v2[1] - v1[1]
                        length = np.sqrt(dx*dx + dy*dy)
                        
                        if length > 0:
                            # Normalize and get perpendicular vector
                            dx, dy = dx/length, dy/length
                            # Perpendicular vector
                            px, py = -dy, dx
                        else:
                            px, py = 0, 1
                        
                        # Create quad vertices for this segment
                        quad_verts = [
                            (v1[0] + px * thickness/2, v1[1] + py * thickness/2),
                            (v2[0] + px * thickness/2, v2[1] + py * thickness/2),
                            (v2[0] - px * thickness/2, v2[1] - py * thickness/2),
                            (v1[0] - px * thickness/2, v1[1] - py * thickness/2)
                        ]
                        
                        # Draw filled quad
                        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": quad_verts})
                        batch.draw(shader)
                    
                    # Draw radius line with black-to-white gradient
                    # Calculate angle to current mouse position if available
                    angle = 0
                    if cls._draw_current_point:
                        mx, my = cls._draw_current_point
                        dx, dy = mx - x, my - y
                        angle = np.arctan2(dy, dx)
                    
                    # Calculate direction vector for the line
                    dx = np.cos(angle)
                    dy = np.sin(angle)
                    
                    # Get perpendicular vector for thickness
                    px, py = -dy, dx
                    
                    # Create points along the line
                    num_segments = 20  # Number of segments to divide the line into
                    line_points = []
                    for i in range(num_segments + 1):
                        t = i / num_segments
                        radius = t * cls._draw_radius
                        line_points.append((
                            x + radius * dx,
                            y + radius * dy
                        ))
                    
                    # Draw each segment with its appropriate grayscale value
                    for i in range(len(line_points) - 1):
                        # Calculate the factor (0-1) for this segment
                        t = i / num_segments
                        
                        # For mask mode, we don't need to invert the gradient direction
                        # Just apply the gradient reversal if needed
                        
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
                elif cls._draw_radius > 0:
                    # Simple circle for fallback
                    shader.uniform_float("color", (1, 1, 1, 1))
                    segments = 32
                    circle_verts = [(x + cls._draw_radius * np.cos(angle), y + cls._draw_radius * np.sin(angle)) 
                                   for angle in [i * 2 * np.pi / segments for i in range(segments)]]
                    
                    batch = batch_for_shader(shader, 'LINE_LOOP', {
                        "pos": circle_verts
                    })
                    batch.draw(shader)
                    

                    
            # Draw color preview circle
            if cls._draw_current_point:
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                
                # Get current mouse position
                x, y = cls._draw_current_point
                
                # Check if we're in mask mode
                use_mask_mode = context.mode == 'SCULPT' and cls._last_event and cls._last_event.alt
                
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
    
    def get_screen_radius(self, context, center, current):
        """Get screen space radius between two points"""
        region = context.region
        rv3d = context.region_data
        center_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, center)
        if not center_2d:
            return 0.0
        # Get 3D point at mouse position with same depth as center
        current_3d = view3d_utils.region_2d_to_location_3d(region, rv3d, current, center)
        # Project that point back to screen space
        current_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, current_3d)
        if not current_2d:
            return 0.0
        # Store the 3D radius for later use
        self.radius_3d = (current_3d - center).length
        # Return screen space distance for visual feedback
        return (Vector((current_2d.x, current_2d.y)) - Vector((center_2d.x, center_2d.y))).length
        
    def apply_gradient(self, context):
        """Apply the radial gradient based on distance from center"""
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
            
        # Check if we should use mask mode
        use_mask_mode, gradient = utils.apply_mask_mode(context, self._last_event)
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
            
                
            # Get vertex positions and mask
            num_verts = len(mesh.vertices)
            verts = np.empty(num_verts * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", verts)
            verts = verts.reshape(-1, 3)
            
            # Get selected vertices in Edit mode
            selected_verts = None
            if context.mode == 'EDIT_MESH':
                selected_verts = utils.get_selected_vertices(obj)
            
            # Transform to world space using optimized matrix multiplication
            matrix = np.array(obj.matrix_world)
            rotation = matrix[:3, :3]
            translation = matrix[:3, 3]
            verts = np.dot(verts, rotation.T) + translation
            
            # Debug information commented out
            # print("\nVertex Space Debug:")
            # print(f"Number of vertices: {len(verts)}")
            # print(f"Center point (world space): {self.center_point}")
            # print(f"3D Radius: {self.radius_3d}")
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
            
            # Get center point as numpy array
            center = np.array(self.center_point)
            
            # If screen space is enabled, we need to project center point to screen space
            center_2d = None
            if use_screen_space:
                # Get the view matrix
                region = context.region
                rv3d = context.region_data
                
                # Project center point to screen space
                center_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, self.center_point)
                
                if center_2d:
                    # Convert to numpy arrays for vectorized operations
                    center_2d = np.array([center_2d.x, center_2d.y])
                    
                    # Calculate screen space radius
                    radius_2d = self.get_screen_radius(context, self.center_point, (self._draw_current_point.x, self._draw_current_point.y))
                    
                    # If radius is too small, use 3D space instead
                    if radius_2d < 1.0:
                        use_screen_space = False
                        print("Radius too small in screen space, falling back to 3D space")
        
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * chunk_size
                end_idx = min(start_idx + chunk_size, num_verts)
                
                # Calculate factors for this chunk
                chunk_verts = verts[start_idx:end_idx]
                
                if use_screen_space and center_2d is not None and radius_2d > 0:
                    # Project vertices to screen space using batch operation
                    screen_coords = utils.world_to_screen_batch(chunk_verts, context.region, context.region_data)
                    
                    # Calculate distances in screen space
                    distances = np.linalg.norm(screen_coords - center_2d, axis=1)
                    
                    # Convert to factor (0 to 1)
                    factors = np.clip(distances / radius_2d, 0, 1)
                    
                    # Reverse factors if gradient is reversed
                    if self.__class__._gradient_reversed:
                        factors = 1.0 - factors
                else:
                    # Calculate distances in 3D space
                    distances = np.linalg.norm(chunk_verts - center, axis=1)
                    factors = np.clip(distances / float(self.radius_3d), 0, 1)
                    
                    # Reverse factors if gradient is reversed
                    if self.__class__._gradient_reversed:
                        factors = 1.0 - factors
                
                # Symmetry code removed - will be replaced with new optimized implementation
            
                # Interpolate colors for this chunk
                if use_mask_mode:
                    # For mask mode, we just use the inverted factor directly (closer = higher value)
                    new_values = 1.0 - factors
                    
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
                        if chunk_current is None:
                            chunk_current = current_values[start_idx:end_idx]
                        
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
        
        # Update center point if we have one
        if hasattr(self, 'center_point'):
            region = context.region
            rv3d = context.region_data
            screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, self.center_point)
            if screen_pos:
                self.__class__._draw_screen_center = Vector((screen_pos.x, screen_pos.y))
                self.__class__._draw_center_point = self.center_point
                
                # Update radius if we're in radius selection mode
                if self.center_point and not hasattr(self, 'radius'):
                    self.__class__._draw_radius = self.get_screen_radius(
                        context, self.center_point, 
                        (event.mouse_region_x, event.mouse_region_y))
    
        # Check if we're in mask mode
        use_mask_mode = context.mode == 'SCULPT' and self._last_event and self._last_event.alt
        
        if not use_mask_mode:
            # Only update preview color if not in mask mode
            gradient = utils.get_active_gradient(context)
            if gradient and utils.get_gradient_color_count(gradient) > 0:
                # Default color based on gradient direction
                if self.__class__._gradient_reversed:
                    color = utils.get_gradient_last_color(gradient)
                else:
                    color = utils.get_gradient_first_color(gradient)
                
                # If we have a center point and a current mouse position, sample the color at the cursor position
                if hasattr(self, 'center_point') and self.__class__._draw_current_point:
                    current_point = (event.mouse_region_x, event.mouse_region_y)
                    
                    if self.__class__._draw_screen_center:
                        center_point = self.__class__._draw_screen_center
                        delta = Vector(current_point) - center_point
                        distance = delta.length
                        radius = self.__class__._draw_radius if hasattr(self.__class__, '_draw_radius') else 1.0
                        
                        if radius > 0:
                            t = min(1.0, distance / radius)
                            if self.__class__._gradient_reversed:
                                t = 1.0 - t
                            color = utils.interpolate_gradient_color(gradient, t)
                    else:
                        # Use appropriate end color based on state
                        if hasattr(self, 'center_point') and not hasattr(self, 'radius'):
                            # After first click, show the opposite end color
                            if self.__class__._gradient_reversed:
                                color = utils.get_gradient_first_color(gradient)
                            else:
                                color = utils.get_gradient_last_color(gradient)
                else:
                    # Choose color based on state
                    if hasattr(self, 'center_point') and not hasattr(self, 'radius'):
                        # After first click, show the opposite end color
                        if self.__class__._gradient_reversed:
                            color = utils.get_gradient_first_color(gradient)
                        else:
                            color = utils.get_gradient_last_color(gradient)
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
        self.__class__._last_event = event  # Store in class for draw callback
        
        # Handle X key press to reverse gradient direction
        if event.type == 'X' and event.value == 'PRESS':
            self.__class__._gradient_reversed = not self.__class__._gradient_reversed
            context.area.tag_redraw()
            # Update status text to indicate the gradient direction
            direction_text = "reversed" if self.__class__._gradient_reversed else "normal"
            context.workspace.status_text_set(
                f"Gradient direction: {direction_text}. Move mouse to set radius, click to confirm. Press X to toggle direction. Right click/Esc to cancel")
            return {'RUNNING_MODAL'}
        
        # Update draw state
        self.update_draw_state(context, event)
        
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cleanup(context)
            return {'CANCELLED'}
            
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if not hasattr(self, 'center_point'):
                    # First click - get surface point
                    hit_point, hit_normal = self.get_surface_point(context, event)
                    # We'll always get a point now, even in empty space
                    self.center_point = hit_point
                    self.surface_normal = hit_normal
                    self.update_draw_state(context, event)
                    context.workspace.status_text_set(
                        "Move mouse to set radius, click to confirm. Press X to reverse gradient. Right click/Esc to cancel")
                    return {'RUNNING_MODAL'}
                else:
                    # Second click - get radius and apply
                    current = Vector((event.mouse_region_x, event.mouse_region_y))
                    self.radius = self.get_screen_radius(context, self.center_point, current)
                    self.update_draw_state(context, event)
                    self.apply_gradient(context)
                    self.cleanup(context)
                    return {'FINISHED'}
                    
        if event.type == 'MOUSEMOVE':
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
        
        context.workspace.status_text_set("Click on surface to set gradient center. Right click/Esc to cancel")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
