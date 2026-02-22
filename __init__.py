"""
vColorTools - Vertex Color Tools addon for Blender
Tools to supplement your vertex painting workflow
"""

bl_info = {
    "name": "vColor Tools",
    "blender": (4, 5, 0),
    "category": "Object",
    "version": (2, 0, 1),
    "author": "MattGPT",
    "description": "Tools to supplement your vertex painting workflow",
}

import bpy
from bpy.props import IntProperty, CollectionProperty, PointerProperty
from bpy.app.handlers import persistent
from . import operators
from . import ui
from . import properties
from . import preferences
from . import utils
from .ui import color_palette

# Store keymap entries to remove on unregister
addon_keymaps = []

# Check Blender version
def get_blender_version():
    """Get the current Blender version as a tuple"""
    return bpy.app.version

def is_blender_44_or_newer():
    """Check if Blender version is 4.4 or newer"""
    version = get_blender_version()
    return version[0] > 4 or (version[0] == 4 and version[1] >= 4)

# Scene load handler to initialize gradient positions and migrate legacy gradients
@persistent
def initialize_gradient_positions(dummy):
    """Initialize positions and migrate legacy gradients for all scenes"""
    # This runs when a file is loaded
    # First, migrate any legacy gradients to the new ColorRamp format
    utils.migrate_legacy_gradients()
    
    # Then ensure gradient positions are initialized
    for scene in bpy.data.scenes:
        if hasattr(scene, 'vgradient_collection'):
            for gradient in scene.vgradient_collection:
                utils.ensure_gradient_positions(gradient)


@persistent
def persist_gradient_color_ramps(dummy):
    """Persist ColorRamp edits back to scene data before saving."""
    utils.sync_all_color_ramps_to_gradients()

def register():
    # Register preferences (includes auto-updater)
    preferences.register()
    
    # Register property classes
    properties.register()
    
    # Register operators
    operators.register()
    
    # Register properties
    bpy.types.Scene.vgradient_collection = CollectionProperty(type=properties.GradientData)
    bpy.types.Scene.vgradient_active_index = IntProperty()
    
    # Register handlers for load/save gradient data flow
    bpy.app.handlers.load_post.append(initialize_gradient_positions)
    bpy.app.handlers.save_pre.append(persist_gradient_color_ramps)
    
    # Register UI - do this last so UI can access the properties
    ui.register()
    
    # Add keymap entries
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Linear gradient
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_linear.bl_idname,
            type='MINUS',
            value='PRESS'
        )
        addon_keymaps.append((km, kmi))
        
        # Radial gradient
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_radial.bl_idname,
            type='ZERO',
            value='PRESS'
        )
        addon_keymaps.append((km, kmi))
        
        # Curve gradient
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_curve.bl_idname,
            type='ZERO',
            value='PRESS',
            shift=True
        )
        addon_keymaps.append((km, kmi))
        
        # Flood fill
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_flood_fill.bl_idname,
            type='EQUAL',
            value='PRESS'
        )
        addon_keymaps.append((km, kmi))

        # Flex gradient
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_flex_gradient.bl_idname,
            type='EQUAL',
            value='PRESS',
            shift=True
        )
        addon_keymaps.append((km, kmi))
        
        # Normal gradient
        kmi = km.keymap_items.new(
            operators.VGRADIENT_OT_normal.bl_idname,
            type='MINUS',
            value='PRESS',
            shift=True
        )
        addon_keymaps.append((km, kmi))

def unregister():
    # Remove keymap entries
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Remove handlers
    if initialize_gradient_positions in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(initialize_gradient_positions)
    if persist_gradient_color_ramps in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(persist_gradient_color_ramps)
    
    # Unregister UI
    ui.unregister()
    
    # Unregister operators
    operators.unregister()
    
    # Unregister property classes
    properties.unregister()
    
    # Remove properties
    del bpy.types.Scene.vgradient_active_index
    del bpy.types.Scene.vgradient_collection
    
    # Unregister preferences
    preferences.unregister()

if __name__ == "__main__":
    register()
