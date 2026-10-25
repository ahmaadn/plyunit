"""Math helpers: clamp, lerp, and easing."""

from .easing import EASINGS, get_easing
from .geometry import (
    aabb_contains,
    aabb_from_center,
    aabb_intersection,
    aabb_intersects,
    aabb_union,
    contains,
    expand_aabb,
)
from .utils import clamp, lerp, lerp_vector2

__all__ = [
    "EASINGS",
    "aabb_contains",
    "aabb_from_center",
    "aabb_intersection",
    "aabb_intersects",
    "aabb_union",
    "clamp",
    "contains",
    "expand_aabb",
    "get_easing",
    "lerp",
    "lerp_vector2",
]
