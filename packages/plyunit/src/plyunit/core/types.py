"""Shared engine types (Texture, RectType, ColorType, ...).

Contains primitive type aliases and lightweight protocols used by the core
engine components without depending on the renderer backend.
"""

import array
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

type ColorType = tuple[int, int, int, int]
"""RGBA color representation (red, green, blue, alpha)."""

type Vec2Type = tuple[float, float]
"""2D vector or point (x, y)."""

type RectType = tuple[float, float, float, float]
"""Rectangle geometry defined by (x, y, width, height)."""

type PosType = Vec2Type
"""2D spatial position (x, y)."""

type SizeType = Vec2Type
"""2D dimensions (width, height)."""

type SourceRectType = RectType
"""Source rectangle (x, y, width, height) defining a sub-region of a texture."""

type PosFlatType = array.array[float] | Sequence[float]
"""Flat sequence of positions [x0, y0, x1, y1, ...] optimized for batch submissions."""

type PosNestedType = Sequence[PosType]
"""Nested sequence of positions [(x0, y0), (x1, y1), ...]."""


@runtime_checkable
class PrColor(Protocol):
    """4-component R8G8B8A8 (32-bit) color."""

    r: int
    g: int
    b: int
    a: int


@runtime_checkable
class Vector2Type(Protocol):
    """2D vector components."""

    x: float
    y: float


@runtime_checkable
class RectangleType(Protocol):
    """Rectangle geometry components."""

    x: float
    y: float
    width: float
    height: float


@runtime_checkable
class Texture(Protocol):
    """GPU texture object properties."""

    id: int
    width: int
    height: int
    mipmaps: int
    format: int


@runtime_checkable
class RenderTexture(Protocol):
    """RenderTexture (FBO) for render-to-texture operations."""

    id: int
    texture: Texture
    depth: Texture


@runtime_checkable
class ShaderType(Protocol):
    """GPU shader program."""

    id: int
    locs: Sequence[int]  # Array of shader uniform locations


@runtime_checkable
class NPatchInfoType(Protocol):
    """NPatch (nine-patch) layout configuration for scalable textures."""

    source: RectangleType
    left: int
    top: int
    right: int
    bottom: int
    layout: int


@runtime_checkable
class FontType(Protocol):
    """Font object containing a glyph atlas texture and rendering metrics."""

    baseSize: int
    glyphCount: int
    glyphPadding: int
    texture: Texture
    recs: Sequence[RectangleType]
    glyphs: Sequence[Any]  # Replace Any with a GlyphInfo protocol if available
