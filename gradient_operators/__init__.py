"""
Gradient operators package for vColGradient addon
Contains all gradient-related operator classes
"""

# Import all operator classes for easy access
from .linear import VGRADIENT_OT_linear
from .radial import VGRADIENT_OT_radial
from .normal import VGRADIENT_OT_normal
from .flex import VGRADIENT_OT_flex_gradient
from .management import (
    VGRADIENT_OT_add_gradient,
    VGRADIENT_OT_remove_gradient,
    VGRADIENT_OT_migrate_gradients
)
