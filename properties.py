"""
Properties module for vColGradient addon
Defines the property groups for gradient data
"""

import bpy
from bpy.props import FloatVectorProperty, IntProperty, BoolProperty, CollectionProperty, StringProperty, FloatProperty

class GradientColorItem(bpy.types.PropertyGroup):
    """Group of properties for a gradient color"""
    color: FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0, 1.0),
        size=4,
        min=0.0, max=1.0,
        description="Color for gradient stop"
    )
    position: FloatProperty(
        name="Position",
        default=0.0,
        min=0.0, max=1.0,
        description="Position of the color stop along the gradient (0-1)"
    )

class GradientData(bpy.types.PropertyGroup):
    """Group of properties for a gradient"""
    name: StringProperty(
        name="Name",
        default="Gradient",
        description="Gradient name"
    )
    colors: CollectionProperty(
        type=GradientColorItem,
        name="Colors",
        description="Gradient colors"
    )
    active_color_index: IntProperty(
        name="Active Color Index",
        default=0,
        min=0
    )
    use_oklab: BoolProperty(
        name="Use Oklab Blending",
        description="Use Oklab color space for more perceptually uniform color blending",
        default=False
    )
    use_screen_space: BoolProperty(
        name="Screen Space",
        description="Use screen space projection instead of 3D space projection",
        default=True
    )

# List of all classes in this module
classes = (
    GradientColorItem,
    GradientData,
)

def register():
    """Register all property classes"""
    for cls in classes:
        bpy.utils.register_class(cls)
        
    # Register global opacity property
    bpy.types.Scene.vgradient_global_opacity = bpy.props.FloatProperty(
        name="Opacity",
        description="Global opacity for all color tools (controls blending with existing colors)",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    # Register blend mode property
    bpy.types.Scene.vgradient_blend_mode = bpy.props.EnumProperty(
        name="Blend Mode",
        description="Method used to blend colors with existing vertex colors",
        items=[
            ('NORMAL', "Normal", "Standard alpha blending"),
            ('MULTIPLY', "Multiply", "Multiply colors together"),
            ('ADD', "Add", "Add colors together"),
            ('SUBTRACT', "Subtract", "Subtract colors"),
            ('COLOR', "Color", "Preserve luminosity of base color while applying the hue and saturation of the blend color")
        ],
        default='NORMAL'
    )
    
    bpy.types.Scene.vgradient_use_unified_color = bpy.props.BoolProperty(
        name="Use Global Color",
        description="Use Blender's global paint color for flood fill instead of the custom color",
        default=False
    )

    # Register flood fill color property
    bpy.types.Scene.vgradient_flood_fill_color = bpy.props.FloatVectorProperty(
        name="Flood Fill Color",
        description="Color used by the Flood Fill tool",
        subtype='COLOR',
        default=(0.5, 0.5, 0.5, 1.0),
        size=4,
        min=0.0,
        max=1.0
    )
    
    # Register UI panel states
    bpy.types.Scene.vgradient_show_info_panel = bpy.props.BoolProperty(
        name="Show Info Panel",
        default=False,
        description="Show or hide the tool information panel"
    )
    
    # Register panel visibility states
    bpy.types.Scene.vgradient_show_gradient_tools = bpy.props.BoolProperty(
        name="Show Gradient Tools",
        default=True,
        description="Show or hide the gradient tools panel"
    )
    
    bpy.types.Scene.vgradient_show_flood_fill = bpy.props.BoolProperty(
        name="Show Flood Fill Tool",
        default=True,
        description="Show or hide the flood fill tool panel"
    )
    
    bpy.types.Scene.vgradient_show_color_palette = bpy.props.BoolProperty(
        name="Show Color Palette",
        default=True,
        description="Show or hide the color palette panel"
    )

def unregister():
    """Unregister all property classes"""
    # Unregister scene properties
    del bpy.types.Scene.vgradient_use_unified_color
    del bpy.types.Scene.vgradient_flood_fill_color
    del bpy.types.Scene.vgradient_global_opacity
    del bpy.types.Scene.vgradient_blend_mode
    del bpy.types.Scene.vgradient_show_info_panel
    del bpy.types.Scene.vgradient_show_gradient_tools
    del bpy.types.Scene.vgradient_show_flood_fill
    del bpy.types.Scene.vgradient_show_color_palette
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    # Unregister global opacity property
    if hasattr(bpy.types.Scene, 'vgradient_global_opacity'):
        del bpy.types.Scene.vgradient_global_opacity
    
    if hasattr(bpy.types.Scene, 'vgradient_use_unified_color'):
        del bpy.types.Scene.vgradient_use_unified_color

    if hasattr(bpy.types.Scene, 'vgradient_flood_fill_color'):
        del bpy.types.Scene.vgradient_flood_fill_color
