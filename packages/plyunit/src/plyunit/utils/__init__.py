"""Utility subpackage: math, geometry, IO, text, and data structures."""

from . import math as math
from .geometry import (
    aabb_contains,
    aabb_from_center,
    aabb_intersection,
    aabb_intersects,
    aabb_union,
    expand_aabb,
)
from .io import read_json, write_json
from .text import bstr

__all__ = [
    "aabb_contains",
    "aabb_from_center",
    "aabb_intersection",
    "aabb_intersects",
    "aabb_union",
    "bstr",
    "expand_aabb",
    "math",
    "read_json",
    "write_json",
]
