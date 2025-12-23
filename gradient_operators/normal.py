"""
Normal gradient operator for vColGradient addon
Applies a gradient based on vertex normal alignment with a sampled normal
"""

import bpy
import gpu
import numpy as np
import time
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras import view3d_utils
from .. import utils

class VGRADIENT_OT_normal(bpy.types.Operator):
    """Apply a gradient based on vertex normal alignment with a sampled normal"""
    bl_idname = "vgradient.normal"
    bl_label = "Normal"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a gradient based on vertex normal alignment. Hold Alt to apply as sculpt mask"
    
    # Class variables for drawing state
    _handle = None
    _draw_sample_point = None
    _draw_screen_sample = None
    _draw_preview_color = (1, 1, 1, 1)
    _draw_area = None
    _last_event = None
    _sampled_normal = None
    _alt_pressed = False  # Track Alt key state at class level
    _gradient_reversed = False  # Track if gradient direction is reversed
    _raycast_mode = False  # Track raycast mode state
    
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
            cls._draw_sample_point = None
            cls._draw_screen_sample = None
            cls._draw_preview_color = (1, 1, 1, 1)
            cls._draw_area = None
            cls._last_event = None
            cls._sampled_normal = None
            cls._alt_pressed = False
            cls._gradient_reversed = False  # Reset gradient direction flag
            if context:
                try:
                    context.workspace.status_text_set(None)
                    context.area.tag_redraw()
                except:
                    pass
    
    @classmethod
    def draw_callback_px(cls, *args):
        """Draw the preview point"""
        try:
            # Get current context
            context = bpy.context
            if not cls._draw_area or context.area != cls._draw_area:
                return
                
            gpu.state.line_width_set(2)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            
            # Draw sample point if we have one
            if cls._draw_screen_sample:
                # Get current mouse position for both color preview and crosshair
                x, y = cls._draw_screen_sample
                
                # FIRST DRAW COLOR PREVIEW CIRCLE (so normal preview will be on top)
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                
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
                
                # NOW DRAW CROSSHAIR AND NORMAL PREVIEW (on top of color preview)
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                
                # Draw crosshair at sample point
                shader.uniform_float("color", (1, 1, 1, 1))
                size = 10
                gpu.state.blend_set('ALPHA')
                batch = batch_for_shader(shader, 'LINES', {"pos": [
                    (x - size, y), (x + size, y),
                    (x, y - size), (x, y + size)
                ]})
                batch.draw(shader)
                
                # Draw normal direction indicator if we have a sampled normal and a valid mesh object was hit
                # We know we have a valid mesh hit if _draw_sample_point is not None and it wasn't created by the fallback
                # in get_surface_point (which returns ray_origin + view_vector * 10.0 when no hit is found)
                if cls._sampled_normal and cls._draw_sample_point:
                    # Check if we have a valid hit by testing if the last event exists
                    # and if we can raycast against a mesh object
                    is_valid_mesh_hit = False
                    
                    if cls._last_event:
                        # Get the context arguments
                        scene = context.scene
                        region = context.region
                        rv3d = context.region_data
                        coord = cls._last_event.mouse_region_x, cls._last_event.mouse_region_y
                        
                        # Get the ray from the viewport and mouse
                        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
                        
                        # Cast ray against the scene
                        depsgraph = context.evaluated_depsgraph_get()
                        result = scene.ray_cast(depsgraph, ray_origin, view_vector)
                        
                        # If we hit something and it's a mesh object
                        if result[0]:
                            hit_obj = result[4] if len(result) > 4 else None
                            if hit_obj and hit_obj.type == 'MESH':
                                is_valid_mesh_hit = True
                    
                    # Only draw the normal preview if we have a valid mesh hit
                    if is_valid_mesh_hit:
                        # Project the normal direction to screen space
                        region = context.region
                        rv3d = context.region_data
                        
                        # Get the sample point in 3D
                        sample_point = cls._draw_sample_point
                        
                        # Project sample point to screen space
                        sample_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, sample_point)
                        
                        if sample_2d:
                            # Base length in screen space (pixels)
                            base_screen_length = 200
                            
                            # Project the normal to screen space
                            # First, create a point a small distance away in the normal direction
                            temp_end = sample_point + Vector(cls._sampled_normal) * 0.1
                            temp_end_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, temp_end)
                            
                            if temp_end_2d:
                                # Calculate direction vector in screen space
                                direction_2d = temp_end_2d - sample_2d
                                
                                # Normalize the direction vector
                                direction_length = direction_2d.length
                                if direction_length > 0.0001:  # Avoid division by zero
                                    direction_2d = direction_2d / direction_length
                                    
                                    # Get the view vector (camera direction) at this point
                                    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, (sample_2d.x, sample_2d.y))
                                    view_vector.normalize()
                                    
                                    # Calculate dot product between normal and view vector
                                    # This gives us the cosine of the angle between them
                                    # When normal points at camera, dot product approaches -1
                                    # When normal is perpendicular to view, dot product approaches 0
                                    # When normal points away from camera, dot product approaches 1
                                    dot_product = Vector(cls._sampled_normal).dot(view_vector)
                                    
                                    # Adjust length based on alignment with camera
                                    # Convert dot product range [-1, 1] to length multiplier range [0.05, 1.0]
                                    # When normal points at camera (dot = -1), length is shortest (0.05)
                                    # When normal points away from camera (dot = 1), length is longest (1.0)
                                    length_multiplier = 0.7 * (dot_product + 1.0) + 0.05
                                    
                                    # Apply the adjusted length
                                    screen_length = base_screen_length * length_multiplier
                                    
                                    # Calculate end point with perspective-adjusted screen space length
                                    end_2d = sample_2d + direction_2d * screen_length
                                else:
                                    # Fallback if direction is too short
                                    end_2d = sample_2d + Vector((0, base_screen_length * 0.5))
                        
                            if 'end_2d' in locals() and end_2d and sample_2d:
                                # Get the active gradient to use its colors
                                gradient = utils.get_active_gradient(context)
                                
                                # Draw a circle at the base of the arrow with the starting color of the gradient
                                if gradient and utils.get_gradient_color_count(gradient) > 0 and not use_mask_mode:
                                    # Get the appropriate colors from gradient based on direction
                                    if cls._gradient_reversed:
                                        # If reversed, last color is the starting color
                                        start_color = utils.get_gradient_last_color(gradient)
                                        end_color = utils.get_gradient_first_color(gradient)
                                    else:
                                        # Otherwise first color is the starting color
                                        start_color = utils.get_gradient_first_color(gradient)
                                        end_color = utils.get_gradient_last_color(gradient)
                                    
                                    # Convert from linear to sRGB for display
                                    start_display_color = (utils.linear_to_srgb(start_color[0]), 
                                                        utils.linear_to_srgb(start_color[1]), 
                                                        utils.linear_to_srgb(start_color[2]), 
                                                        start_color[3])
                                    
                                    end_display_color = (utils.linear_to_srgb(end_color[0]), 
                                                        utils.linear_to_srgb(end_color[1]), 
                                                        utils.linear_to_srgb(end_color[2]), 
                                                        end_color[3])
                                    
                                    # Draw filled circle at the base with the starting color
                                    shader.uniform_float("color", start_display_color)
                                    base_radius = 12  # Radius of 20 as requested
                                    segments = 32
                                    base_verts = [(sample_2d.x + base_radius * np.cos(angle), sample_2d.y + base_radius * np.sin(angle)) 
                                                for angle in [i * 2 * np.pi / segments for i in range(segments)]]
                                    
                                    gpu.state.blend_set('ALPHA')
                                    batch = batch_for_shader(shader, 'TRI_FAN', {
                                        "pos": [(sample_2d.x, sample_2d.y)] + base_verts
                                    })
                                    batch.draw(shader)
                                    
                                    # Draw thick arrow line with a gradient from end color at base to start color at tip
                                    line_width = 8  # Thicker line for better visibility
                                    
                                    # Create a thick line by making a quad from sample_2d to end_2d
                                    if direction_2d.length > 0.0001:  # Only draw if we have a valid direction
                                        # Calculate perpendicular vector for line thickness
                                        perp = Vector((-direction_2d.y, direction_2d.x)) * (line_width / 2)
                                        
                                        # Calculate the four corners of the quad
                                        p1 = Vector((sample_2d.x, sample_2d.y)) + perp
                                        p2 = Vector((sample_2d.x, sample_2d.y)) - perp
                                        p3 = Vector((end_2d.x, end_2d.y)) - perp
                                        p4 = Vector((end_2d.x, end_2d.y)) + perp
                                        
                                        # Create a more detailed gradient with multiple segments to show all color stops
                                        # We'll create a series of quads along the arrow shaft, each with its own gradient segment
                                        
                                        # Number of segments to use for the gradient (more segments = smoother gradient)
                                        num_segments = max(10, utils.get_gradient_color_count(gradient) * 3)
                                        
                                        # Calculate direction and length
                                        direction = Vector((end_2d.x - sample_2d.x, end_2d.y - sample_2d.y))
                                        total_length = direction.length
                                        if total_length > 0:
                                            direction.normalize()
                                        
                                            # For each segment, create a quad with the appropriate gradient colors
                                            for i in range(num_segments):
                                                # Calculate segment start and end positions
                                                start_factor = i / num_segments
                                                end_factor = (i + 1) / num_segments
                                                
                                                # Get positions for this segment
                                                seg_start = sample_2d + direction * (start_factor * total_length)
                                                seg_end = sample_2d + direction * (end_factor * total_length)
                                                
                                                # Calculate gradient factors based on direction
                                                if cls._gradient_reversed:
                                                    # If reversed, go from 1.0 at base to 0.0 at tip
                                                    color_start_factor = 1.0 - start_factor
                                                    color_end_factor = 1.0 - end_factor
                                                else:
                                                    # Otherwise go from 0.0 at base to 1.0 at tip
                                                    color_start_factor = start_factor
                                                    color_end_factor = end_factor
                                                
                                                # Get colors from the full gradient
                                                start_seg_color = utils.interpolate_gradient_color(gradient, color_start_factor)
                                                end_seg_color = utils.interpolate_gradient_color(gradient, color_end_factor)
                                                
                                                # Convert to sRGB for display
                                                start_seg_display = (utils.linear_to_srgb(start_seg_color[0]),
                                                                    utils.linear_to_srgb(start_seg_color[1]),
                                                                    utils.linear_to_srgb(start_seg_color[2]),
                                                                    start_seg_color[3])
                                                
                                                end_seg_display = (utils.linear_to_srgb(end_seg_color[0]),
                                                                  utils.linear_to_srgb(end_seg_color[1]),
                                                                  utils.linear_to_srgb(end_seg_color[2]),
                                                                  end_seg_color[3])
                                                
                                                # Calculate the four corners of this segment's quad
                                                perp = Vector((-direction.y, direction.x)) * (line_width / 2)
                                                
                                                arrow_size = 45  # 50% larger arrow head
                                                direction_2d = (end_2d - sample_2d).normalized()
                                                # Calculate the four corners of the quad for the shaft, ending at the base of the arrow head
                                                shaft_end = end_2d - direction_2d * arrow_size
                                                e1 = shaft_end + perp
                                                e2 = shaft_end - perp
                                                s1 = Vector((seg_start.x, seg_start.y)) + perp
                                                s2 = Vector((seg_start.x, seg_start.y)) - perp
                                                
                                                # Draw the shaft of the arrow as a single green color with 0.5 transparency using TRI_STRIP for thickness
                                                shader = gpu.shader.from_builtin('SMOOTH_COLOR')
                                                shader.bind()
                                                green = (0.0, 1.0, 0.0, 0.1)
                                                batch = batch_for_shader(shader, 'TRI_STRIP', {
                                                    "pos": [(s1.x, s1.y), (s2.x, s2.y), (e1.x, e1.y), (e2.x, e2.y)],
                                                    "color": [green, green, green, green]
                                                })
                                                batch.draw(shader)
                                        
                                        # Draw arrow head with start color
                                        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                                        shader.bind()
                                        shader.uniform_float("color", start_display_color)
                                        
                                        # Calculate arrow head points using shaft_end as the base, with 50% larger width
                                        arrow1 = shaft_end + perp * 2.25
                                        arrow2 = shaft_end - perp * 2.25
                                        
                                        # Draw filled arrow head
                                        batch = batch_for_shader(shader, 'TRI_FAN', {
                                            "pos": [(end_2d.x, end_2d.y), (arrow1.x, arrow1.y), (arrow2.x, arrow2.y)]
                                        })
                                        batch.draw(shader)
                                elif use_mask_mode:
                                    # For mask mode, use the same TRI_STRIP method but with red shaft
                                    # Draw filled circle at the base with split black/white like the cursor preview
                                    base_radius = 12
                                    segments = 32
                                    half_segments = segments // 2
                                    
                                    # Create vertices for top (white) half of base circle
                                    top_verts = [(sample_2d.x, sample_2d.y)]  # Center point
                                    top_verts.extend([(sample_2d.x + base_radius * np.cos(angle), sample_2d.y + base_radius * np.sin(angle)) 
                                                for angle in [i * np.pi / half_segments for i in range(half_segments + 1)]])
                                    
                                    # Create vertices for bottom (black) half of base circle
                                    bottom_verts = [(sample_2d.x, sample_2d.y)]  # Center point
                                    bottom_verts.extend([(sample_2d.x + base_radius * np.cos(angle), sample_2d.y + base_radius * np.sin(angle)) 
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
                                    
                                    # Create a thick line by making a quad from sample_2d to end_2d
                                    if direction_2d.length > 0.0001:  # Only draw if we have a valid direction
                                        # Calculate perpendicular vector for line thickness
                                        perp = Vector((-direction_2d.y, direction_2d.x)) * (4) # Line width
                                        
                                        arrow_size = 45  # 50% larger arrow head
                                        direction_2d = (end_2d - sample_2d).normalized()
                                        # Calculate the four corners of the quad for the shaft
                                        shaft_end = end_2d - direction_2d * arrow_size
                                        e1 = shaft_end + perp
                                        e2 = shaft_end - perp
                                        s1 = Vector((sample_2d.x, sample_2d.y)) + perp
                                        s2 = Vector((sample_2d.x, sample_2d.y)) - perp
                                        
                                        # Draw the shaft of the arrow as a single RED color with 0.1 transparency using TRI_STRIP
                                        shader = gpu.shader.from_builtin('SMOOTH_COLOR')
                                        shader.bind()
                                        red = (1.0, 0.0, 0.0, 0.1)
                                        batch = batch_for_shader(shader, 'TRI_STRIP', {
                                            "pos": [(s1.x, s1.y), (s2.x, s2.y), (e1.x, e1.y), (e2.x, e2.y)],
                                            "color": [red, red, red, red]
                                        })
                                        batch.draw(shader)
                                        
                                        # Draw arrow head with color based on whether gradient is flipped
                                        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                                        shader.bind()
                                        # Black when not flipped, white when flipped
                                        if cls._gradient_reversed:
                                            arrow_head_color = (1.0, 1.0, 1.0, 0.8)  # White when flipped
                                        else:
                                            arrow_head_color = (0.0, 0.0, 0.0, 0.8)  # Black when not flipped
                                        shader.uniform_float("color", arrow_head_color)
                                        
                                        # Calculate arrow head points using shaft_end as the base, with 50% larger width
                                        arrow1 = shaft_end + perp * 2.25
                                        arrow2 = shaft_end - perp * 2.25
                                        
                                        # Draw filled arrow head
                                        batch = batch_for_shader(shader, 'TRI_FAN', {
                                            "pos": [(end_2d.x, end_2d.y), (arrow1.x, arrow1.y), (arrow2.x, arrow2.y)]
                                        })
                                        batch.draw(shader)
                                else:
                                    # Fallback if no gradient is available - use default green color
                                    # Draw a more visible line using multiple offset lines
                                    # This creates a more visible "halo" effect around the line
                                    
                                    # Set up line drawing
                                    gpu.state.blend_set('ALPHA')
                                    gpu.state.line_width_set(5)  # Much thicker line for better visibility
                                    
                                    # Draw multiple offset lines for a stronger halo effect
                                    # Include diagonal offsets and larger offsets for a thicker halo
                                    offsets = [
                                        (1, 0), (-1, 0), (0, 1), (0, -1),  # Primary offsets
                                        (1, 1), (-1, 1), (1, -1), (-1, -1),  # Diagonal offsets
                                        (2, 0), (-2, 0), (0, 2), (0, -2)  # Larger offsets
                                    ]
                                    
                                    # First draw black offset lines (creates outline effect)
                                    shader.uniform_float("color", (0, 0, 0, 0.7))  # Black with transparency
                                    for offset_x, offset_y in offsets:
                                        batch = batch_for_shader(shader, 'LINES', {"pos": [
                                            (sample_2d.x + offset_x, sample_2d.y + offset_y), 
                                            (end_2d.x + offset_x, end_2d.y + offset_y)
                                        ]})
                                        batch.draw(shader)
                                    
                                    # Then draw the main bright green line
                                    shader.uniform_float("color", (0, 1, 0.3, 1))  # Bright green for better visibility
                                    gpu.state.line_width_set(3)  # Thicker green line
                                    batch = batch_for_shader(shader, 'LINES', {"pos": [
                                        (sample_2d.x, sample_2d.y), (end_2d.x, end_2d.y)
                                    ]})
                                    batch.draw(shader)
                                    
                                    # Draw a small arrow head with similar halo effect
                                    arrow_size = 10  # Slightly larger arrow
                                    if direction_2d.length > 0.0001:  # Only draw if we have a valid direction
                                        # Calculate perpendicular vector for arrow head
                                        perp = Vector((-direction_2d.y, direction_2d.x))
                                        
                                        # Calculate arrow head points
                                        arrow1 = end_2d - direction_2d * arrow_size + perp * arrow_size * 0.5
                                        arrow2 = end_2d - direction_2d * arrow_size - perp * arrow_size * 0.5
                                        
                                        # Draw black offset arrow heads (outline effect)
                                        gpu.state.line_width_set(5)  # Thicker outline for arrowhead
                                        shader.uniform_float("color", (0, 0, 0, 0.7))
                                        for offset_x, offset_y in offsets:
                                            batch = batch_for_shader(shader, 'LINES', {"pos": [
                                                (end_2d.x + offset_x, end_2d.y + offset_y), 
                                                (arrow1.x + offset_x, arrow1.y + offset_y),
                                                (end_2d.x + offset_x, end_2d.y + offset_y), 
                                                (arrow2.x + offset_x, arrow2.y + offset_y)
                                            ]})
                                            batch.draw(shader)
                                        
                                        # Draw main green arrow head
                                        gpu.state.line_width_set(3)  # Thicker green arrowhead
                                        shader.uniform_float("color", (0, 1, 0.3, 1))  # Bright green
                                        batch = batch_for_shader(shader, 'LINES', {"pos": [
                                            (end_2d.x, end_2d.y), (arrow1.x, arrow1.y),
                                            (end_2d.x, end_2d.y), (arrow2.x, arrow2.y)
                                        ]})
                                        batch.draw(shader)
                

                
                gpu.state.blend_set('NONE')
                gpu.state.line_width_set(2)
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
        
        # Detect if we're in local view by comparing visible vs total objects
        is_local_view = len(context.visible_objects) < len(scene.objects)
        
        # First try scene.ray_cast which is faster
        depsgraph = context.evaluated_depsgraph_get()
        result = scene.ray_cast(depsgraph, ray_origin, view_vector)
        
        # If we hit something
        if result[0]:
            hit_obj = result[4] if len(result) > 4 else None
            
            # If we're in local view, only use the hit if it's on a visible object
            if is_local_view:
                if hit_obj and hit_obj in context.visible_objects:
                    return result[1], result[2]  # Return location and normal
            else:
                # Normal view - return the hit
                return result[1], result[2]  # Return location and normal
        
        # If scene.ray_cast didn't work or we're in local view and hit a non-visible object,
        # try individual ray casting on visible objects
        visible_objects = [obj for obj in context.visible_objects if obj.type == 'MESH']
        
        closest_hit = None
        closest_dist = float('inf')
        closest_normal = None
        
        # Cast ray against each visible object
        for obj in visible_objects:
            # Get object matrix for transformations
            matrix_inv = obj.matrix_world.inverted()
            
            # Transform ray to object space
            obj_ray_origin = matrix_inv @ ray_origin
            obj_ray_direction = matrix_inv.to_3x3() @ view_vector
            
            # Perform ray cast on object
            success, location, normal, index = obj.ray_cast(obj_ray_origin, obj_ray_direction)
            
            if success:
                # Transform hit point back to world space
                hit_point = obj.matrix_world @ location
                # Transform normal back to world space (normals use the transposed inverse)
                world_normal = (matrix_inv.transposed().to_3x3().inverted() @ normal).normalized()
                
                # Calculate distance to hit
                dist = (hit_point - ray_origin).length
                
                # Keep track of closest hit
                if dist < closest_dist:
                    closest_dist = dist
                    closest_hit = hit_point
                    closest_normal = world_normal
        
        # If we found a hit in visible objects
        if closest_hit is not None:
            return closest_hit, closest_normal
        
        # If we didn't hit anything, create a point at a fixed distance
        return ray_origin + view_vector * 10.0, view_vector
    
    def modal(self, context, event):
        """Handle modal events for the operator"""
        self._last_event = event
        self.__class__._last_event = event
        self.__class__._alt_pressed = event.alt

        # Handle R key press to toggle raycast mode
        if event.type == 'R' and event.value == 'PRESS':
            self.__class__._raycast_mode = not self.__class__._raycast_mode
            mode_text = "ON" if self.__class__._raycast_mode else "OFF"
            context.area.tag_redraw()
            context.workspace.status_text_set(
                f"Raycast mode: {mode_text}. Press R to toggle. X to reverse gradient. ESC/Right-click to cancel.")
            return {'RUNNING_MODAL'}

        # Handle X key press to reverse gradient direction
        if event.type == 'X' and event.value == 'PRESS':
            self.__class__._gradient_reversed = not self.__class__._gradient_reversed
            context.area.tag_redraw()
            direction_text = "reversed" if self.__class__._gradient_reversed else "normal"
            context.workspace.status_text_set(
                f"Gradient direction: {direction_text}. Click to sample normal and apply gradient. Press X to toggle direction. R to toggle raycast. ESC/Right-click to cancel.")
            return {'RUNNING_MODAL'}

        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cleanup(context)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Sample the normal at the clicked point
            hit_point, hit_normal = self.get_surface_point(context, event)
            
            if hit_normal:
                # Store the sample point and normal
                self.__class__._draw_sample_point = hit_point
                self.__class__._draw_screen_sample = (event.mouse_region_x, event.mouse_region_y)
                self.__class__._sampled_normal = hit_normal
                
                # Apply the gradient
                self.sample_point = hit_point
                self.sampled_normal = hit_normal
                
                # Store the event state for mask mode detection in execute
                self.alt_pressed = event.alt
                
                # Execute the operator
                self.execute(context)
                
                # Clean up
                self.cleanup(context)
                return {'FINISHED'}
        
        # Update the preview
        if event.type == 'MOUSEMOVE':
            hit_point, hit_normal = self.get_surface_point(context, event)
            
            if hit_normal:
                # Update the preview
                self.__class__._draw_sample_point = hit_point
                self.__class__._draw_screen_sample = (event.mouse_region_x, event.mouse_region_y)
                self.__class__._sampled_normal = hit_normal
                
                # Update the preview color
                gradient = utils.get_active_gradient(context)
                if gradient and utils.get_gradient_color_count(gradient) > 0:
                    self.__class__._draw_preview_color = utils.get_gradient_first_color(gradient)
                
                # Force a redraw
                context.area.tag_redraw()
        
        # Set status text
        raycast_text = "Raycast mode: ON. Press R to toggle." if self.__class__._raycast_mode else "Raycast mode: OFF. Press R to toggle."
        context.workspace.status_text_set(
            f"Click to sample normal and apply gradient. Press X to reverse gradient. {raycast_text} ESC/Right-click to cancel.")
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        """Start the operator"""
        # Check if we're in a valid context
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
        
        # Check if we have a gradient
        if not utils.get_active_gradient(context):
            self.report({'WARNING'}, "No active gradient")
            return {'CANCELLED'}
            
        # Check for valid objects based on mode
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
        
        # Store the area for drawing
        self.__class__._draw_area = context.area
        
        # Add the draw handler
        args = ()
        self.__class__._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.__class__.draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
        
        # Enter modal mode
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        """Execute the operator"""
        # Create a custom event-like object with the alt state from class variable
        event_data = type('EventData', (), {'alt': self.__class__._alt_pressed})()
            
        # Get the active gradient
        use_mask_mode, gradient = utils.apply_mask_mode(context, event_data)
        
        if not gradient:
            self.report({'WARNING'}, "No active gradient")
            return {'CANCELLED'}
        
        # Check if we have a sampled normal
        if not hasattr(self, 'sampled_normal') or not self.sampled_normal:
            self.report({'WARNING'}, "No normal sampled")
            return {'CANCELLED'}
        
        # Get screen space setting from gradient
        use_screen_space = gradient.use_screen_space if hasattr(gradient, 'use_screen_space') else False
        
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
            
        # Process all objects
        for obj in objects:
            
            # Get the mesh data
            depsgraph = context.evaluated_depsgraph_get()
            mesh = obj.evaluated_get(depsgraph).data
            
            # Start timing
            start_time = time.time()
            
            # Set up target attribute (vertex colors or sculpt mask)
            if use_mask_mode:
                # For mask mode, ensure we have a mask attribute
                if context.mode != 'SCULPT':
                    self.report({'WARNING'}, "Mask mode only works in Sculpt mode")
                    continue
                
                # Initialize sculpt mask if needed - use .sculpt_mask as in the other tools
                if not obj.data.attributes.get(".sculpt_mask"):
                    mask_layer = obj.data.attributes.new(name=".sculpt_mask", type='FLOAT', domain='POINT')
                    # Initialize mask values to 0
                    mask_values = np.zeros(len(obj.data.vertices), dtype=np.float32)
                    mask_layer.data.foreach_set("value", mask_values)
                    obj.data.update()
                
                # Use the .sculpt_mask attribute
                target_attribute = obj.data.attributes[".sculpt_mask"]
            else:
                # Get active vertex colors
                target_attribute = utils.ensure_vertex_color_attribute(obj)
                if not target_attribute:
                    self.report({'WARNING'}, f"Could not create or find a color attribute for object {obj.name}")
                    continue
                
                # Make sure the color attribute is active
                obj.data.attributes.active_color = target_attribute
            
                
            # Get vertex positions and normals
            num_verts = len(mesh.vertices)
            
            # Handle Edit mode differently to get up-to-date normals
            if context.mode == 'EDIT_MESH':
                import bmesh
                # Get the BMesh representation
                bm = bmesh.from_edit_mesh(mesh)
                bm.verts.ensure_lookup_table()
                
                # Explicitly update normals in BMesh
                bm.normal_update()
                
                # Get positions and normals from BMesh
                # Get the BMesh vertex count
                bmesh_num_verts = len(bm.verts)
                print(f"BMesh has {bmesh_num_verts} vertices")
                
                # Debug: Check if we have any selected faces
                selected_faces = [f for f in bm.faces if f.select]
                print(f"Edit Mode Debug: {len(selected_faces)} selected faces")
                
                # Make sure normals are up-to-date
                bm.normal_update()
                
                # Debug: Print some normal values
                print("Sample of BMesh normals:")
                sample_count = min(5, len(bm.verts))
                for i in range(sample_count):
                    print(f"Vertex {i} normal: {bm.verts[i].normal}")
                
                # In Edit mode, use the BMesh vertex count for array initialization
                verts = np.empty(bmesh_num_verts * 3, dtype=np.float32)
                normals = np.empty(bmesh_num_verts * 3, dtype=np.float32)
                
                # Get vertex positions and normals from BMesh
                for v in bm.verts:
                    idx = v.index * 3
                    verts[idx:idx+3] = v.co.x, v.co.y, v.co.z
                    normals[idx:idx+3] = v.normal.x, v.normal.y, v.normal.z
                
                # Get selected vertices
                selected_verts = utils.get_selected_vertices(obj)
                
                # Debug selection info
                print(f"\nSelection Debug:")
                print(f"Selected vertices: {len(selected_verts) if selected_verts is not None else 0}")
                print(f"Selection mode: {bpy.context.tool_settings.mesh_select_mode}")
                
                # Force a selection update to ensure face selection is properly detected
                # This is a critical step for Edit mode to work correctly
                if selected_verts is None or len(selected_verts) == 0:
                    print("No vertices selected, checking if we need to sync selection")
                    # Try to sync the selection state
                    bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.ops.object.mode_set(mode='EDIT')
                    # Get selected vertices again
                    selected_verts = utils.get_selected_vertices(obj)
                    print(f"After sync: {len(selected_verts) if selected_verts is not None else 0} vertices selected")
                    
                    # If still no selection, treat as if all vertices are selected
                    # This matches behavior in Object mode
                    if selected_verts is None or len(selected_verts) == 0:
                        print("Still no selection, treating as if all vertices are selected")
                        selected_verts = None  # None means 'all vertices' in our code
            else:
                # In Object mode, use the standard approach
                verts = np.empty(num_verts * 3, dtype=np.float32)
                normals = np.empty(num_verts * 3, dtype=np.float32)
                mesh.vertices.foreach_get("co", verts)
                mesh.vertices.foreach_get("normal", normals)
                verts = verts.reshape(-1, 3)
                normals = normals.reshape(-1, 3)
                selected_verts = None
            
            # Arrays are already properly shaped for Object mode
            # For Edit mode, we need to reshape them here
            if obj.mode == 'EDIT':
                verts = verts.reshape(-1, 3)
                normals = normals.reshape(-1, 3)
            
            # Transform to world space
            matrix = np.array(obj.matrix_world)
            rotation = matrix[:3, :3]
            translation = matrix[:3, 3]
            verts = np.dot(verts, rotation.T) + translation
            
            # Transform normals to world space (only rotation, no translation)
            normals = np.dot(normals, rotation.T)
            
            # Normalize normals to ensure they have unit length
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = normals / np.where(norms > 0, norms, 1.0)
            
            # utils.print_timing(start_time, f"Get vertex positions and normals for {obj.name}")
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
                        mask_data_len = len(mask.data)
                        mask_data = np.empty(mask_data_len, dtype=np.float32)
                        mask.data.foreach_get('value', mask_data)
                        # If you need mask_data to match num_verts, handle mapping after this point.
                        
            # utils.print_timing(start_time, f"Get mask values for {obj.name}")
            start_time = time.time()
            
            # Initialize bmesh_num_verts for Edit mode
            bmesh_num_verts = None
            if obj.mode == 'EDIT':
                import bmesh
                bm = bmesh.from_edit_mesh(obj.data)
                bmesh_num_verts = len(bm.verts)
                print(f"BMesh has {bmesh_num_verts} vertices")
            
            # Process vertices in chunks for better memory usage
            chunk_size = 100000  # Adjust based on available memory
            
            # Use the correct vertex count for chunking
            if obj.mode == 'EDIT' and bmesh_num_verts is not None:
                vertex_count_for_chunks = bmesh_num_verts
                print(f"Using BMesh vertex count for chunks: {vertex_count_for_chunks}")
            else:
                vertex_count_for_chunks = num_verts
                
            num_chunks = (vertex_count_for_chunks + chunk_size - 1) // chunk_size
            
            # Pre-allocate output array
            # In Edit mode, we need to use the BMesh vertex count for array initialization
            if obj.mode == 'EDIT':
                # bmesh_num_verts is already initialized above
                print(f"Initializing arrays with BMesh vertex count: {bmesh_num_verts} instead of {num_verts}")
                
                if use_mask_mode:
                    # For mask mode, use a 1D array
                    final_values = np.empty(bmesh_num_verts, dtype=np.float32)
                    # We'll need to update the mask values later
                else:
                    # For color mode, use a 2D array (vertices × RGBA)
                    final_values = np.empty((bmesh_num_verts, 4), dtype=np.float32)
            else:
                # In Object mode, use the standard approach with mesh vertex count
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
            # Use the correct vertex count based on mode (bmesh_num_verts already initialized above)
            
            if use_mask_mode:
                # For mask mode
                if obj.mode == 'EDIT' and bmesh_num_verts is not None:
                    current_values = np.empty(bmesh_num_verts, dtype=np.float32)
                else:
                    current_values = np.empty(num_verts, dtype=np.float32)
                    
                if need_current_values and obj.mode != 'EDIT':
                    target_attribute.data.foreach_get('value', current_values)
            else:
                # For color mode
                if obj.mode == 'EDIT' and bmesh_num_verts is not None:
                    current_values = np.ones((bmesh_num_verts, 4), dtype=np.float32)
                else:
                    current_values = np.ones((num_verts, 4), dtype=np.float32)
                    
                if need_current_values:
                    # In Edit mode, we need to use BMesh to get colors with proper color space conversion
                    if obj.mode == 'EDIT':
                        # Use the actual number of vertices from the BMesh, not the mesh data
                        import bmesh
                        bm = bmesh.from_edit_mesh(obj.data)
                        bmesh_num_verts = len(bm.verts)
                        print(f"Using BMesh vertex count: {bmesh_num_verts} instead of mesh vertex count: {num_verts}")
                        current_values = utils.get_vertex_colors_from_bmesh(obj, bmesh_num_verts)
                    else:
                        # In Object mode, we can use foreach_get
                        try:
                            # Check if the object has modifiers that might affect vertex count
                            has_modifiers = len(obj.modifiers) > 0
                            print(f"[DEBUG] Object has modifiers: {has_modifiers}")
                            
                            # Get the expected length of the attribute data
                            expected_length = 0
                            if target_attribute.domain == 'POINT':
                                expected_length = len(obj.data.vertices) * 4  # RGBA = 4 components
                            elif target_attribute.domain == 'CORNER':
                                expected_length = len(obj.data.loops) * 4  # RGBA = 4 components
                            elif target_attribute.domain == 'FACE':
                                expected_length = len(obj.data.polygons) * 4  # RGBA = 4 components
                            
                            print(f"[DEBUG] Expected attribute length: {expected_length}")
                            print(f"[DEBUG] Requested array length: {num_verts * 4}")
                            
                            # Use the correct size for the temporary array
                            if expected_length > 0:
                                temp_values = np.empty(expected_length, dtype=np.float32)
                            else:
                                temp_values = np.empty(num_verts * 4, dtype=np.float32)
                                
                            # Get the color data
                            target_attribute.data.foreach_get('color', temp_values)
                            
                            # Reshape to get RGBA values
                            current_values = temp_values.reshape(-1, 4)
                            
                            # If the reshaped array doesn't match our expected number of vertices,
                            # we need to adjust it
                            if len(current_values) != num_verts:
                                print(f"[DEBUG] Vertex count mismatch: got {len(current_values)}, expected {num_verts}")
                                if len(current_values) < num_verts:
                                    # Pad with default values if we have fewer vertices than expected
                                    padding = np.ones((num_verts - len(current_values), 4), dtype=np.float32)
                                    current_values = np.vstack([current_values, padding])
                                else:
                                    # Truncate if we have more vertices than expected
                                    current_values = current_values[:num_verts]
                        except Exception as e:
                            print(f"[DEBUG] Error getting color data with foreach_get: {e}")
                            print(f"[DEBUG] Falling back to per-vertex color retrieval")
                            
                            # Fallback: Get colors one by one
                            current_values = np.ones((num_verts, 4), dtype=np.float32)
                            try:
                                for i in range(min(len(target_attribute.data), num_verts)):
                                    current_values[i] = target_attribute.data[i].color
                            except Exception as e2:
                                print(f"[DEBUG] Fallback method also failed: {e2}")
                                # If all else fails, just use default white color
                                current_values = np.ones((num_verts, 4), dtype=np.float32)
            
            # Get the sampled normal as a numpy array
            sampled_normal = np.array(self.sampled_normal, dtype=np.float32)
            sampled_normal = sampled_normal / np.linalg.norm(sampled_normal)

            from mathutils import Vector
            from mathutils.bvhtree import BVHTree
            depsgraph = context.evaluated_depsgraph_get()
            bvh = BVHTree.FromObject(obj, depsgraph)

            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * chunk_size
                if obj.mode == 'EDIT' and bmesh_num_verts is not None:
                    end_idx = min(start_idx + chunk_size, bmesh_num_verts)
                else:
                    end_idx = min(start_idx + chunk_size, num_verts)
                process_chunk = True
                if selected_verts is not None:
                    chunk_indices = np.arange(start_idx, end_idx)
                    mask = np.isin(chunk_indices, selected_verts)
                    process_chunk = np.any(mask)
                if not process_chunk:
                    continue
                if obj.mode == 'EDIT':
                    chunk_normals = normals[start_idx*3:end_idx*3].reshape(-1, 3)
                else:
                    chunk_normals = normals[start_idx:end_idx]
                dot_products = np.sum(chunk_normals * sampled_normal, axis=1)
                if chunk_idx == 0:
                    print("\nSampled normal:", sampled_normal)
                    print("Chunk normals shape:", chunk_normals.shape)
                    print("Chunk indices:", start_idx, "to", end_idx)
                    if len(dot_products) > 0:
                        print("Dot product range:", np.min(dot_products), "to", np.max(dot_products))
                        sample_indices = min(5, len(dot_products))
                        print("Sample dot products:", dot_products[:sample_indices])
                    else:
                        print("No dot products calculated (empty chunk)")
                    if selected_verts is not None:
                        selected_in_chunk = np.isin(np.arange(start_idx, end_idx), selected_verts)
                        print(f"Selected vertices in this chunk: {np.sum(selected_in_chunk)} out of {len(dot_products)}")

                # --- Raycast mode logic ---
                if self.__class__._raycast_mode:
                    verts_chunk = verts[start_idx:end_idx]
                    shadowed = np.zeros(len(verts_chunk), dtype=bool)
                    if obj.mode == 'OBJECT':
                        # Build BVHs for all selected mesh objects
                        selected_mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
                        bvhs = []
                        obj_matrices = []
                        obj_inv_matrices = []
                        depsgraph = context.evaluated_depsgraph_get()
                        for o in selected_mesh_objs:
                            bvhs.append(BVHTree.FromObject(o, depsgraph))
                            obj_matrices.append(o.matrix_world)
                            obj_inv_matrices.append(o.matrix_world.inverted())
                        for vi, vco in enumerate(verts_chunk):
                            shadowed_found = False
                            for bvh_idx, bvh_other in enumerate(bvhs):
                                # Transform ray to this object's local space
                                inv = obj_inv_matrices[bvh_idx]
                                normal_obj = inv.to_3x3() @ Vector(sampled_normal)
                                normal_obj.normalize()
                                vco_obj = inv @ Vector(vco)
                                ray_origin = vco_obj + normal_obj * 1e-4
                                hit = bvh_other.ray_cast(ray_origin, normal_obj, 1e6)
                                if hit is not None:
                                    hit_point, hit_normal, hit_index, hit_dist = hit
                                    if hit_dist is not None and hit_dist > 1e-5:
                                        shadowed_found = True
                                        break
                            shadowed[vi] = shadowed_found
                    else:
                        # Edit mode: only self
                        obj_matrix_inv = obj.matrix_world.inverted()
                        sampled_normal_obj = obj_matrix_inv.to_3x3() @ Vector(sampled_normal)
                        sampled_normal_obj.normalize()
                        for vi, vco in enumerate(verts_chunk):
                            vco_obj = obj_matrix_inv @ Vector(vco)
                            ray_origin = vco_obj + sampled_normal_obj * 1e-4
                            hit = bvh.ray_cast(ray_origin, sampled_normal_obj, 1e6)
                            if hit is not None:
                                hit_point, hit_normal, hit_index, hit_dist = hit
                                if hit_dist is not None and hit_dist > 1e-5:
                                    shadowed[vi] = True
                    last_color = np.array(utils.get_gradient_last_color(gradient))
                    if use_mask_mode:
                        factors = (dot_products + 1.0) * 0.5
                        if self.__class__._gradient_reversed:
                            factors = 1.0 - factors
                        new_values = np.where(shadowed, 1.0, factors)
                        chunk_current = final_values[start_idx:end_idx]
                        opacity_blended_values = chunk_current * (1 - opacity) + new_values * opacity
                        final_values[start_idx:end_idx] = opacity_blended_values
                    else:
                        factors = (1.0 - dot_products) * 0.5
                        if self.__class__._gradient_reversed:
                            factors = 1.0 - factors
                        new_colors = utils.interpolate_gradient_colors_batch(gradient, factors)
                        for vi in range(len(verts_chunk)):
                            if shadowed[vi]:
                                new_colors[vi] = last_color
                        chunk_current = current_values[start_idx:end_idx]
                        opacity_blended_colors = utils.apply_blend_mode(
                            chunk_current, new_colors, blend_mode, opacity)
                        if use_existing_mask:
                            chunk_mask = mask_data[start_idx:end_idx]
                            final_values[start_idx:end_idx] = chunk_current * chunk_mask[:, np.newaxis] + opacity_blended_colors * (1 - chunk_mask[:, np.newaxis])
                        elif selected_verts is not None:
                            chunk_indices = np.arange(start_idx, end_idx)
                            mask = np.isin(chunk_indices, selected_verts)
                            broadcast_mask = mask[:, np.newaxis]
                            if chunk_current is None:
                                chunk_current = current_values[start_idx:end_idx]
                            final_values[start_idx:end_idx] = np.where(broadcast_mask, opacity_blended_colors, chunk_current)
                        else:
                            final_values[start_idx:end_idx] = opacity_blended_colors
                    continue
                # --- End raycast mode logic ---

                # Normal logic (non-raycast mode):
                if use_mask_mode:
                    factors = (dot_products + 1.0) * 0.5
                    if self.__class__._gradient_reversed:
                        factors = 1.0 - factors
                else:
                    factors = (1.0 - dot_products) * 0.5
                    if self.__class__._gradient_reversed:
                        factors = 1.0 - factors
                if chunk_idx == 0:
                    print("Factor range:", np.min(factors), "to", np.max(factors))
                    print("Sample factors:", factors[:sample_indices])
                if use_mask_mode:
                    new_values = factors
                    chunk_current = final_values[start_idx:end_idx]
                    opacity_blended_values = chunk_current * (1 - opacity) + new_values * opacity
                    final_values[start_idx:end_idx] = opacity_blended_values
                else:
                    new_colors = utils.interpolate_gradient_colors_batch(gradient, factors)
                    chunk_current = None
                    if need_current_values:
                        chunk_current = current_values[start_idx:end_idx]
                    if chunk_current is None:
                        chunk_current = current_values[start_idx:end_idx]
                    opacity_blended_colors = utils.apply_blend_mode(
                        chunk_current, 
                        new_colors, 
                        blend_mode, 
                        opacity
                        )
                    if use_existing_mask:
                        chunk_mask = mask_data[start_idx:end_idx]
                        final_values[start_idx:end_idx] = chunk_current * chunk_mask[:, np.newaxis] + opacity_blended_colors * (1 - chunk_mask[:, np.newaxis])
                    elif selected_verts is not None:
                        chunk_indices = np.arange(start_idx, end_idx)
                        mask = np.isin(chunk_indices, selected_verts)
                        broadcast_mask = mask[:, np.newaxis]
                        if chunk_current is None:
                            chunk_current = current_values[start_idx:end_idx]
                        final_values[start_idx:end_idx] = np.where(broadcast_mask, opacity_blended_colors, chunk_current)
                    else:
                        final_values[start_idx:end_idx] = opacity_blended_colors

            # Update color attribute or mask
            if use_mask_mode:
                target_attribute.data.foreach_set("value", final_values)
                # mesh.update() removed: Blender updates mesh data automatically
            else:
                print(f"\nFinal update for {obj.name}:")
                print(f"Final values shape: {final_values.shape}")
                print(f"Target attribute: {target_attribute}")
                print(f"Selected verts: {'Yes' if selected_verts is not None else 'No'} ({len(selected_verts) if selected_verts is not None else 0} vertices)")
                if len(final_values) > 0:
                    print(f"Sample final values (first 3): {final_values[:3]}")
                utils.update_color_attribute(obj, target_attribute, final_values, selected_verts)
                print("Color attribute update completed.")
        # utils.print_timing(start_time, f"Apply gradient to {obj.name}")
        return {'FINISHED'}
