"""Utility subpackage: math, geometry, IO, text, and data structures."""

from . import math as math
from .io import read_json, write_json
from .text import bstr

__all__ = [
    "bstr",
    "math",
    "read_json",
    "write_json",
]
