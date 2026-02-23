"""
RGB Curves adjustment operator for vColorTools addon
Allows adjustment of vertex color values using curve-based controls
"""

import bpy
import numpy as np
import time
from bpy.props import PointerProperty
from .. import utils


# Module-level node tree name for curves storage
CURVES_NODE_TREE_NAME = ".vColorTools_CurveTree"
CURVES_NODE_NAME = "vColorTools_Curves"


def get_or_create_curves_node():
    """Get or create the RGB Curves node for storing curve data
    
    Returns:
        The ShaderNodeRGBCurve node, or None if creation failed
    """
    # Get or create the node tree
    if CURVES_NODE_TREE_NAME in bpy.data.node_groups:
        node_tree = bpy.data.node_groups[CURVES_NODE_TREE_NAME]
    else:
        node_tree = bpy.data.node_groups.new(name=CURVES_NODE_TREE_NAME, type='ShaderNodeTree')
    
    # Find or create the RGB Curves node
    curves_node = None
    for node in node_tree.nodes:
        if node.name == CURVES_NODE_NAME:
            curves_node = node
            break
    
    if not curves_node:
        curves_node = node_tree.nodes.new(type='ShaderNodeRGBCurve')
        curves_node.name = CURVES_NODE_NAME
    
    return curves_node


def get_curves_mapping():
    """Get the CurveMapping from the stored node
    
    Returns:
        CurveMapping object, or None if not available
    """
    curves_node = get_or_create_curves_node()
    if curves_node:
        return curves_node.mapping
    return None


def get_curve_value_vectorized(curve_mapping, curve, values):
    """Evaluate curve for an array of values using LUT for performance
    
    Args:
        curve_mapping: Blender CurveMapping object (has the evaluate method)
        curve: Blender CurveMap object (the specific curve to evaluate)
        values: NumPy array of input values (0-1 range)
        
    Returns:
        NumPy array of output values after curve transformation
    """
    # Build a 256-entry lookup table for fast evaluation
    lut_size = 256
    lut_inputs = np.linspace(0.0, 1.0, lut_size)
    # Use CurveMapping.evaluate(curve, position) - the correct API
    lut_outputs = np.array([curve_mapping.evaluate(curve, v) for v in lut_inputs], dtype=np.float32)
    
    # Clamp input values to valid range
    values_clamped = np.clip(values, 0.0, 1.0)
    
    # Use linear interpolation with the LUT
    result = np.interp(values_clamped, lut_inputs, lut_outputs)
    
    return result


def apply_contrast(colors, contrast):
    """Apply contrast adjustment to colors
    
    Args:
        colors: NumPy array of colors (Nx4 RGBA)
        contrast: Contrast value (-1 to 1, 0 = no change)
        
    Returns:
        NumPy array of adjusted colors
    """
    if abs(contrast) < 0.001:
        return colors
    
    result = colors.copy()
    
    # Convert contrast range (-1, 1) to a subtle multiplier
    # At contrast=1, we get factor ~1.1 (gentle increase)
    # At contrast=-1, we get factor ~0.9 (gentle decrease)
    # Scale down by 10x for more usable range
    scaled_contrast = contrast * 0.1
    if scaled_contrast >= 0:
        factor = 1.0 + scaled_contrast
    else:
        factor = 1.0 / (1.0 - scaled_contrast)
    
    # Apply contrast around midpoint (0.5)
    result[:, :3] = (result[:, :3] - 0.5) * factor + 0.5
    
    # Clamp to valid range
    result[:, :3] = np.clip(result[:, :3], 0.0, 1.0)
    
    return result


def apply_saturation(colors, saturation):
    """Apply saturation adjustment to colors
    
    Args:
        colors: NumPy array of colors (Nx4 RGBA in linear space)
        saturation: Saturation value (-1 to 1, 0 = no change)
        
    Returns:
        NumPy array of adjusted colors
    """
    if abs(saturation) < 0.001:
        return colors
    
    result = colors.copy()
    
    # Calculate luminance (using Rec. 709 coefficients for linear RGB)
    luminance = 0.2126 * colors[:, 0] + 0.7152 * colors[:, 1] + 0.0722 * colors[:, 2]
    
    # Convert saturation range (-1, 1) to a factor
    # At saturation=1, we get factor=2 (more saturated)
    # At saturation=-1, we get factor=0 (grayscale)
    factor = 1.0 + saturation
    
    # Interpolate between grayscale and original color
    for i in range(3):
        result[:, i] = luminance + (colors[:, i] - luminance) * factor
    
    # Clamp to valid range
    result[:, :3] = np.clip(result[:, :3], 0.0, 1.0)
    
    return result


def apply_curves_to_colors(colors, curve_mapping):
    """Apply RGB curves to a color array
    
    Args:
        colors: NumPy array of colors (Nx4 RGBA in linear space)
        curve_mapping: Blender CurveMapping object with 4 curves (C, R, G, B)
        
    Returns:
        NumPy array of transformed colors (Nx4 RGBA)
    """
    result = colors.copy()
    
    # CurveMapping has curves in order: C (combined), R, G, B
    # We apply per-channel curves first, then the combined curve
    c_curve = curve_mapping.curves[3]  # Combined/Master (index 3 for COLOR type)
    r_curve = curve_mapping.curves[0]  # Red
    g_curve = curve_mapping.curves[1]  # Green
    b_curve = curve_mapping.curves[2]  # Blue
    
    # Apply per-channel curves (vectorized)
    result[:, 0] = get_curve_value_vectorized(curve_mapping, r_curve, colors[:, 0])
    result[:, 1] = get_curve_value_vectorized(curve_mapping, g_curve, colors[:, 1])
    result[:, 2] = get_curve_value_vectorized(curve_mapping, b_curve, colors[:, 2])
    
    # Apply combined curve to all RGB channels
    result[:, 0] = get_curve_value_vectorized(curve_mapping, c_curve, result[:, 0])
    result[:, 1] = get_curve_value_vectorized(curve_mapping, c_curve, result[:, 1])
    result[:, 2] = get_curve_value_vectorized(curve_mapping, c_curve, result[:, 2])
    
    # Clamp results to valid range
    result[:, :3] = np.clip(result[:, :3], 0.0, 1.0)
    
    # Preserve alpha
    result[:, 3] = colors[:, 3]
    
    return result


class VGRADIENT_OT_apply_curves(bpy.types.Operator):
    """Apply RGB curves adjustment to vertex colors on selected objects"""
    bl_idname = "vgradient.apply_curves"
    bl_label = "Apply RGB Curves"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply RGB curves adjustment to vertex colors"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    @classmethod
    def poll(cls, context):
        # Check if we have valid objects to work with
        if context.mode == 'SCULPT':
            return context.active_object and context.active_object.type == 'MESH'
        elif context.mode == 'EDIT_MESH':
            return context.active_object and context.active_object.type == 'MESH'
        else:  # Object mode
            return any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        """Execute the curves adjustment operation"""
        start_time = time.time()
        total_start = time.time()
        
        # Get the curve mapping from the stored node
        curve_mapping = get_curves_mapping()
        if not curve_mapping:
            self.report({'WARNING'}, "No curves data found. Please initialize curves first.")
            return {'CANCELLED'}
        
        # Update the curve mapping to ensure it's ready for evaluation
        curve_mapping.update()
        
        # Get list of objects to process
        objects = []
        if context.mode == 'SCULPT':
            objects = [context.active_object]
        elif context.mode == 'EDIT_MESH':
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        else:  # Object mode
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
            
        if not objects:
            self.report({'WARNING'}, "No valid mesh objects found")
            return {'CANCELLED'}
        
        processed_count = 0
        
        # Process each object
        for obj in objects:
            mesh = obj.data
            num_verts = len(mesh.vertices)
            
            # Get or create vertex color attribute
            target_attribute = utils.ensure_vertex_color_attribute(obj)
            if not target_attribute:
                self.report({'WARNING'}, f"Could not find/create color attribute for {obj.name}")
                continue
            
            # Make sure the color attribute is active
            obj.data.attributes.active_color = target_attribute
            
            # Get selected vertices in Edit mode
            selected_verts = None
            if context.mode == 'EDIT_MESH':
                selected_verts = utils.get_selected_vertices(obj)

            # Check if we need to respect sculpt mask
            use_existing_mask = False
            mask_data = None
            if hasattr(obj.data, 'vertex_paint_mask'):
                mask = obj.data.vertex_paint_mask
                if mask and hasattr(mask, 'data'):
                    use_existing_mask = True
                    mask_data = np.empty(num_verts, dtype=np.float32)
                    mask.data.foreach_get('value', mask_data)

            if not use_existing_mask:
                mask = obj.data.attributes.get("mask")
                if mask and hasattr(mask, 'data'):
                    use_existing_mask = True
                    mask_data = np.empty(num_verts, dtype=np.float32)
                    mask.data.foreach_get('value', mask_data)
            
            # Check if we have stored colors to use as baseline
            if "vgradient_stored_colors" in obj:
                stored_data = obj["vgradient_stored_colors"]
                source_colors = np.array(stored_data, dtype=np.float32).reshape(num_verts, 4)
            else:
                # No stored colors, read current colors
                if obj.mode == 'EDIT':
                    source_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
                else:
                    source_colors = np.zeros(num_verts * 4, dtype=np.float32)
                    target_attribute.data.foreach_get("color", source_colors)
                    source_colors = source_colors.reshape(num_verts, 4)
            
            # Read existing colors for blend mode (current state on mesh)
            if obj.mode == 'EDIT':
                existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
            else:
                existing_colors = np.zeros(num_verts * 4, dtype=np.float32)
                target_attribute.data.foreach_get("color", existing_colors)
                existing_colors = existing_colors.reshape(num_verts, 4)
            
            # Apply curves transformation to source colors (stored or current)
            new_colors = apply_curves_to_colors(source_colors, curve_mapping)
            
            # Apply contrast adjustment
            contrast = context.scene.vgradient_curves_contrast
            new_colors = apply_contrast(new_colors, contrast)
            
            # Apply saturation adjustment
            saturation = context.scene.vgradient_curves_saturation
            new_colors = apply_saturation(new_colors, saturation)
            
            # Get global opacity and blend mode
            opacity = context.scene.vgradient_global_opacity
            blend_mode = context.scene.vgradient_blend_mode
            
            # Apply blend mode if needed
            if blend_mode != 'NORMAL' or opacity < 0.999:
                final_colors = utils.apply_blend_mode(
                    existing_colors,
                    new_colors,
                    blend_mode,
                    opacity
                )
            else:
                final_colors = new_colors
            
            # Handle Edit mode selection
            if selected_verts is not None and len(selected_verts) > 0:
                # Only apply to selected vertices
                mask = np.zeros(num_verts, dtype=bool)
                mask[selected_verts] = True
                final_colors = np.where(mask[:, np.newaxis], final_colors, existing_colors)

            # In sculpt mode, respect existing mask data
            if use_existing_mask:
                final_colors = (
                    existing_colors * mask_data[:, np.newaxis]
                    + final_colors * (1 - mask_data[:, np.newaxis])
                )
            
            # Write colors back
            utils.update_color_attribute(obj, target_attribute, final_colors, selected_verts)
            processed_count += 1
        
        utils.print_timing(total_start, "Total curves adjustment time")
        self.report({'INFO'}, f"Applied curves to {processed_count} object(s)")
        return {'FINISHED'}


def has_stored_colors(context):
    """Check if any selected object has stored colors"""
    if context.mode == 'SCULPT':
        if context.active_object and context.active_object.type == 'MESH':
            return "vgradient_stored_colors" in context.active_object
    elif context.mode == 'EDIT_MESH':
        if context.active_object and context.active_object.type == 'MESH':
            return "vgradient_stored_colors" in context.active_object
    else:
        for obj in context.selected_objects:
            if obj.type == 'MESH' and "vgradient_stored_colors" in obj:
                return True
    return False


class VGRADIENT_OT_store_colors(bpy.types.Operator):
    """Store current vertex colors as baseline for non-destructive editing"""
    bl_idname = "vgradient.store_colors"
    bl_label = "Store Colors"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Store current vertex colors as baseline for curves adjustment"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @classmethod
    def poll(cls, context):
        if context.mode == 'SCULPT':
            return context.active_object and context.active_object.type == 'MESH'
        elif context.mode == 'EDIT_MESH':
            return context.active_object and context.active_object.type == 'MESH'
        else:
            return any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        """Store current vertex colors for each selected object"""
        objects = []
        if context.mode == 'SCULPT':
            objects = [context.active_object]
        elif context.mode == 'EDIT_MESH':
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        else:
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not objects:
            self.report({'WARNING'}, "No valid mesh objects found")
            return {'CANCELLED'}
        
        stored_count = 0
        for obj in objects:
            mesh = obj.data
            num_verts = len(mesh.vertices)
            
            target_attribute = utils.ensure_vertex_color_attribute(obj)
            if not target_attribute:
                continue
            
            # Read current colors
            if obj.mode == 'EDIT':
                colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
            else:
                colors = np.zeros(num_verts * 4, dtype=np.float32)
                target_attribute.data.foreach_get("color", colors)
                colors = colors.reshape(num_verts, 4)
            
            # Store as custom property on the object (flattened list)
            obj["vgradient_stored_colors"] = colors.flatten().tolist()
            stored_count += 1
        
        self.report({'INFO'}, f"Stored colors for {stored_count} object(s)")
        return {'FINISHED'}


class VGRADIENT_OT_clear_stored_colors(bpy.types.Operator):
    """Clear stored vertex colors from selected objects"""
    bl_idname = "vgradient.clear_stored_colors"
    bl_label = "Clear Stored Colors"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Remove stored base colors from selected objects"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @classmethod
    def poll(cls, context):
        return has_stored_colors(context)
    
    def execute(self, context):
        """Clear stored colors from selected objects"""
        objects = []
        if context.mode == 'SCULPT':
            objects = [context.active_object]
        elif context.mode == 'EDIT_MESH':
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        else:
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        cleared_count = 0
        for obj in objects:
            if "vgradient_stored_colors" in obj:
                del obj["vgradient_stored_colors"]
                cleared_count += 1
        
        self.report({'INFO'}, f"Cleared stored colors from {cleared_count} object(s)")
        return {'FINISHED'}


class VGRADIENT_OT_reset_curves(bpy.types.Operator):
    """Reset RGB curves to default linear values and restore stored colors"""
    bl_idname = "vgradient.reset_curves"
    bl_label = "Reset Curves"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Reset curves, contrast, saturation, and optionally restore stored colors"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def execute(self, context):
        """Reset all curves to linear and reset contrast/saturation"""
        curve_mapping = get_curves_mapping()
        if curve_mapping:
            # Reset each curve to linear
            for curve in curve_mapping.curves:
                # Remove all points except first and last
                while len(curve.points) > 2:
                    curve.points.remove(curve.points[1])
                
                # Set first point to (0, 0) and last to (1, 1)
                curve.points[0].location = (0.0, 0.0)
                curve.points[0].handle_type = 'AUTO'
                curve.points[-1].location = (1.0, 1.0)
                curve.points[-1].handle_type = 'AUTO'
            
            # Update the curve mapping
            curve_mapping.update()
        
        # Reset contrast and saturation sliders
        context.scene.vgradient_curves_contrast = 0.0
        context.scene.vgradient_curves_saturation = 0.0
        
        # Restore stored colors for selected objects
        objects = []
        if context.mode == 'SCULPT':
            objects = [context.active_object]
        elif context.mode == 'EDIT_MESH':
            if context.active_object and context.active_object.type == 'MESH':
                objects = [context.active_object]
        else:
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        restored_count = 0
        for obj in objects:
            if "vgradient_stored_colors" not in obj:
                continue
            
            mesh = obj.data
            num_verts = len(mesh.vertices)
            
            target_attribute = utils.ensure_vertex_color_attribute(obj)
            if not target_attribute:
                continue
            
            # Restore stored colors
            stored_data = obj["vgradient_stored_colors"]
            stored_colors = np.array(stored_data, dtype=np.float32).reshape(num_verts, 4)
            
            utils.update_color_attribute(obj, target_attribute, stored_colors, None)
            restored_count += 1
        
        if restored_count > 0:
            self.report({'INFO'}, f"Reset curves and restored colors for {restored_count} object(s)")
        else:
            self.report({'INFO'}, "Curves reset to default (no stored colors found)")
        return {'FINISHED'}


class VGRADIENT_OT_init_curves(bpy.types.Operator):
    """Initialize RGB curves for vertex color adjustment"""
    bl_idname = "vgradient.init_curves"
    bl_label = "Initialize Curves"
    bl_options = {'REGISTER'}
    bl_description = "Initialize the RGB curves editor"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def execute(self, context):
        """Initialize the CurveMapping"""
        # Get or create the curves node (this also creates the node tree if needed)
        curves_node = get_or_create_curves_node()
        
        if curves_node:
            self.report({'INFO'}, "RGB Curves initialized")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to initialize RGB Curves")
            return {'CANCELLED'}


# List of operator classes
classes = (
    VGRADIENT_OT_apply_curves,
    VGRADIENT_OT_store_colors,
    VGRADIENT_OT_clear_stored_colors,
    VGRADIENT_OT_reset_curves,
    VGRADIENT_OT_init_curves,
)


def register():
    """Register curves operators"""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister curves operators"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
