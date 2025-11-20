"""
Color palette UI components for vColorTools addon
Uses Blender's built-in palette system for color management
"""

import bpy
import math
from bpy.props import FloatVectorProperty, IntProperty, BoolProperty, StringProperty, PointerProperty
from .. import utils

# Color space conversion functions
def srgb_to_linear(c):
    """Convert from sRGB to linear RGB"""
    if c <= 0.04045:
        return c / 12.92
    else:
        return math.pow((c + 0.055) / 1.055, 2.4)

def linear_to_srgb(c):
    """Convert from linear RGB to sRGB"""
    if c <= 0.0031308:
        return c * 12.92
    else:
        return 1.055 * math.pow(c, 1/2.4) - 0.055

def convert_color_srgb_to_linear(color):
    """Convert a color from sRGB to linear RGB"""
    return tuple(srgb_to_linear(c) for c in color)

def convert_color_linear_to_srgb(color):
    """Convert a color from linear RGB to sRGB"""
    return tuple(linear_to_srgb(c) for c in color)

class VGRADIENT_OT_add_to_palette(bpy.types.Operator):
    """Add current color to active palette"""
    bl_idname = "vgradient.add_to_palette"
    bl_label = "Add to Palette"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Get the active palette
        palette = context.scene.vgradient_active_palette
        if not palette:
            self.report({'WARNING'}, "No active palette selected")
            return {'CANCELLED'}
            
        # Get the current color from UnifiedPaintSettings (sRGB) if available
        ups = utils.get_unified_paint_settings(context)
        
        # Add current color to palette
        color_item = palette.colors.new()
        
        # The color picker/palette expects sRGB
        if ups and hasattr(ups, 'color'):
            color_item.color = ups.color
        else:
            # Fallback: use scene property (likely linear); convert to sRGB
            lc = context.scene.vgradient_flood_fill_color
            color_item.color = (
                utils.linear_to_srgb(lc[0]),
                utils.linear_to_srgb(lc[1]),
                utils.linear_to_srgb(lc[2]),
                )
        
        return {'FINISHED'}

class VGRADIENT_OT_select_palette_color(bpy.types.Operator):
    """Select a color from the palette and set it as the active color"""
    bl_idname = "vgradient.select_palette_color"
    bl_label = "Select Color"
    bl_options = {'REGISTER', 'UNDO'}
    
    color_index: IntProperty(
        name="Color Index",
        default=0,
        min=0
    )
    
    def execute(self, context):
        scene = context.scene
        palette = scene.vgradient_active_palette
        
        if not palette or self.color_index >= len(palette.colors):
            return {'CANCELLED'}
        
        # Set the active color index
        scene.vgradient_active_color_index = self.color_index
        
        # Get the selected color from the palette
        color = palette.colors[self.color_index].color
        
        # Set the color in UnifiedPaintSettings if available, else mirror to scene prop
        ups = utils.get_unified_paint_settings(context)
        if ups and hasattr(ups, 'color'):
            ups.color = color
        else:
            # Store converted linear color in scene property so flood fill still uses it
            context.scene.vgradient_flood_fill_color = utils.convert_color_srgb_to_linear(color) + (1.0,)
        
        return {'FINISHED'}

class VGRADIENT_OT_remove_palette_color(bpy.types.Operator):
    """Remove the currently selected color from the palette"""
    bl_idname = "vgradient.remove_palette_color"
    bl_label = "Remove Color"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        palette = scene.vgradient_active_palette
        active_index = scene.vgradient_active_color_index
        
        if not palette or active_index < 0 or active_index >= len(palette.colors):
            self.report({'WARNING'}, "No active color to remove")
            return {'CANCELLED'}
        
        # Get the color to remove
        color_to_remove = palette.colors[active_index]
        
        # Remove the color from the palette
        palette.colors.remove(color_to_remove)
        
        # Update the active index
        if active_index >= len(palette.colors):
            scene.vgradient_active_color_index = max(0, len(palette.colors) - 1)
        
        self.report({'INFO'}, "Removed color from palette")
        return {'FINISHED'}

# Removed old comment

class VGRADIENT_OT_create_default_palette(bpy.types.Operator):
    """Create a default palette for vColorTools"""
    bl_idname = "vgradient.create_default_palette"
    bl_label = "Create Default Palette"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Create a new palette if it doesn't exist
        palette_name = "vColorTools"
        palette = None
        
        # Check if the palette already exists
        if palette_name in bpy.data.palettes:
            palette = bpy.data.palettes[palette_name]
        else:
            # Create a new palette
            palette = bpy.data.palettes.new(name=palette_name)
            
            # Add default colors to the palette (already in sRGB space for UI display)
            default_colors = [
                (1.0, 1.0, 1.0),  # White
                (0.0, 0.0, 0.0),  # Black
                (1.0, 0.0, 0.0),  # Red
                (0.0, 1.0, 0.0),  # Green
                (0.0, 0.0, 1.0),  # Blue
                (1.0, 1.0, 0.0),  # Yellow
                (1.0, 0.0, 1.0),  # Magenta
                (0.0, 1.0, 1.0),  # Cyan
            ]
            
            for color_rgb in default_colors:
                color = palette.colors.new()
                color.color = color_rgb
        
        # Set as the active palette
        context.scene.vgradient_active_palette = palette
        
        self.report({'INFO'}, f"Created or selected palette '{palette_name}'")
        return {'FINISHED'}

# List of all classes in this module
classes = (
    VGRADIENT_OT_add_to_palette,
    VGRADIENT_OT_select_palette_color,
    VGRADIENT_OT_remove_palette_color,
    VGRADIENT_OT_create_default_palette,
)

def register():
    """Register all UI classes"""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    # Reference to a Blender palette
    bpy.types.Scene.vgradient_active_palette = PointerProperty(
        type=bpy.types.Palette,
        name="Active Palette",
        description="Active color palette for vColorTools"
    )
    
    # Index of the active color in the palette
    bpy.types.Scene.vgradient_active_color_index = IntProperty(
        name="Active Color Index",
        default=0,
        min=-1,
        description="Index of the active color in the palette"
    )
    
    # Try to set a default palette if available
    try:
        if bpy.context.scene and not bpy.context.scene.vgradient_active_palette:
            # Look for existing vColorTools palette
            if "vColorTools" in bpy.data.palettes:
                bpy.context.scene.vgradient_active_palette = bpy.data.palettes["vColorTools"]
                
                # Initialize the unified paint settings color if needed
                ups = bpy.context.scene.tool_settings.unified_paint_settings
                if ups.color[0] == 0 and ups.color[1] == 0 and ups.color[2] == 0:
                    # Set to white as default
                    ups.color = (1.0, 1.0, 1.0)
    except:
        pass

def unregister():
    """Unregister all UI classes"""
    # Remove properties if they exist
    if hasattr(bpy.types.Scene, 'vgradient_active_palette'):
        del bpy.types.Scene.vgradient_active_palette
    if hasattr(bpy.types.Scene, 'vgradient_active_color_index'):
        del bpy.types.Scene.vgradient_active_color_index
    
    # Unregister classes
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass
