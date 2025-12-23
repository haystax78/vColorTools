"""
Operators module for vColGradient addon
Contains all operator classes
"""

import bpy
from bpy.props import EnumProperty, StringProperty
from . import utils
from . import gradient_operators

# Import all operator classes from submodules
from .gradient_operators.linear import VGRADIENT_OT_linear
from .gradient_operators.radial import VGRADIENT_OT_radial
from .gradient_operators.normal import VGRADIENT_OT_normal
from .gradient_operators.curve import VGRADIENT_OT_curve
from .gradient_operators.flood_fill import VGRADIENT_OT_flood_fill
from .gradient_operators.management import (
    VGRADIENT_OT_add_gradient,
    VGRADIENT_OT_remove_gradient,
    VGRADIENT_OT_migrate_gradients
)
from .gradient_operators.curves import (
    VGRADIENT_OT_apply_curves,
    VGRADIENT_OT_store_colors,
    VGRADIENT_OT_clear_stored_colors,
    VGRADIENT_OT_reset_curves,
    VGRADIENT_OT_init_curves
)

# List of all operator classes
classes = (
    VGRADIENT_OT_add_gradient,
    VGRADIENT_OT_remove_gradient,
    VGRADIENT_OT_migrate_gradients,
    VGRADIENT_OT_linear,
    VGRADIENT_OT_radial,
    VGRADIENT_OT_normal,
    VGRADIENT_OT_curve,
    VGRADIENT_OT_flood_fill,
    VGRADIENT_OT_apply_curves,
    VGRADIENT_OT_store_colors,
    VGRADIENT_OT_clear_stored_colors,
    VGRADIENT_OT_reset_curves,
    VGRADIENT_OT_init_curves,
)

def register():
    """Register all operator classes"""
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    """Unregister all operator classes"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
