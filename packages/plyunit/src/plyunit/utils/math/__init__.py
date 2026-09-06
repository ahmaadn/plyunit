"""Math helpers: clamp, lerp, and easing."""

from .easing import EASINGS, get_easing
from .utils import clamp, lerp, lerp_vector2

__all__ = [
    "EASINGS",
    "clamp",
    "get_easing",
    "lerp",
    "lerp_vector2",
]
