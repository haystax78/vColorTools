"""
UI module for vColGradient addon
Contains panel and UI list classes
"""

import bpy
from . import color_palette
from . import panels
from . import debug

# List of all classes to register from this module
classes = []

def register():
    """Register all UI classes"""
    # Register panel classes
    panels.register()
    
    # Register color palette UI
    color_palette.register()
    
    # Register debug UI
    debug.register()

def unregister():
    """Unregister all UI classes"""
    # Unregister debug UI
    debug.unregister()
    
    # Unregister color palette UI
    color_palette.unregister()
    
    # Unregister panel classes
    panels.unregister()
