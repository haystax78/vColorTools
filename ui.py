"""
UI module for vColGradient addon - Legacy file
This file is kept for backward compatibility and imports from the ui module
"""

import bpy
from . import ui

def register():
    """Register all UI classes"""
    ui.register()

def unregister():
    """Unregister all UI classes"""
    ui.unregister()
