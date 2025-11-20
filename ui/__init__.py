"""
UI module for vColGradient addon
Contains panel and UI list classes
"""

import bpy
from . import color_palette
from . import panels
from . import debug
from . import gradient_editor

# List of all classes to register from this module
classes = []

def register():
    """Register all UI classes"""
    # Register panel classes
    panels.register()
    
    # Register color palette UI
    color_palette.register()
    
    # Register gradient editor UI
    gradient_editor.register()
    
    # Register debug UI
    debug.register()

def unregister():
    """Unregister all UI classes"""
    # Unregister debug UI
    debug.unregister()
    
    # Unregister gradient editor UI
    gradient_editor.unregister()
    
    # Unregister color palette UI
    color_palette.unregister()
    
    # Unregister panel classes
    panels.unregister()
