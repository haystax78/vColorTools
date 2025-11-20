"""
Gradient operators package for vColGradient addon
Contains all gradient-related operator classes
"""

# Import all operator classes for easy access
from .linear import VGRADIENT_OT_linear
from .radial import VGRADIENT_OT_radial
from .normal import VGRADIENT_OT_normal
from .management import (
    VGRADIENT_OT_add_color,
    VGRADIENT_OT_remove_color,
    VGRADIENT_OT_move_color,
    VGRADIENT_OT_add_gradient,
    VGRADIENT_OT_remove_gradient
)
