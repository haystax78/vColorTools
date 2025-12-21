"""
Flood fill operator for vColGradient addon
Fills the entire mesh with a single color
"""

import bpy
import numpy as np
import time
from .. import utils

class VGRADIENT_OT_flood_fill(bpy.types.Operator):
    """Fill the entire mesh with a single color"""
    bl_idname = "vgradient.flood_fill"
    bl_label = "Flood Fill"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Fill the entire mesh with the selected color"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def execute(self, context):
        """Execute the flood fill operation"""
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
        
        # Always use vertex color mode, not mask mode
        use_mask_mode = False
        
        if context.scene.vgradient_use_unified_color:
            # Get color from unified paint settings
            ups = utils.get_unified_paint_settings(context)
            if ups:
                # In Blender 5.0+, unified_paint_settings.color is already linear
                # In earlier versions, it was sRGB
                if bpy.app.version >= (5, 0, 0):
                    # Blender 5.0+: color is already in linear space
                    linear_color = tuple(ups.color)
                else:
                    # Pre-5.0: color is in sRGB, convert to linear
                    linear_color = utils.convert_color_srgb_to_linear(ups.color)
            else:
                # Fallback to scene property
                linear_color = context.scene.vgradient_flood_fill_color
        else:
            # Get color from the custom flood fill property
            # FloatVectorProperty(subtype='COLOR') stores linear color
            linear_color = context.scene.vgradient_flood_fill_color
        
        # Convert from RGB to RGBA (add alpha=1.0)
        fill_color = (linear_color[0], linear_color[1], linear_color[2], 1.0)
        
        # Ensure we have a palette set
        scene = context.scene
        if not scene.vgradient_active_palette and "vColorTools" in bpy.data.palettes:
            scene.vgradient_active_palette = bpy.data.palettes["vColorTools"]
        
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
                
                target_attribute = obj.data.attributes[".sculpt_mask"]
                
                # Fill the mask with the value (using only the red channel for intensity)
                num_verts = len(mesh.vertices)
                mask_value = fill_color[0]  # Use red channel as mask intensity
                mask_values = np.full(num_verts, mask_value, dtype=np.float32)
                target_attribute.data.foreach_set("value", mask_values)
                
            else:
                # Get active vertex colors
                target_attribute = utils.ensure_vertex_color_attribute(obj)
                if not target_attribute:
                    self.report({'WARNING'}, f"Could not create or find a color attribute for object {obj.name}")
                    continue
                
                # Make sure the color attribute is active
                obj.data.attributes.active_color = target_attribute
                
                # Get global opacity for blending
                opacity = context.scene.vgradient_global_opacity
                num_verts = len(mesh.vertices)
                
                # Check if we need to respect the sculpt mask
                use_existing_mask = False
                mask_data = None
                if context.mode == 'SCULPT':
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
                
                # Get the current blend mode
                blend_mode = context.scene.vgradient_blend_mode
                
                # Check if we need to get existing colors for blending or masking
                # We need existing colors for all blend modes except NORMAL with opacity=1
                need_current_values = use_existing_mask or opacity < 0.999 or blend_mode != 'NORMAL'
                
                # Get selected vertices in Edit mode
                selected_verts = None
                if context.mode == 'EDIT_MESH':
                    selected_verts = utils.get_selected_vertices(obj)
                
                # Create array of new colors
                new_colors = np.tile(fill_color, (num_verts, 1)).astype(np.float32)
                
                # Initialize existing_colors to None
                existing_colors = None
                
                # Get existing colors if needed
                if need_current_values:
                    # Get existing colors
                    # In Edit mode, we need to use BMesh to get colors with proper color space conversion
                    if obj.mode == 'EDIT':
                        existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
                    else:
                        # In Object mode, we can use foreach_get
                        existing_colors = np.zeros(num_verts * 4, dtype=np.float32)
                        target_attribute.data.foreach_get("color", existing_colors)
                        existing_colors = existing_colors.reshape(num_verts, 4)
                
                # Apply blend mode based on settings
                if blend_mode == 'NORMAL' and opacity >= 0.999:
                    # For normal blend mode with full opacity, just use new colors directly
                    opacity_blended_colors = new_colors
                else:
                    # For all other cases, apply the selected blend mode
                    opacity_blended_colors = utils.apply_blend_mode(
                        existing_colors, 
                        new_colors, 
                        blend_mode, 
                        opacity
                    )
                
                # Apply mask if in sculpt mode and mask exists
                if use_existing_mask:
                    # Apply mask (0=unmasked, 1=masked)
                    # Blend between existing colors and opacity-blended colors based on mask
                    # mask_data: 0=unmasked (apply new color), 1=masked (keep original)
                    final_colors = existing_colors * mask_data[:, np.newaxis] + opacity_blended_colors * (1 - mask_data[:, np.newaxis])
                    # Use the utility function to update color attribute (handles Edit mode correctly)
                    utils.update_color_attribute(obj, target_attribute, final_colors, None)
                elif selected_verts is not None:
                    # In Edit mode with selection, only apply to selected vertices
                    # Get existing colors if we haven't already
                    if existing_colors is None:
                        # Get colors with proper color space conversion
                        existing_colors = utils.get_vertex_colors_from_bmesh(obj, num_verts)
                    
                    # Create a mask for selected vertices
                    mask = np.zeros(num_verts, dtype=bool)
                    mask[selected_verts] = True
                    
                    # Apply colors only to selected vertices
                    # For unselected vertices, keep their current values
                    final_colors = np.where(mask[:, np.newaxis], opacity_blended_colors, existing_colors)
                    # Use the utility function to update color attribute (handles Edit mode correctly)
                    utils.update_color_attribute(obj, target_attribute, final_colors, selected_verts)
                else:
                    # If no mask or selection, just apply the opacity-blended colors
                    # Use the utility function to update color attribute (handles Edit mode correctly)
                    utils.update_color_attribute(obj, target_attribute, opacity_blended_colors, None)
            
        utils.print_timing(total_start, "Total flood fill time")
        return {'FINISHED'}
