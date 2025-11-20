"""
Debug utilities for vColorTools addon
"""

import bpy

class VGRADIENT_OT_debug_palette(bpy.types.Operator):
    """Debug operator to check palette status"""
    bl_idname = "vgradient.debug_palette"
    bl_label = "Debug Palette"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        
        # Check if palette property exists
        has_palette_prop = hasattr(scene, "vgradient_active_palette")
        active_palette = scene.vgradient_active_palette if has_palette_prop else None
        
        # Check if the vColorTools palette exists in Blender's data
        palette_exists = "vColorTools" in bpy.data.palettes
        palette = bpy.data.palettes.get("vColorTools")
        palette_colors = len(palette.colors) if palette else 0
        
        # Report results
        self.report({'INFO'}, f"Palette property exists: {has_palette_prop}, ")
        self.report({'INFO'}, f"vColorTools palette exists: {palette_exists}, Colors: {palette_colors}")
        
        # Create the palette if it doesn't exist
        if not palette_exists or palette_colors == 0:
            bpy.ops.vgradient.create_default_palette()
            self.report({'INFO'}, "Created default vColorTools palette")
        
        # Set the active palette if it's not set
        if has_palette_prop and not active_palette and "vColorTools" in bpy.data.palettes:
            scene.vgradient_active_palette = bpy.data.palettes["vColorTools"]
            self.report({'INFO'}, "Set vColorTools as the active palette")
        
        return {'FINISHED'}

# List of all classes in this module
classes = (
    VGRADIENT_OT_debug_palette,
)

def register():
    """Register debug classes"""
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    """Unregister debug classes"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
