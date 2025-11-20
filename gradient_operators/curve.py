"""
Curve gradient operator for vColorTools addon
Applies a gradient along a curve defined by three control points
"""

import bpy
import gpu
import numpy as np
import time
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry
from bpy_extras import view3d_utils
from .. import utils

class VGRADIENT_OT_curve(bpy.types.Operator):
    """Apply a gradient along a curve defined by three control points"""
    bl_idname = "vgradient.curve"
    bl_label = "Curve"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a gradient along a curve defined by three control points. Hold Alt to apply as sculpt mask"
    
    # Class variables for drawing state
    _handle = None
    _draw_points = []  # List of 3D points defining the curve
    _draw_screen_points = []  # List of 2D screen points
    _draw_current_point = None  # Current mouse position
    _draw_preview_color = (1, 1, 1, 1)
    _draw_area = None
    _last_event = None
    _alt_pressed = False  # Track Alt key state at class level
    _gradient_reversed = False  # Track if gradient direction is reversed
    _curve_points = None  # Cached curve points for drawing
    _curve_screen_points = None  # Cached curve screen points
    _curve_resolution = 20  # Number of points to use for curve visualization
    _active_point_index = -1  # Index of the point being repositioned (-1 means none)
    _point_radius = 20  # Radius for control point selection (matches the 40 pixel diameter pick circle)
    
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
            cls._draw_points = []
            cls._draw_screen_points = []
            cls._draw_current_point = None
            cls._draw_preview_color = (1, 1, 1, 1)
            cls._draw_area = None
            cls._last_event = None
            cls._gradient_reversed = False  # Reset gradient direction
            cls._curve_points = None
            cls._curve_screen_points = None
            cls._active_point_index = -1
            if context:
                try:
                    context.workspace.status_text_set(None)
                    context.area.tag_redraw()
                except:
                    pass
    
    @classmethod
    def draw_callback_px(cls, *args):
        """Draw the preview curve and points"""
        try:
            # Get current context
            context = bpy.context
            if not cls._draw_area or context.area != cls._draw_area:
                return
                
            # Get UI scale factor for consistent appearance across platforms
            ui_scale = utils.get_ui_scale(context)
            
            # Set base line width with UI scaling
            gpu.state.line_width_set(2 * ui_scale)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            
            # Draw control points if we have any
            for i, screen_point in enumerate(cls._draw_screen_points):
                # Determine if this is the active point being repositioned
                is_active = (i == cls._active_point_index)
                
                # Set color based on whether point is active
                if is_active:
                    shader.uniform_float("color", (1, 0.5, 0, 1))  # Orange for active point
                else:
                    shader.uniform_float("color", (1, 1, 1, 1))  # White for inactive points
                
                x, y = screen_point
                # Scale the crosshair size based on UI scale
                size = 10 * ui_scale
                gpu.state.blend_set('ALPHA')
                
                # Draw crosshair
                batch = batch_for_shader(shader, 'LINES', {"pos": [
                    (x - size, y), (x + size, y),
                    (x, y - size), (x, y + size)
                ]})
                batch.draw(shader)
                
                # Draw pick circle around point (40 pixels diameter = 20 radius)
                # Scale the radius based on UI scale
                pick_radius = 20 * ui_scale
                segments = 32
                
                # Set color based on whether point is active (green if active, white if not)
                if is_active:
                    shader.uniform_float("color", (0.2, 1.0, 0.2, 1.0))  # Green for active point
                else:
                    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.8))  # White for inactive points
                
                # Create circle vertices
                circle_verts = [(x + pick_radius * math.cos(angle), y + pick_radius * math.sin(angle)) 
                               for angle in [i * 2 * math.pi / segments for i in range(segments)]]
                
                # Draw circle outline
                batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": circle_verts})
                batch.draw(shader)
                
                # Draw point number
                # TODO: Add text rendering for point numbers if needed
            
            # Draw curve if we have at least 2 points
            if len(cls._draw_points) >= 2:
                # If we have 2 points, draw a straight line
                if len(cls._draw_points) == 2:
                    x1, y1 = cls._draw_screen_points[0]
                    x2, y2 = cls._draw_screen_points[1]
                    
                    # Get the active gradient
                    gradient = utils.get_active_gradient(context)
                    
                    # Check if we're in mask mode
                    use_mask_mode = context.mode == 'SCULPT' and cls._alt_pressed
                    
                    # Create subdivided points along the line
                    num_segments = 20
                    line_points = []
                    for i in range(num_segments + 1):
                        t = i / num_segments
                        x = x1 + (x2 - x1) * t
                        y = y1 + (y2 - y1) * t
                        line_points.append((x, y))
                    
                    # Calculate perpendicular direction for thick line
                    dx = x2 - x1
                    dy = y2 - y1
                    length = math.sqrt(dx*dx + dy*dy)
                    if length > 0:
                        # Normalize and get perpendicular vector
                        dx, dy = dx/length, dy/length
                        # Perpendicular vector
                        px, py = -dy, dx
                    else:
                        px, py = 0, 1
                    
                    # Thickness of the line (in pixels)
                    thickness = 10 * ui_scale
                    
                    if use_mask_mode:
                        # In mask mode, use a white line
                        shader.uniform_float("color", (1, 1, 1, 1))
                        
                        # Draw as a thick polygon
                        for i in range(len(line_points) - 1):
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
                        # Draw the line as a thick gradient-colored line using quads
                        for i in range(len(line_points) - 1):
                            # Calculate the factor (0-1) for this segment
                            t = i / (len(line_points) - 1)
                            
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
                # If we have 3 points, draw a quadratic Bezier curve
                elif len(cls._draw_points) == 3:
                    # Generate curve points if not already cached
                    if not cls._curve_screen_points:
                        # We'll use the 3 points as a quadratic Bezier curve
                        p0 = Vector((cls._draw_screen_points[0][0], cls._draw_screen_points[0][1], 0))
                        p1 = Vector((cls._draw_screen_points[1][0], cls._draw_screen_points[1][1], 0))
                        p2 = Vector((cls._draw_screen_points[2][0], cls._draw_screen_points[2][1], 0))
                        
                        # Generate points along the curve
                        curve_points = []
                        for i in range(cls._curve_resolution + 1):
                            t = i / cls._curve_resolution
                            # Quadratic Bezier formula: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
                            point = (1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2
                            curve_points.append((point.x, point.y))
                        
                        cls._curve_screen_points = curve_points
                    
                    # Get the active gradient
                    gradient = utils.get_active_gradient(context)
                    
                    # Check if we're in mask mode
                    use_mask_mode = context.mode == 'SCULPT' and cls._alt_pressed
                    
                    # Thickness of the line (in pixels)
                    thickness = 10 * ui_scale
                    
                    if use_mask_mode:
                        # For mask mode, show a black-to-white gradient
                        # Draw the curve as a thick gradient-colored line using quads
                        for i in range(len(cls._curve_screen_points) - 1):
                            # Calculate the factor (0-1) for this segment
                            t = i / (len(cls._curve_screen_points) - 1)
                            
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
                            
                            p1 = cls._curve_screen_points[i]
                            p2 = cls._curve_screen_points[i + 1]
                            
                            # Calculate direction vector for this segment
                            dx = p2[0] - p1[0]
                            dy = p2[1] - p1[1]
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Normalize and get perpendicular vector
                                dx, dy = dx/length, dy/length
                                # Perpendicular vector
                                px, py = -dy, dx
                            else:
                                px, py = 0, 1
                            
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
                        # Draw the curve as a thick gradient-colored line using quads
                        for i in range(len(cls._curve_screen_points) - 1):
                            # Calculate the factor (0-1) for this segment
                            t = i / (len(cls._curve_screen_points) - 1)
                            
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
                            
                            p1 = cls._curve_screen_points[i]
                            p2 = cls._curve_screen_points[i + 1]
                            
                            # Calculate direction vector for this segment
                            dx = p2[0] - p1[0]
                            dy = p2[1] - p1[1]
                            length = math.sqrt(dx*dx + dy*dy)
                            if length > 0:
                                # Normalize and get perpendicular vector
                                dx, dy = dx/length, dy/length
                                # Perpendicular vector
                                px, py = -dy, dx
                            else:
                                px, py = 0, 1
                            
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
            
            # Draw line from last point to current mouse position if we're placing points
            if cls._draw_screen_points and cls._draw_current_point and len(cls._draw_points) < 3:
                x1, y1 = cls._draw_screen_points[-1]
                x2, y2 = cls._draw_current_point
                batch = batch_for_shader(shader, 'LINES', {"pos": [
                    (x1, y1), (x2, y2)
                ]})
                batch.draw(shader)
                    
            # Draw color preview circle - only if we don't have all 3 points placed yet
            if cls._draw_current_point and len(cls._draw_points) < 3:
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
        except Exception as e:
            print(f"Error in draw_callback_px: {e}")
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
            return result[1], result[2]  # Return location, normal
        else:
            # If we didn't hit anything, create a point 10 units away from the camera
            # along the view vector
            return ray_origin + view_vector * 10.0, view_vector
    
    def update_preview_color(self, context, event):
        """Update the preview color based on the current mouse position and point placement progress"""
        # Get the gradient
        gradient = utils.get_active_gradient(context)
        if not gradient:
            return
        
        # Set preview color based on number of points placed
        num_points = len(self._draw_points)
        
        if num_points == 0:
            # No points placed yet - show first or last color based on gradient direction
            if gradient.colors:
                # Get the appropriate color based on gradient direction
                color_index = -1 if self.__class__._gradient_reversed else 0
                linear_color = gradient.colors[color_index].color
                
                # Convert from linear to sRGB for display
                display_color = (utils.linear_to_srgb(linear_color[0]), 
                               utils.linear_to_srgb(linear_color[1]), 
                               utils.linear_to_srgb(linear_color[2]), 
                               linear_color[3])
                self.__class__._draw_preview_color = display_color
            return
        elif num_points == 1:
            # One point placed - show middle color in gradient
            if gradient.colors and len(gradient.colors) > 1:
                # Find the middle color or interpolate between colors
                if self.__class__._gradient_reversed:
                    # For reversed gradient, use a color from the first half
                    middle_idx = len(gradient.colors) // 4
                else:
                    # For normal gradient, use a color from the second half
                    middle_idx = (len(gradient.colors) * 3) // 4
                
                # Ensure index is within bounds
                middle_idx = max(0, min(len(gradient.colors) - 1, middle_idx))
                
                linear_color = gradient.colors[middle_idx].color
                # Convert from linear to sRGB for display
                display_color = (utils.linear_to_srgb(linear_color[0]), 
                               utils.linear_to_srgb(linear_color[1]), 
                               utils.linear_to_srgb(linear_color[2]), 
                               linear_color[3])
                self.__class__._draw_preview_color = display_color
            return
        
        # For 2 points, calculate based on mouse position
        # Get the current mouse position in 3D
        current_point, _ = self.get_surface_point(context, event)
        
        # Calculate the closest point on the curve to the current mouse position
        if len(self._draw_points) == 2:
            # For 2 points, use the closest point on the line
            line_start = self._draw_points[0]
            line_end = self._draw_points[1]
            
            # Calculate closest point on line
            line_vec = line_end - line_start
            line_len = line_vec.length
            line_dir = line_vec / line_len if line_len > 0 else Vector((0, 0, 0))
            
            # Project current point onto line
            v = current_point - line_start
            d = v.dot(line_dir)
            
            # Clamp to line segment
            d = max(0, min(line_len, d))
            
            # Calculate factor (0-1) along the line
            factor = d / line_len if line_len > 0 else 0
            
            # Reverse the factor if needed
            if self.__class__._gradient_reversed:
                factor = 1.0 - factor
            
        elif len(self._draw_points) == 3:
            # For 3 points, use the closest point on the quadratic Bezier curve
            p0 = self._draw_points[0]
            p1 = self._draw_points[1]
            p2 = self._draw_points[2]
            
            # Generate points along the curve if not already cached
            if not self._curve_points:
                curve_points = []
                for i in range(self._curve_resolution + 1):
                    t = i / self._curve_resolution
                    # Quadratic Bezier formula: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
                    point = (1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2
                    curve_points.append((point, t))  # Store point and t value
                
                self._curve_points = curve_points
            
            # Find closest point on curve
            closest_dist = float('inf')
            closest_t = 0
            
            for point, t in self._curve_points:
                dist = (Vector(point) - current_point).length
                if dist < closest_dist:
                    closest_dist = dist
                    closest_t = t
            
            # Use t as the factor
            factor = closest_t
            
            # Reverse the factor if needed
            if self.__class__._gradient_reversed:
                factor = 1.0 - factor
        
        # Get color at this factor (in linear space)
        linear_color = utils.interpolate_gradient_color(gradient, factor)
        
        # Convert from linear to sRGB for display
        display_color = (utils.linear_to_srgb(linear_color[0]), 
                       utils.linear_to_srgb(linear_color[1]), 
                       utils.linear_to_srgb(linear_color[2]), 
                       linear_color[3])
        
        # Update preview color
        self.__class__._draw_preview_color = display_color
    
    def find_closest_point(self, mouse_x, mouse_y):
        """Find the closest control point to the given mouse coordinates"""
        closest_index = -1
        closest_dist = float('inf')
        
        # Get UI scale factor for consistent selection across platforms
        ui_scale = utils.get_ui_scale(bpy.context)
        # Apply UI scale to the selection radius
        scaled_radius = self.__class__._point_radius * ui_scale
        
        for i, (x, y) in enumerate(self.__class__._draw_screen_points):
            dist = math.sqrt((mouse_x - x)**2 + (mouse_y - y)**2)
            if dist < closest_dist and dist <= scaled_radius:
                closest_dist = dist
                closest_index = i
                
        return closest_index
    
    def modal(self, context, event):
        """Handle modal events"""
        # Store the event for use in the draw callback
        self.__class__._last_event = event
        
        # Update current mouse position for drawing
        if event.type == 'MOUSEMOVE':
            self.__class__._draw_current_point = (event.mouse_region_x, event.mouse_region_y)
            
            # If we're repositioning a point, update its position
            if self.__class__._active_point_index >= 0:
                # Update screen position
                self.__class__._draw_screen_points[self.__class__._active_point_index] = (event.mouse_region_x, event.mouse_region_y)
                
                # Update 3D position
                point, normal = self.get_surface_point(context, event)
                self.__class__._draw_points[self.__class__._active_point_index] = point
                
                # Clear cached curve points when moving control points
                self.__class__._curve_points = None
                self.__class__._curve_screen_points = None
            
            context.area.tag_redraw()
            
            # Update preview color
            self.update_preview_color(context, event)
        
        # Track Alt key state at class level for sculpt mask mode
        if event.type == 'LEFT_ALT' or event.type == 'RIGHT_ALT':
            if event.value == 'PRESS':
                self.__class__._alt_pressed = True
                context.area.tag_redraw()
            elif event.value == 'RELEASE':
                self.__class__._alt_pressed = False
                context.area.tag_redraw()
                
        # Handle X key press to reverse gradient direction
        if event.type == 'X' and event.value == 'PRESS':
            self.__class__._gradient_reversed = not self.__class__._gradient_reversed
            # Clear cached curve points to force redraw with new gradient direction
            self.__class__._curve_points = None
            self.__class__._curve_screen_points = None
            context.area.tag_redraw()
            # Update status text to indicate the gradient direction
            direction_text = "reversed" if self.__class__._gradient_reversed else "normal"
            if len(self.__class__._draw_points) == 3:
                context.workspace.status_text_set(
                    f"Gradient direction: {direction_text}. Click and drag points to reposition. Press X to toggle direction. Press ENTER to apply gradient, ESC to cancel")
            else:
                context.workspace.status_text_set(
                    f"Gradient direction: {direction_text}. Press X to toggle direction. Press ENTER to apply gradient, ESC to cancel")
            return {'RUNNING_MODAL'}
        
        # Handle left mouse button to place or reposition points
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # If we already have 3 points, check if we're clicking on an existing point
            if len(self.__class__._draw_points) == 3:
                point_index = self.find_closest_point(event.mouse_region_x, event.mouse_region_y)
                if point_index >= 0:
                    # Start repositioning this point
                    self.__class__._active_point_index = point_index
                    context.workspace.status_text_set(f"Repositioning point {point_index+1}. Release mouse to confirm.")
                    return {'RUNNING_MODAL'}
            
            # If we're not repositioning a point, place a new one
            if self.__class__._active_point_index < 0 and len(self.__class__._draw_points) < 3:
                # Get the 3D point under the mouse
                point, normal = self.get_surface_point(context, event)
                
                # Add the point to our list (max 3 points)
                self.__class__._draw_points.append(point)
                self.__class__._draw_screen_points.append((event.mouse_region_x, event.mouse_region_y))
                
                # Clear cached curve points when adding new control points
                self.__class__._curve_points = None
                self.__class__._curve_screen_points = None
                
                # If we have 3 points, we're ready to apply the gradient
                if len(self.__class__._draw_points) == 3:
                    # Update status text
                    context.workspace.status_text_set("Click and drag points to reposition. Press X to reverse gradient. Press ENTER to apply gradient, ESC to cancel")
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        # Handle mouse release to finish repositioning
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.__class__._active_point_index >= 0:
                # Stop repositioning
                self.__class__._active_point_index = -1
                context.workspace.status_text_set("Click and drag points to reposition. Press X to reverse gradient. Press ENTER to apply gradient, ESC to cancel")
                return {'RUNNING_MODAL'}
        
        # Apply gradient on Enter/Return if we have 3 points
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if len(self.__class__._draw_points) == 3:
                # Apply the gradient
                self.apply_gradient(context, event)
                
                # Clean up
                self.cleanup(context)
                return {'FINISHED'}
            else:
                # Not enough points yet
                self.report({'WARNING'}, "Please place 3 points to define the curve")
                return {'RUNNING_MODAL'}
        
        # Cancel on Escape or right click
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cleanup(context)
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        """Start the operator"""
        # Check if we have a gradient
        if not utils.get_active_gradient(context):
            self.report({'WARNING'}, "No gradient available. Create a gradient first.")
            return {'CANCELLED'}
        
        # Check if we're in a supported mode
        if context.mode not in {'OBJECT', 'EDIT_MESH', 'SCULPT'}:
            self.report({'WARNING'}, "Curve gradient only works in Object, Edit, or Sculpt mode")
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
        
        # Reset class variables
        self.__class__._draw_points = []
        self.__class__._draw_screen_points = []
        self.__class__._draw_current_point = (event.mouse_region_x, event.mouse_region_y)
        self.__class__._draw_preview_color = (1, 1, 1, 1)
        self.__class__._draw_area = context.area
        self.__class__._curve_points = None
        self.__class__._curve_screen_points = None
        self.__class__._active_point_index = -1
        
        # Store Alt key state
        self.__class__._alt_pressed = event.alt
        
        # Add the draw handler
        args = ()
        self.__class__._handle = bpy.types.SpaceView3D.draw_handler_add(
            self.__class__.draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
        
        # Set status text
        context.workspace.status_text_set("Click to place curve points (3 required). After placing, click and drag points to reposition. Press ESC to cancel")
        
        # Enter modal mode
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def apply_gradient(self, context, event):
        """Apply the gradient to the mesh"""
        total_start = time.time()
        setup_start = time.time()
        
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
        
        # Check if we should apply as sculpt mask
        use_mask_mode, gradient = utils.apply_mask_mode(context, event)
        
        # Get the curve points
        p0 = self.__class__._draw_points[0]
        p1 = self.__class__._draw_points[1]
        p2 = self.__class__._draw_points[2]
        
        utils.print_timing(setup_start, "Initial setup time")
        
        # Process vertices in chunks for better memory usage
        chunk_size = 50000  # Adjust based on available memory and performance
        
        # Process each object
        for obj_idx, obj in enumerate(objects):
            obj_start = time.time()
            mesh = obj.data
            
            # Handle either vertex colors or sculpt mask
            if use_mask_mode:
                mask_start = time.time()
                # Ensure we're in sculpt mode
                if context.mode != 'SCULPT':
                    self.report({'WARNING'}, "Mask mode only works in sculpt mode")
                    return {'CANCELLED'}
                    
                # Initialize sculpt mask if needed
                if not obj.data.attributes.get(".sculpt_mask"):
                    mask_layer = obj.data.attributes.new(name=".sculpt_mask", type='FLOAT', domain='POINT')
                
                target_attribute = obj.data.attributes[".sculpt_mask"]
                utils.print_timing(mask_start, "Mask setup time")
                
                # Get vertex positions
                vert_start = time.time()
                num_verts = len(mesh.vertices)
                num_chunks = (num_verts + chunk_size - 1) // chunk_size
                
                # Transform vertices to world space
                vert_positions = np.zeros(num_verts * 3, dtype=np.float32)
                mesh.vertices.foreach_get('co', vert_positions)
                vert_positions = vert_positions.reshape(num_verts, 3)
                vert_positions = utils.transform_verts_to_world_batch(vert_positions, obj.matrix_world)
                utils.print_timing(vert_start, "Get vertex positions time")
                
                # Calculate gradient factors for each vertex
                factor_start = time.time()
                factors = self.calculate_curve_factors(vert_positions, p0, p1, p2, gradient)
                utils.print_timing(factor_start, "Calculate factors time")
                
                # Apply symmetry if needed
                symmetry_start = time.time()
                symmetry_data = utils.get_symmetry_data(obj, context)
                if symmetry_data['use_symmetry']:
                    factors = utils.apply_symmetry_to_factors(vert_positions, factors, symmetry_data)
                utils.print_timing(symmetry_start, "Apply symmetry time")
                
                # Update the mask attribute in chunks
                update_start = time.time()
                for chunk_idx in range(num_chunks):
                    chunk_start = time.time()
                    start_idx = chunk_idx * chunk_size
                    end_idx = min(start_idx + chunk_size, num_verts)
                    
                    # Get factors for this chunk
                    chunk_factors = factors[start_idx:end_idx]
                    
                    # Update the mask attribute for this chunk
                    for i, factor in enumerate(chunk_factors):
                        target_attribute.data[start_idx + i].value = factor
                    
                    utils.print_timing(chunk_start, f"Process mask chunk {chunk_idx+1}/{num_chunks}")
                
                utils.print_timing(update_start, "Update mask attribute time")
                
            else:
                color_start = time.time()
                # Get active vertex colors
                target_attribute = utils.ensure_vertex_color_attribute(obj)
                if not target_attribute:
                    self.report({'WARNING'}, f"Could not create or find a color attribute for object {obj.name}")
                    continue
                
                # Make sure the color attribute is active
                obj.data.attributes.active_color = target_attribute
                utils.print_timing(color_start, "Color attribute setup time")
                
                # Get global opacity for blending
                opacity = context.scene.vgradient_global_opacity
                blend_mode = context.scene.vgradient_blend_mode
                
                # Get vertex positions
                vert_start = time.time()
                num_verts = len(mesh.vertices)
                num_chunks = (num_verts + chunk_size - 1) // chunk_size
                
                # Transform vertices to world space
                vert_positions = np.zeros(num_verts * 3, dtype=np.float32)
                mesh.vertices.foreach_get('co', vert_positions)
                vert_positions = vert_positions.reshape(num_verts, 3)
                vert_positions = utils.transform_verts_to_world_batch(vert_positions, obj.matrix_world)
                utils.print_timing(vert_start, "Get vertex positions time")
                
                # Get mask values if in sculpt mode and not in mask mode
                mask_start = time.time()
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
                utils.print_timing(mask_start, "Get mask values time")
                
                # Get selected vertices in Edit mode
                selection_start = time.time()
                selected_verts = None
                if context.mode == 'EDIT_MESH':
                    selected_verts = utils.get_selected_vertices(obj)
                    if selected_verts is not None and len(selected_verts) == 0:
                        selected_verts = None  # Treat empty selection as all vertices
                utils.print_timing(selection_start, "Get selected vertices time")
                
                # Calculate gradient factors for each vertex
                factor_start = time.time()
                factors = self.calculate_curve_factors(vert_positions, p0, p1, p2, gradient, selected_verts)
                utils.print_timing(factor_start, "Calculate factors time")
                
                # Apply symmetry if needed
                symmetry_start = time.time()
                symmetry_data = utils.get_symmetry_data(obj, context)
                if symmetry_data['use_symmetry']:
                    factors = utils.apply_symmetry_to_factors(vert_positions, factors, symmetry_data)
                utils.print_timing(symmetry_start, "Apply symmetry time")
                
                # Pre-allocate final colors array
                final_colors = np.zeros((num_verts, 4), dtype=np.float32)
                
                # Always get existing colors to ensure alpha values are respected
                # This is critical for proper blending with color stop alpha values
                existing_start = time.time()
                existing_colors = None
                
                # In Edit mode, we need to use BMesh to get colors
                if obj.mode == 'EDIT':
                    existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
                else:
                    # In Object mode, we can use foreach_get
                    existing_colors = np.zeros(num_verts * 4, dtype=np.float32)
                    target_attribute.data.foreach_get("color", existing_colors)
                    existing_colors = existing_colors.reshape(num_verts, 4)
                
                # Initialize final colors with existing colors
                final_colors = existing_colors.copy()
                utils.print_timing(existing_start, "Get existing colors time")
                
                # Process colors in chunks
                color_process_start = time.time()
                for chunk_idx in range(num_chunks):
                    chunk_start = time.time()
                    start_idx = chunk_idx * chunk_size
                    end_idx = min(start_idx + chunk_size, num_verts)
                    
                    # Skip this chunk if no vertices are selected
                    process_chunk = True
                    if selected_verts is not None:
                        # Find which vertices in this chunk are selected
                        chunk_indices = np.arange(start_idx, end_idx)
                        mask = np.isin(chunk_indices, selected_verts)
                        process_chunk = np.any(mask)
                    
                    if not process_chunk:
                        continue
                    
                    # Get factors for this chunk
                    chunk_factors = factors[start_idx:end_idx]
                    
                    # Get colors from gradient for this chunk
                    chunk_colors = utils.interpolate_gradient_colors_batch(gradient, chunk_factors)
                    
                    # Apply blend mode based on settings
                    # Check if any color stops have alpha < 1.0
                    has_alpha = any(color.color[3] < 0.999 for color in gradient.colors)
                    
                    # Always get existing colors to ensure they're available
                    # Initialize chunk_existing_colors first
                    if existing_colors is None:
                        # If existing_colors is None, create an array of zeros with alpha=1
                        chunk_existing_colors = np.zeros((end_idx - start_idx, 4))
                        chunk_existing_colors[:, 3] = 1.0  # Set alpha to 1.0
                    else:
                        chunk_existing_colors = existing_colors[start_idx:end_idx]
                    
                    # Always apply the selected blend mode to ensure alpha values are respected
                    chunk_final_colors = utils.apply_blend_mode(
                        chunk_existing_colors, 
                        chunk_colors, 
                        blend_mode, 
                        opacity
                        )
                    
                    # Apply mask if in sculpt mode and mask exists
                    if use_existing_mask:
                        # Get the mask values for this chunk
                        chunk_mask = mask_data[start_idx:end_idx]
                        # Blend between current and opacity-blended colors based on mask (0=unmasked, 1=masked)
                        chunk_final_colors = chunk_existing_colors * chunk_mask[:, np.newaxis] + chunk_final_colors * (1 - chunk_mask[:, np.newaxis])
                    # Apply colors to selected vertices only in Edit mode
                    elif selected_verts is not None:
                        # Create a mask for selected vertices in this chunk
                        chunk_indices = np.arange(start_idx, end_idx)
                        mask = np.isin(chunk_indices, selected_verts)
                        
                        # Apply colors only to selected vertices in this chunk
                        # For unselected vertices, keep their current values
                        chunk_final_colors = np.where(mask[:, np.newaxis], chunk_final_colors, existing_colors[start_idx:end_idx])
                    
                    # Store the final colors for this chunk
                    final_colors[start_idx:end_idx] = chunk_final_colors
                    
                    utils.print_timing(chunk_start, f"Process color chunk {chunk_idx+1}/{num_chunks}")
                
                utils.print_timing(color_process_start, "Color processing time")
                
                # Update the color attribute
                update_start = time.time()
                utils.update_color_attribute(obj, target_attribute, final_colors, selected_verts)
                utils.print_timing(update_start, "Update color attribute time")
            
            utils.print_timing(obj_start, f"Process object {obj_idx+1}/{len(objects)}: {obj.name}")
        
        utils.print_timing(total_start, "Total curve gradient time")
        return {'FINISHED'}
    
    def calculate_curve_factors(self, vert_positions, p0, p1, p2, gradient, selected_verts=None):
        """Calculate gradient factors for each vertex based on the curve"""
        start_time = time.time()
        
        # Get context for screen space calculations
        context = bpy.context
        
        # Check if we should use screen space
        use_screen_space = False
        if gradient and hasattr(gradient, "use_screen_space"):
            use_screen_space = gradient.use_screen_space
        
        num_verts = len(vert_positions)
        factors = np.zeros(num_verts, dtype=np.float32)
        
        # Process vertices in chunks for better memory usage
        chunk_size = 50000  # Adjust based on available memory and performance
        num_chunks = (num_verts + chunk_size - 1) // chunk_size
        
        utils.print_timing(start_time, "Setup time")
        curve_gen_time = time.time()
        
        # If using screen space, project control points and vertices
        if use_screen_space:
            # Get the view matrix
            region = context.region
            rv3d = context.region_data
            
            # Project control points to screen space
            p0_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, p0)
            p1_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, p1)
            p2_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, p2)
            
            # Check if projection was successful
            if p0_2d and p1_2d and p2_2d:
                # Convert to numpy arrays for vectorized operations
                p0_np = np.array([p0_2d.x, p0_2d.y])
                p1_np = np.array([p1_2d.x, p1_2d.y])
                p2_np = np.array([p2_2d.x, p2_2d.y])
                
                # Generate curve points in 2D - this is done once for all vertices
                curve_resolution = 100  # Increased for better quality
                
                # Pre-calculate all curve points using vectorized operations
                t_values = np.linspace(0, 1, curve_resolution + 1)[1:]
                one_minus_t = 1 - t_values
                term1 = np.outer(one_minus_t**2, p0_np)
                term2 = np.outer(2 * one_minus_t * t_values, p1_np)
                term3 = np.outer(t_values**2, p2_np)
                curve_points_array = term1 + term2 + term3
                
                # Calculate segment lengths
                curve_lengths = [0.0]  # Start with 0 length
                total_length = 0.0
                
                # Add p0 as the first point
                all_points = np.vstack([p0_np[np.newaxis, :], curve_points_array])
                
                # Calculate segment lengths using vectorized operations
                segments = np.diff(all_points, axis=0)
                segment_lengths = np.linalg.norm(segments, axis=1)
                total_length = np.sum(segment_lengths)
                
                # Cumulative sum for lengths
                cumulative_lengths = np.cumsum(segment_lengths)
                curve_lengths = np.concatenate([[0], cumulative_lengths])
                
                # Normalize curve lengths to 0-1 range
                if total_length > 0:
                    curve_lengths = curve_lengths / total_length
                else:
                    curve_lengths = np.linspace(0, 1, len(curve_lengths))
                
                utils.print_timing(curve_gen_time, "Curve generation time (2D)")
                process_time = time.time()
                
                # Filter vertices by selection if needed
                if selected_verts is not None:
                    # Create a mask for all vertices
                    selection_mask = np.zeros(num_verts, dtype=bool)
                    selection_mask[selected_verts] = True
                    # Only process selected vertices
                    process_indices = np.where(selection_mask)[0]
                else:
                    # Process all vertices
                    process_indices = np.arange(num_verts)
                
                # Process vertices in chunks
                for chunk_idx in range(num_chunks):
                    chunk_start = time.time()
                    start_idx = chunk_idx * chunk_size
                    end_idx = min(start_idx + chunk_size, len(process_indices))
                    
                    if start_idx >= len(process_indices):
                        break
                    
                    # Get indices for this chunk
                    chunk_indices = process_indices[start_idx:end_idx]
                    
                    # Get vertices for this chunk
                    chunk_verts = vert_positions[chunk_indices]
                    
                    # Project this chunk of vertices to screen space
                    vert_positions_2d = utils.world_to_screen_batch(chunk_verts, region, rv3d)
                    
                    # Skip vertices that didn't project properly
                    valid_mask = ~np.isnan(vert_positions_2d).any(axis=1)
                    
                    if not np.any(valid_mask):
                        continue
                    
                    # Get valid vertices and their indices
                    valid_verts_2d = vert_positions_2d[valid_mask]
                    valid_indices = chunk_indices[valid_mask]
                    
                    if len(valid_verts_2d) == 0:
                        continue
                    
                    # Calculate distances using broadcasting - much faster than loops
                    # Shape: (num_valid_verts, num_curve_points)
                    diff = valid_verts_2d[:, np.newaxis, :] - curve_points_array[np.newaxis, :, :]
                    distances = np.linalg.norm(diff, axis=2)
                    
                    # Find closest point for each vertex
                    closest_indices = np.argmin(distances, axis=1)
                    
                    # Get the two closest points for smoother interpolation
                    sorted_indices = np.argsort(distances, axis=1)[:, :2]
                    closest_points = sorted_indices[:, 0]
                    second_closest = sorted_indices[:, 1]
                    
                    # Calculate weights based on inverse distance for smoother blending
                    closest_distances = np.take_along_axis(distances, sorted_indices, axis=1)
                    closest_dist = closest_distances[:, 0]
                    second_dist = closest_distances[:, 1]
                    
                    # Avoid division by zero
                    epsilon = 1e-6
                    total_dist = closest_dist + second_dist + epsilon
                    weight1 = second_dist / total_dist
                    weight2 = closest_dist / total_dist
                    
                    # Weighted average of the two closest points for smoother gradient
                    # +1 because curve_lengths includes p0 at the beginning
                    factor1 = curve_lengths[closest_points + 1]
                    factor2 = curve_lengths[second_closest + 1]
                    final_factors = factor1 * weight1 + factor2 * weight2
                    
                    # Reverse the factors if needed
                    if self.__class__._gradient_reversed:
                        final_factors = 1.0 - final_factors
                        
                    factors[valid_indices] = final_factors
                    
                    utils.print_timing(chunk_start, f"Processed chunk {chunk_idx+1}/{num_chunks} (2D)")
                
                utils.print_timing(process_time, "Total vertex processing time (2D)")
                utils.print_timing(start_time, "Total 2D calculation time")
                return factors
            else:
                # Fall back to 3D space if projection fails
                print("Screen space projection failed, falling back to 3D space")
        
        # 3D space calculation (either by choice or as fallback)
        # Convert control points to numpy arrays
        p0_np = np.array([p0.x, p0.y, p0.z])
        p1_np = np.array([p1.x, p1.y, p1.z])
        p2_np = np.array([p2.x, p2.y, p2.z])
        
        # Generate curve points in 3D - this is done once for all vertices
        curve_resolution = 100  # Increased for better quality
        
        # Pre-calculate all curve points using vectorized operations
        t_values = np.linspace(0, 1, curve_resolution + 1)[1:]
        one_minus_t = 1 - t_values
        term1 = np.outer(one_minus_t**2, p0_np)
        term2 = np.outer(2 * one_minus_t * t_values, p1_np)
        term3 = np.outer(t_values**2, p2_np)
        curve_points_array = term1 + term2 + term3
        
        # Add p0 as the first point
        all_points = np.vstack([p0_np[np.newaxis, :], curve_points_array])
        
        # Calculate segment lengths using vectorized operations
        segments = np.diff(all_points, axis=0)
        segment_lengths = np.linalg.norm(segments, axis=1)
        total_length = np.sum(segment_lengths)
        
        # Cumulative sum for lengths
        cumulative_lengths = np.cumsum(segment_lengths)
        curve_lengths = np.concatenate([[0], cumulative_lengths])
        
        # Normalize curve lengths to 0-1 range
        if total_length > 0:
            curve_lengths = curve_lengths / total_length
        else:
            curve_lengths = np.linspace(0, 1, len(curve_lengths))
        
        utils.print_timing(curve_gen_time, "Curve generation time (3D)")
        process_time = time.time()
        
        # Filter vertices by selection if needed
        if selected_verts is not None:
            # Create a mask for all vertices
            selection_mask = np.zeros(num_verts, dtype=bool)
            selection_mask[selected_verts] = True
            # Only process selected vertices
            process_indices = np.where(selection_mask)[0]
        else:
            # Process all vertices
            process_indices = np.arange(num_verts)
        
        # Process vertices in chunks
        for chunk_idx in range(num_chunks):
            chunk_start = time.time()
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(process_indices))
            
            if start_idx >= len(process_indices):
                break
            
            # Get indices for this chunk
            chunk_indices = process_indices[start_idx:end_idx]
            
            # Get vertices for this chunk
            chunk_verts = vert_positions[chunk_indices]
            
            # Calculate distances using broadcasting - much faster than loops
            # Shape: (num_chunk_verts, num_curve_points)
            diff = chunk_verts[:, np.newaxis, :] - curve_points_array[np.newaxis, :, :]
            distances = np.linalg.norm(diff, axis=2)
            
            # Find closest point for each vertex
            closest_indices = np.argmin(distances, axis=1)
            
            # Get the two closest points for smoother interpolation
            sorted_indices = np.argsort(distances, axis=1)[:, :2]
            closest_points = sorted_indices[:, 0]
            second_closest = sorted_indices[:, 1]
            
            # Calculate weights based on inverse distance for smoother blending
            closest_distances = np.take_along_axis(distances, sorted_indices, axis=1)
            closest_dist = closest_distances[:, 0]
            second_dist = closest_distances[:, 1]
            
            # Avoid division by zero
            epsilon = 1e-6
            total_dist = closest_dist + second_dist + epsilon
            weight1 = second_dist / total_dist
            weight2 = closest_dist / total_dist
            
            # Weighted average of the two closest points for smoother gradient
            # +1 because curve_lengths includes p0 at the beginning
            factor1 = curve_lengths[closest_points + 1]
            factor2 = curve_lengths[second_closest + 1]
            final_factors = factor1 * weight1 + factor2 * weight2
            
            # Reverse the factors if needed
            if self.__class__._gradient_reversed:
                final_factors = 1.0 - final_factors
                
            factors[chunk_indices] = final_factors
            
            utils.print_timing(chunk_start, f"Processed chunk {chunk_idx+1}/{num_chunks} (3D)")
        
        utils.print_timing(process_time, "Total vertex processing time (3D)")
        utils.print_timing(start_time, "Total 3D calculation time")
        return factors
