"""
Management operators for vColGradient addon
Contains operators for adding, removing, and managing gradients and colors
"""

import bpy
from bpy.props import EnumProperty
from .. import utils

class VGRADIENT_OT_add_color(bpy.types.Operator):
    """Add a new color to the gradient"""
    bl_idname = "vgradient.add_color"
    bl_label = "Add Color"
    bl_options = {'REGISTER', 'UNDO'}

    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)

    def execute(self, context):
        gradient = utils.get_active_gradient(context)
        if gradient:
            existing_colors = sorted(gradient.colors, key=lambda c: c.position)
            num_colors = len(existing_colors)
            active_idx = gradient.active_color_index if hasattr(gradient, 'active_color_index') else 0

            # Add a new color
            color = gradient.colors.add()

            if num_colors > 0:
                # Default: place between active and next neighbor
                insert_idx = min(active_idx, num_colors - 1)
                if insert_idx < num_colors - 1:
                    pos_a = existing_colors[insert_idx].position
                    pos_b = existing_colors[insert_idx + 1].position
                    move_to = insert_idx + 1
                else:
                    # If at the end, use previous neighbor
                    pos_a = existing_colors[insert_idx - 1].position if num_colors > 1 else 0.25
                    pos_b = existing_colors[insert_idx].position
                    move_to = insert_idx
                new_position = (pos_a + pos_b) / 2
                color.position = new_position
                # Interpolate RGBA from the two neighbors
                col_a = existing_colors[insert_idx - 1].color if insert_idx == num_colors - 1 else existing_colors[insert_idx].color
                col_b = existing_colors[insert_idx].color if insert_idx == num_colors - 1 else existing_colors[insert_idx + 1].color
                t = (new_position - pos_a) / (pos_b - pos_a) if pos_b != pos_a else 0.5
                interp_color = [
                    (1 - t) * col_a[i] + t * col_b[i]
                    for i in range(4)
                ]
                color.color = interp_color
                # Move the new color stop to the correct position in the list
                gradient.colors.move(len(gradient.colors) - 1, move_to)
                gradient.active_color_index = move_to
            else:
                color.position = 0.5
                color.color = (1.0, 1.0, 1.0, 1.0)
                gradient.active_color_index = 0
        return {'FINISHED'}

class VGRADIENT_OT_remove_color(bpy.types.Operator):
    """Remove the active color from the gradient"""
    bl_idname = "vgradient.remove_color"
    bl_label = "Remove Color"
    bl_options = {'REGISTER', 'UNDO'}

    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)

    @classmethod
    def poll(cls, context):
        gradient = utils.get_active_gradient(context)
        return gradient and len(gradient.colors) > 2

    def execute(self, context):
        gradient = utils.get_active_gradient(context)
        if gradient and len(gradient.colors) > 2:
            gradient.colors.remove(gradient.active_color_index)
            gradient.active_color_index = min(gradient.active_color_index, len(gradient.colors) - 1)
        return {'FINISHED'}

class VGRADIENT_OT_move_color(bpy.types.Operator):
    """Move a color stop in the gradient"""
    bl_idname = "vgradient.move_color"
    bl_label = "Move Color"
    bl_options = {'REGISTER', 'UNDO'}
    
    type: EnumProperty(
        name="Type",
        items=[
            ('UP', "Up", "Move color up"),
            ('DOWN', "Down", "Move color down"),
        ],
        default='UP'
    )

    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)

    @classmethod
    def poll(cls, context):
        gradient = utils.get_active_gradient(context)
        return gradient and len(gradient.colors) > 1

    def execute(self, context):
        gradient = utils.get_active_gradient(context)
        if not gradient:
            return {'CANCELLED'}

        colors = gradient.colors
        index = gradient.active_color_index

        if self.type == 'UP' and index > 0:
            # Swap position values
            pos_a = colors[index].position
            pos_b = colors[index - 1].position
            colors[index].position, colors[index - 1].position = pos_b, pos_a
            colors.move(index, index - 1)
            gradient.active_color_index -= 1
        elif self.type == 'DOWN' and index < len(colors) - 1:
            # Swap position values
            pos_a = colors[index].position
            pos_b = colors[index + 1].position
            colors[index].position, colors[index + 1].position = pos_b, pos_a
            colors.move(index, index + 1)
            gradient.active_color_index += 1
        elif self.type == 'TOP' and index > 0:
            # Move to top: set position to just less than the first stop
            top_pos = colors[0].position if len(colors) > 1 else 0.0
            colors[index].position = top_pos - 0.0001
            colors.move(index, 0)
            gradient.active_color_index = 0
        elif self.type == 'BOTTOM' and index < len(colors) - 1:
            # Move to bottom: set position to just more than the last stop
            bottom_pos = colors[-1].position if len(colors) > 1 else 1.0
            colors[index].position = bottom_pos + 0.0001
            colors.move(index, len(colors) - 1)
            gradient.active_color_index = len(colors) - 1

        # Force gradient update and UI redraw
        if hasattr(gradient, 'update_tag'):
            gradient.update_tag()
        for area in bpy.context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}

class VGRADIENT_OT_add_gradient(bpy.types.Operator):
    """Add a new gradient"""
    bl_idname = "vgradient.add_gradient"
    bl_label = "Add Gradient"
    bl_description = "Add a new gradient"
    bl_options = {'REGISTER', 'UNDO'}

    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)

    def execute(self, context):
        gradients = context.scene.vgradient_collection
        new_gradient = gradients.add()
        new_gradient.name = f"Gradient {len(gradients)}"
        
        # Initialize the ColorRamp with default black to white gradient
        # The ColorRamp node group is created automatically with defaults
        # when get_or_create_gradient_node_group is called
        from .. import utils
        utils.get_or_create_gradient_node_group(new_gradient)
        
        # Set the active gradient index to the new gradient
        context.scene.vgradient_active_index = len(gradients) - 1
        
        return {'FINISHED'}

class VGRADIENT_OT_remove_gradient(bpy.types.Operator):
    """Remove the active gradient"""
    bl_idname = "vgradient.remove_gradient"
    bl_label = "Remove Gradient"
    bl_description = "Remove the active gradient"
    bl_options = {'REGISTER', 'UNDO'}
    
    def __new__(cls, *args, **kwargs):
        # For Blender 4.4 compatibility
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        # For Blender 4.4 compatibility
        super().__init__(*args, **kwargs)
    
    @classmethod
    def poll(cls, context):
        return context.scene.vgradient_collection
        
    def execute(self, context):
        scene = context.scene
        index = scene.vgradient_active_index
        
        if index >= 0 and index < len(scene.vgradient_collection):
            # Get the gradient name before removing to clean up its node group
            gradient_name = scene.vgradient_collection[index].name
            from .. import utils
            node_group_name = utils.get_gradient_node_group_name(gradient_name)
            
            # Remove the gradient
            scene.vgradient_collection.remove(index)
            scene.vgradient_active_index = min(index, len(scene.vgradient_collection) - 1)
            
            # Clean up the associated node group
            if node_group_name in bpy.data.node_groups:
                bpy.data.node_groups.remove(bpy.data.node_groups[node_group_name])
            
        return {'FINISHED'}


class VGRADIENT_OT_migrate_gradients(bpy.types.Operator):
    """Migrate legacy gradients to the new ColorRamp format"""
    bl_idname = "vgradient.migrate_gradients"
    bl_label = "Migrate Gradients"
    bl_description = "Convert legacy gradients to the new ColorRamp format"
    bl_options = {'REGISTER', 'UNDO'}
    
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, *args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def execute(self, context):
        utils.migrate_legacy_gradients()
        self.report({'INFO'}, "Legacy gradients migrated successfully")
        return {'FINISHED'}
