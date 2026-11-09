"""Utility subpackage: math, geometry, IO, text, and data structures."""

from . import math as math
from .io import read_json, write_json
from .paths import resolve_config_resource, resolve_inside
from .rects import full_rect, iter_region_rects, parse_rect, shift_rect
from .text import bstr

__all__ = [
    "bstr",
    "full_rect",
    "iter_region_rects",
    "math",
    "parse_rect",
    "read_json",
    "resolve_config_resource",
    "resolve_inside",
    "shift_rect",
    "write_json",
]
