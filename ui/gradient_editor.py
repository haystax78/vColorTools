"""
Gradient Editor UI for vColorTools addon
Provides a visual gradient editor with draggable color stops
"""

import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from bpy.types import Panel, Operator
from mathutils import Vector
from bpy.props import IntProperty, FloatProperty, FloatVectorProperty, BoolProperty
from .. import utils

# Store handle to the draw handler
_handle = None
_is_running = False
_active_gradient = None
_active_color_index = -1
_editor_dimensions = (0, 0, 0, 0)  # x, y, width, height
_dragging = False
_editor_area = None  # Store the area where the editor is running
_original_gradient_state = None  # Store original gradient state for cancellation
_remove_buttons = []  # Store remove button areas for hit testing
_color_swatches = []  # Store color swatch areas for hit testing

def get_editor_dimensions(context):
    """Get the dimensions of the editor area"""
    # Get the region dimensions
    region = context.region
    ui_scale = utils.get_ui_scale(context)
    
    # Calculate a good size for the gradient editor
    width = min(region.width * 0.9, 1000)  # 90% of region width or 600px max
    height = 70 * ui_scale  # Make it taller for better visibility
    
    # Position it horizontally centered
    x = (region.width - width) / 2
    
    # Position it vertically centered
    y = (region.height - height) / 2
    
    # Editor dimensions calculated
    
    return (x, y, width, height)

def draw_gradient_editor_callback(self, context):
    """Draw the gradient editor with the current gradient"""
    global _active_gradient, _editor_dimensions, _active_color_index, _dragging, _is_running, _remove_buttons, _color_swatches
    
    # Safety check - if the editor was stopped but the callback is still running
    if not _is_running:
        return
        
    if not _active_gradient:
        return
    
    # Get UI scale for consistent sizing
    ui_scale = utils.get_ui_scale(context)
    
    # Get editor dimensions
    editor_x, editor_y, editor_width, editor_height = _editor_dimensions
    
    # Enable alpha blending
    gpu.state.blend_set('ALPHA')
    
    # Draw background for the gradient area with a darker, more visible background
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float("color", (0.15, 0.15, 0.15, 1.0))  # Darker background with higher opacity
    
    # Draw background rectangle with more padding
    batch = batch_for_shader(shader, 'TRI_FAN', {
        "pos": [(editor_x - 20, editor_y - editor_height - 50),
               (editor_x + editor_width + 20, editor_y - editor_height - 50),
               (editor_x + editor_width + 20, editor_y + editor_height + 20),
               (editor_x - 20, editor_y + editor_height + 20)]
    })
    batch.draw(shader)
    
    # Draw border with a more visible color
    border_color = (0.7, 0.7, 0.7, 1.0)  # Lighter border for better contrast
    border_width = 2  # Thicker border
    
    shader.bind()
    shader.uniform_float("color", border_color)
    batch = batch_for_shader(shader, 'LINE_LOOP', {
        "pos": [(editor_x - border_width, editor_y - border_width),
               (editor_x + editor_width + border_width, editor_y - border_width),
               (editor_x + editor_width + border_width, editor_y + editor_height + border_width),
               (editor_x - border_width, editor_y + editor_height + border_width)]
    })
    batch.draw(shader)
    
    # Draw checkerboard pattern for transparency visualization (like Blender's color ramp)
    checker_size = 10 * ui_scale  # Size of each checker square
    checker_color1 = (0.2, 0.2, 0.2, 1.0)  # Dark gray
    checker_color2 = (0.4, 0.4, 0.4, 1.0)  # Light gray
    
    # Calculate number of checker squares needed
    num_x = int(editor_width / checker_size) + 1
    num_y = int(editor_height / checker_size) + 1
    
    # Draw checker pattern
    for i in range(num_x):
        for j in range(num_y):
            # Alternate colors based on position
            color = checker_color1 if (i + j) % 2 == 0 else checker_color2
            shader.uniform_float("color", color)
            
            # Calculate position of this checker square
            x1 = editor_x + i * checker_size
            y1 = editor_y + j * checker_size
            x2 = min(x1 + checker_size, editor_x + editor_width)
            y2 = min(y1 + checker_size, editor_y + editor_height)
            
            # Draw the checker square
            batch = batch_for_shader(shader, 'TRI_FAN', {
                "pos": [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            })
            batch.draw(shader)
    
    # Draw gradient bar with more segments for smoother appearance
    num_segments = 256  # Increased for smoother gradient
    for i in range(num_segments):
        # Calculate segment boundaries
        x1 = editor_x + (i / num_segments) * editor_width
        x2 = editor_x + ((i + 1) / num_segments) * editor_width
        
        # Get color for this segment
        factor = i / (num_segments - 1) if num_segments > 1 else 0
        color = utils.interpolate_gradient_color(_active_gradient, factor)
        
        # Convert from linear to sRGB for display
        display_color = (utils.linear_to_srgb(color[0]),
                       utils.linear_to_srgb(color[1]),
                       utils.linear_to_srgb(color[2]),
                       color[3])
        
        # Draw segment
        shader.bind()
        shader.uniform_float("color", display_color)
        
        batch = batch_for_shader(shader, 'TRI_FAN', {
            "pos": [(x1, editor_y),
                   (x2, editor_y),
                   (x2, editor_y + editor_height),
                   (x1, editor_y + editor_height)]
        })
        batch.draw(shader)
    
    # Draw a white border around the gradient for better visibility
    shader.bind()
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.8))  # White with slight transparency
    
    batch = batch_for_shader(shader, 'LINE_LOOP', {
        "pos": [(editor_x, editor_y),
               (editor_x + editor_width, editor_y),
               (editor_x + editor_width, editor_y + editor_height),
               (editor_x, editor_y + editor_height)]
    })
    batch.draw(shader)
    
    # Clear button and swatch lists before redrawing
    _remove_buttons = []
    _color_swatches = []
    
    # Draw color stop markers with larger, more visible triangles
    for i, stop in enumerate(_active_gradient.colors):
        # Calculate marker position
        x = editor_x + stop.position * editor_width
        
        # Draw marker triangle - make it larger and more visible
        is_active = (i == _active_color_index)
        
        # Use more distinctive colors for better visibility
        if is_active:
            marker_color = (1.0, 1.0, 0.0, 1.0)  # Yellow for active marker
            outline_color = (0.0, 0.0, 0.0, 1.0)  # Black outline
        else:
            marker_color = (0.9, 0.9, 0.9, 1.0)  # Light gray for inactive
            outline_color = (0.3, 0.3, 0.3, 1.0)  # Darker outline
        
        # Make markers even larger and position them clearly below the gradient
        marker_size = 15 * ui_scale  # Increased size for better visibility
        marker_y_offset = 5 * ui_scale
        
        # Draw triangle pointing up
        shader.bind()
        shader.uniform_float("color", marker_color)
        
        batch = batch_for_shader(shader, 'TRI_FAN', {
            "pos": [(x, editor_y - marker_y_offset),
                   (x - marker_size, editor_y - marker_size - marker_y_offset),
                   (x + marker_size, editor_y - marker_size - marker_y_offset)]
        })
        batch.draw(shader)
        
        # Draw outline around the marker for better visibility
        shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
        batch = batch_for_shader(shader, 'LINE_LOOP', {
            "pos": [(x, editor_y - marker_y_offset),
                   (x - marker_size, editor_y - marker_size - marker_y_offset),
                   (x + marker_size, editor_y - marker_size - marker_y_offset)]
        })
        batch.draw(shader)
        
        # Get display color for the swatch
        display_color = (utils.linear_to_srgb(stop.color[0]),
                       utils.linear_to_srgb(stop.color[1]),
                       utils.linear_to_srgb(stop.color[2]),
                       stop.color[3])
        
        # Draw color swatch below the marker for editing the color
        swatch_width = 12 * ui_scale
        swatch_height = 28 * ui_scale
        swatch_y = editor_y - marker_size - swatch_height / 2 * ui_scale
        
        # Draw swatch background (tall rectangle)
        shader.uniform_float("color", display_color)
        batch = batch_for_shader(shader, 'TRI_FAN', {
            "pos": [
                (x - swatch_width, swatch_y),
                (x + swatch_width, swatch_y),
                (x + swatch_width, swatch_y - swatch_height),
                (x - swatch_width, swatch_y - swatch_height)
            ]
        })
        batch.draw(shader)
        
        # Draw swatch outline
        shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
        batch = batch_for_shader(shader, 'LINE_LOOP', {
            "pos": [
                (x - swatch_width, swatch_y),
                (x + swatch_width, swatch_y),
                (x + swatch_width, swatch_y - swatch_height),
                (x - swatch_width, swatch_y - swatch_height)
            ]
        })
        batch.draw(shader)
        
        # Store swatch area for hit testing
        _color_swatches.append({
            'index': i,
            'x1': x - swatch_width,
            'y1': swatch_y - swatch_height,
            'x2': x + swatch_width,
            'y2': swatch_y
        })
        
        # Draw 'X' button below the color swatch for removing this color stop
        # Only draw if there are more than 2 color stops (need at least 2 for a gradient)
        if len(_active_gradient.colors) > 2:
            # Draw button background (small square)
            button_size = 10 * ui_scale
            button_y = swatch_y - button_size - 15 * ui_scale
            
            # Draw button background
            shader.uniform_float("color", (0.2, 0.2, 0.2, 0.8))  # Dark gray background
            batch = batch_for_shader(shader, 'TRI_FAN', {
                "pos": [(x - button_size, button_y),
                       (x + button_size, button_y),
                       (x + button_size, button_y - 2 * button_size),
                       (x - button_size, button_y - 2 * button_size)]
            })
            batch.draw(shader)
            
            # Draw button outline
            shader.uniform_float("color", (0.5, 0.5, 0.5, 1.0))  # Light gray outline
            batch = batch_for_shader(shader, 'LINE_LOOP', {
                "pos": [(x - button_size, button_y),
                       (x + button_size, button_y),
                       (x + button_size, button_y - 2 * button_size),
                       (x - button_size, button_y - 2 * button_size)]
            })
            batch.draw(shader)
            
            # Draw 'X' inside the button
            line_width = 2.0  # Thicker lines for better visibility
            shader.uniform_float("color", (1.0, 0.3, 0.3, 1.0))  # Red X
            
            # Draw the X (diagonal lines)
            # First diagonal: top-left to bottom-right
            batch = batch_for_shader(shader, 'LINES', {
                "pos": [(x - button_size * 0.6, button_y - button_size * 0.4),
                       (x + button_size * 0.6, button_y - button_size * 1.6)]
            })
            batch.draw(shader)
            
            # Second diagonal: top-right to bottom-left
            batch = batch_for_shader(shader, 'LINES', {
                "pos": [(x + button_size * 0.6, button_y - button_size * 0.4),
                       (x - button_size * 0.6, button_y - button_size * 1.6)]
            })
            batch.draw(shader)
            
            # Store button area in our global list for hit testing
            # This avoids issues with storing data on the color stop objects
            _remove_buttons.append({
                'index': i,
                'x1': x - button_size,  # Left edge
                'y1': button_y - 2 * button_size,  # Bottom edge
                'x2': x + button_size,  # Right edge
                'y2': button_y  # Top edge
            })
    
    # Draw a message to inform users how to interact with the editor
    font_id = 0  # Default font
    font_size = int(18 * ui_scale)
    blf.color(font_id, 1, 1, 1, 0.3)
    blf.size(font_id, font_size)
    
    # Position text below the gradient
    text_y = editor_y - editor_height - 30 * ui_scale
    blf.position(font_id, editor_x, text_y, 0)
    blf.draw(font_id, "Click in gradient to add color stops. ENTER to accept, ESC/RMB to cancel")
    
    # Reset blend mode
    gpu.state.blend_set('NONE')

class VGRADIENT_OT_drag_color_stop(Operator):
    """Drag a color stop to change its position"""
    bl_idname = "vgradient.drag_color_stop"
    bl_label = "Drag Color Stop"
    bl_options = {'REGISTER', 'UNDO'}
    
    color_index: IntProperty(default=0)
    initial_position: FloatProperty(default=0.5)
    initial_mouse_x: IntProperty(default=0)
    
    def modal(self, context, event):
        global _dragging, _editor_dimensions, _active_gradient, _active_color_index, _editor_area
        
        # Only process events in the editor area
        if context.area != _editor_area:
            return {'PASS_THROUGH'}
            
        # Check if mouse is in the N-panel region (UI region)
        for region in context.area.regions:
            if region.type == 'UI':
                # If mouse is in the UI region, pass through all events
                if (region.x <= event.mouse_x <= region.x + region.width and
                    region.y <= event.mouse_y <= region.y + region.height):
                    return {'PASS_THROUGH'}
        
        # Get editor dimensions
        editor_x, editor_y, editor_width, editor_height = _editor_dimensions
        
        # Calculate new position based on mouse position
        if event.type == 'MOUSEMOVE':
            # Calculate position based on mouse position relative to editor
            new_position = (event.mouse_region_x - editor_x) / editor_width
            new_position = max(0.0, min(1.0, new_position))
            
            # Update color stop position
            if self.color_index < len(_active_gradient.colors):
                _active_gradient.colors[self.color_index].position = new_position
                # Position updated during drag
            
            # Force redraw
            context.area.tag_redraw()
        
        # Handle events
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            _dragging = False
            # Mouse released, sort color stops
            # Sort color stops by position
            self.sort_color_stops(_active_gradient)
            # Force gradient update and UI redraw
            if hasattr(_active_gradient, 'update_tag'):
                _active_gradient.update_tag()
            if context.area:
                context.area.tag_redraw()
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            _dragging = False
            # Cancelled drag, restore position
            # Restore original position
            if self.color_index < len(_active_gradient.colors):
                _active_gradient.colors[self.color_index].position = self.initial_position
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        global _dragging, _active_gradient, _active_color_index
        
        if self.color_index >= len(_active_gradient.colors):
            self.report({'WARNING'}, "Invalid color index")
            return {'CANCELLED'}
        
        # Store initial position and mouse position
        _dragging = True
        self.initial_position = _active_gradient.colors[self.color_index].position
        self.initial_mouse_x = event.mouse_region_x
        _active_color_index = self.color_index
        
        # Start dragging color stop
        
        # Start modal operation
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    @classmethod
    def sort_color_stops(cls, gradient):
        """Sort color stops by position"""
        global _active_color_index
        
        # Create a list of (index, position, color) tuples
        # Make sure to store the full color data (all 4 components)
        color_stops = []
        for i, stop in enumerate(gradient.colors):
            # Store position and a copy of the full color (all 4 components)
            color_data = (stop.color[0], stop.color[1], stop.color[2], stop.color[3])
            color_stops.append((i, stop.position, color_data))
            # Store original color stop data
        
        # Get the active color stop before sorting
        active_color = None
        active_position = 0
        if _active_color_index >= 0 and _active_color_index < len(gradient.colors):
            # Make a copy of the color to ensure we don't lose data
            color = gradient.colors[_active_color_index].color
            active_color = (color[0], color[1], color[2], color[3])
            active_position = gradient.colors[_active_color_index].position
            # Store active color stop data
        
        # Sort by position
        color_stops.sort(key=lambda x: x[1])
        
        # Clear and rebuild the color collection in sorted order
        gradient.colors.clear()
        for i, (_, position, color) in enumerate(color_stops):
            new_stop = gradient.colors.add()
            # Explicitly set each color component to avoid data loss
            new_stop.color = (color[0], color[1], color[2], color[3])
            new_stop.position = position
            # Rebuild color stop
        
        # Update active_color_index to maintain selection after sorting
        if active_color is not None:
            for i, stop in enumerate(gradient.colors):
                # Use a small tolerance for position comparison
                if abs(stop.position - active_position) < 0.001:
                    # Also check if colors match approximately
                    color_matches = all(abs(stop.color[j] - active_color[j]) < 0.001 for j in range(4))
                    if color_matches:
                        _active_color_index = i
                        gradient.active_color_index = i
                        # Update active color index
                        break

class VGRADIENT_OT_start_gradient_editor(Operator):
    """Start the gradient editor"""
    bl_idname = "vgradient.start_gradient_editor"
    bl_label = "Edit Gradient"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global _handle, _is_running, _active_gradient, _editor_dimensions, _editor_area, _original_gradient_state
        
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
        
        # Get the active gradient
        if len(context.scene.vgradient_collection) == 0:
            self.report({'WARNING'}, "No gradients available")
            return {'CANCELLED'}
        
        _active_gradient = context.scene.vgradient_collection[context.scene.vgradient_active_index]
        
        # Ensure all color stops have position values
        utils.ensure_gradient_positions(_active_gradient)
        
        # Store original gradient state for potential cancellation
        # We need to store the entire structure to handle additions and removals
        _original_gradient_state = {
            'num_colors': len(_active_gradient.colors),
            'colors': []
        }
        
        # Store each color stop's properties
        for color_stop in _active_gradient.colors:
            _original_gradient_state['colors'].append({
                'color': color_stop.color[:],  # Make a copy of the color
                'position': color_stop.position
            })
        
        _editor_area = context.area
        
        # Calculate editor dimensions
        _editor_dimensions = get_editor_dimensions(context)
        
        # Print debug info
        # Gradient editor started
        # Store initial gradient state for potential cancellation
        
        # Remove existing handler if it exists
        if _handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
            except:
                pass
            _handle = None
        
        # Add the draw handler
        _handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_gradient_editor_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        _is_running = True
        
        # Set status text with instructions
        context.workspace.status_text_set("Gradient Editor: Click and drag color stops | ENTER to accept | ESC/RMB to cancel")
        
        # Force a redraw to show the gradient immediately
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        # Start the click handler immediately
        bpy.ops.vgradient.click_gradient_editor('INVOKE_DEFAULT')
        
        return {'FINISHED'}

class VGRADIENT_OT_stop_gradient_editor(Operator):
    """Stop the gradient editor and accept changes"""
    bl_idname = "vgradient.stop_gradient_editor"
    bl_label = "Stop Gradient Editor"
    bl_options = {'REGISTER'}
    
    cancel: BoolProperty(default=False)
    
    def execute(self, context):
        global _handle, _is_running, _active_gradient, _editor_area, _original_gradient_state
        
        # Stopping gradient editor
        
        # Remove draw handler
        if _handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
                # Draw handler removed
            except Exception as e:
                # Error removing draw handler
                pass
            _handle = None
        
        # If cancelling, restore the original gradient state
        if self.cancel and _original_gradient_state:
            # Cancelling gradient editor changes
            
            # Get the original number of color stops
            original_num_colors = _original_gradient_state['num_colors']
            current_num_colors = len(_active_gradient.colors)
            
            # Handle case where color stops were added
            if current_num_colors > original_num_colors:
                # Remove extra color stops (from newest to oldest)
                for i in range(current_num_colors - 1, original_num_colors - 1, -1):
                    _active_gradient.colors.remove(i)
                # Remove added color stops
            
            # Handle case where color stops were removed
            elif current_num_colors < original_num_colors:
                # Add back the missing color stops
                for i in range(current_num_colors, original_num_colors):
                    new_stop = _active_gradient.colors.add()
                    # We'll set their properties in the next loop
                # Add back removed color stops
            
            # Now restore all the original color stop properties
            for i, original_color_data in enumerate(_original_gradient_state['colors']):
                if i < len(_active_gradient.colors):
                    _active_gradient.colors[i].color = original_color_data['color']
                    _active_gradient.colors[i].position = original_color_data['position']
        else:
            # Accepting gradient editor changes
            pass
        
        # Reset state variables
        _is_running = False
        _active_gradient = None
        _editor_area = None
        _original_gradient_state = None
        
        # Clear status text
        context.workspace.status_text_set(None)
        
        # Force redraw to remove gradient visualization
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

class VGRADIENT_OT_remove_color_stop(Operator):
    """Remove a specific color stop from the gradient"""
    bl_idname = "vgradient.remove_color_stop"
    bl_label = "Remove Color Stop"
    bl_options = {'REGISTER', 'UNDO'}
    
    color_index: IntProperty(default=0)
    
    def execute(self, context):
        global _active_gradient
        
        # Safety check
        if not _active_gradient or len(_active_gradient.colors) <= 2:
            self.report({'WARNING'}, "Cannot remove color stop: minimum 2 stops required")
            return {'CANCELLED'}
        
        # Remove the color stop
        if self.color_index < len(_active_gradient.colors):
            _active_gradient.colors.remove(self.color_index)
            # Color stop removed
            
            # Force redraw
            context.area.tag_redraw()
            
            return {'FINISHED'}
        
        return {'CANCELLED'}

class VGRADIENT_OT_click_gradient_editor(Operator):
    """Handle clicks in the gradient editor"""
    bl_idname = "vgradient.click_gradient_editor"
    bl_label = "Click in Gradient Editor"
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return _is_running and _active_gradient is not None
    
    def modal(self, context, event):
        global _active_gradient, _editor_dimensions, _active_color_index, _editor_area
        
        # Only process events in the editor area
        if context.area != _editor_area:
            return {'PASS_THROUGH'}
        
        # Check if mouse is in the N-panel region (UI region)
        for region in context.area.regions:
            if region.type == 'UI':
                # If mouse is in the UI region, pass through all events
                if (region.x <= event.mouse_x <= region.x + region.width and
                    region.y <= event.mouse_y <= region.y + region.height):
                    return {'PASS_THROUGH'}
        
        # Handle mouse movement for previewing - but only in the 3D view
        if event.type == 'MOUSEMOVE':
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            

            
        # Handle click to add/edit color stop
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Get mouse position
            mouse_x, mouse_y = event.mouse_region_x, event.mouse_region_y
            
            # Get editor dimensions
            editor_x, editor_y, editor_width, editor_height = _editor_dimensions
            
            # Debug info
            # Process mouse click in editor
            
            # Expanded click area - make it easier to click
            # Include the area of the gradient plus some margin for the markers
            click_area_top = editor_y + editor_height + 10
            click_area_bottom = editor_y - editor_height - 30
            
            # Check if click is within expanded editor area
            if (mouse_x >= editor_x - 10 and mouse_x <= editor_x + editor_width + 10 and
                mouse_y >= click_area_bottom and mouse_y <= click_area_top):
                
                # Handle click within editor area
                
                # First check if click is on any color swatch
                for swatch in _color_swatches:
                    if (mouse_x >= swatch['x1'] and 
                        mouse_x <= swatch['x2'] and
                        mouse_y >= swatch['y1'] and 
                        mouse_y <= swatch['y2']):
                        
                        # Set active color index
                        _active_color_index = swatch['index']
                        _active_gradient.active_color_index = swatch['index']
                        
                        # Open color picker for this stop
                        bpy.ops.vgradient.edit_color_stop('INVOKE_DEFAULT', color_index=swatch['index'])
                        return {'RUNNING_MODAL'}
                
                # Then check if click is on any remove button (X button)
                for button in _remove_buttons:
                    # Check if click is within button area
                    
                    # Check if click is within the button area
                    if (mouse_x >= button['x1'] and 
                        mouse_x <= button['x2'] and
                        mouse_y >= button['y1'] and 
                        mouse_y <= button['y2']):
                        
                        # Remove the color stop when button is clicked
                        # Remove the color stop
                        bpy.ops.vgradient.remove_color_stop(color_index=button['index'])
                        return {'RUNNING_MODAL'}
                
                # If not clicking a remove button, find closest color stop
                closest_index = -1
                closest_distance = float('inf')
                
                # Check for clicks on markers (triangles below the gradient)
                marker_y_offset = 5 * utils.get_ui_scale(context)
                marker_size = 12 * utils.get_ui_scale(context)
                marker_y = editor_y - marker_y_offset
                marker_bottom = editor_y - marker_size - marker_y_offset
                
                for i, stop in enumerate(_active_gradient.colors):
                    stop_x = editor_x + stop.position * editor_width
                    
                    # Check if click is on the marker triangle
                    # Use a simplified triangle hit test
                    if (mouse_y <= marker_y and mouse_y >= marker_bottom and
                        abs(mouse_x - stop_x) < marker_size * (marker_y - mouse_y) / (marker_y - marker_bottom)):
                        closest_index = i
                        closest_distance = 0  # Direct hit
                        break
                    
                    # Otherwise check distance to marker center
                    distance = abs(mouse_x - stop_x)
                    if distance < closest_distance:
                        closest_distance = distance
                        closest_index = i
                
                # If click is close to a color stop or directly on a marker, start dragging it
                if closest_distance < 20:  # Increased threshold for easier selection
                    # Start dragging the closest color stop
                    _active_color_index = closest_index
                    _active_gradient.active_color_index = closest_index
                    
                    # Start drag operation
                    bpy.ops.vgradient.drag_color_stop('INVOKE_DEFAULT', color_index=closest_index)
                    return {'RUNNING_MODAL'}
                else:
                    # Add a new color stop at click position
                    # Only allow adding within the actual gradient bar
                    if mouse_y <= editor_y + editor_height and mouse_y >= editor_y:
                        position = (mouse_x - editor_x) / editor_width
                        position = max(0.0, min(1.0, position))
                        
                        # Add new stop at clicked position
                        
                        # Get color at this position
                        color = utils.interpolate_gradient_color(_active_gradient, position)
                        
                        # Add new color stop
                        new_stop = _active_gradient.colors.add()
                        # Make sure to copy all 4 color components (RGBA)
                        new_stop.color = (color[0], color[1], color[2], color[3])
                        new_stop.position = position
                        
                        # New color stop added
                        
                        # Set as active
                        _active_color_index = len(_active_gradient.colors) - 1
                        _active_gradient.active_color_index = _active_color_index
                        
                        # Sort color stops - call the class method directly
                        VGRADIENT_OT_drag_color_stop.sort_color_stops(_active_gradient)
                        
                        context.area.tag_redraw()
                        return {'RUNNING_MODAL'}
        
        # Allow canceling the modal operator with RMB or ESC
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Stop the gradient editor and cancel changes
            bpy.ops.vgradient.stop_gradient_editor(cancel=True)
            return {'CANCELLED'}
            
        # Accept changes with ENTER
        elif event.type == 'RET' and event.value == 'PRESS':
            # Stop the gradient editor and accept changes
            bpy.ops.vgradient.stop_gradient_editor(cancel=False)
            return {'FINISHED'}
        
        # Capture all events in the 3D view to prevent accidental interaction with the scene
        # This keeps the viewport locked while the editor is active
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        # Start modal operation
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        # This is called when the operator is executed from a button
        # Start the modal operation
        self.invoke(context, None)
        return {'RUNNING_MODAL'}

# The gradient editor panel has been integrated into the main Gradient Tools panel
# This class is no longer needed, but we keep the file for the operators and drawing functions

class VGRADIENT_OT_edit_color_stop(bpy.types.Operator):
    """Edit a color stop's color using a color picker"""
    bl_idname = "vgradient.edit_color_stop"
    bl_label = "Edit Color Stop"
    bl_options = {'REGISTER', 'UNDO'}
    
    color_index: bpy.props.IntProperty(default=0)
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=4,
        min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
        description="Color for this stop"
    )
    
    def invoke(self, context, event):
        global _active_gradient
        
        # Get the current color from the gradient
        if _active_gradient and 0 <= self.color_index < len(_active_gradient.colors):
            stop = _active_gradient.colors[self.color_index]
            # Use the color values directly without conversion
            self.color = stop.color
        
        # Open the color picker popup
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        # Add color property with alpha
        layout.prop(self, "color", text="Color")
    
    def execute(self, context):
        global _active_gradient
        
        # Update the color in the gradient
        if _active_gradient and 0 <= self.color_index < len(_active_gradient.colors):
            stop = _active_gradient.colors[self.color_index]
            
            # Use the color values directly without conversion
            stop.color = self.color
            
            # Update the UI
            context.area.tag_redraw()
        
        return {'FINISHED'}

# Registration
classes = (
    VGRADIENT_OT_drag_color_stop,
    VGRADIENT_OT_start_gradient_editor,
    VGRADIENT_OT_stop_gradient_editor,
    VGRADIENT_OT_remove_color_stop,
    VGRADIENT_OT_click_gradient_editor,
    VGRADIENT_OT_edit_color_stop,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    global _handle, _is_running
    
    # Remove draw handler if it exists
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
        _is_running = False
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
