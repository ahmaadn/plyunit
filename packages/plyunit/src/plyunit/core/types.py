"""Shared engine types (Texture, RectType, ColorType, ...).

Contains primitive type aliases and lightweight protocols used by the core
engine components without depending on the renderer backend.
"""

import array
from collections.abc import Sequence
from typing import Any, Protocol

type ColorType = tuple[int, int, int, int]
"""Alias for ``tuple[int, int, int, int]`` for RGBA colors."""

type Vec2Type = tuple[float, float]
"""Alias for ``tuple[float, float]`` for 2D vectors or positions."""

type RectType = tuple[float, float, float, float]
"""Alias for ``tuple[float, float, float, float]`` for rectangles
``(x, y, width, height)``."""

type PosType = tuple[float, float]
"""Alias for ``tuple[float, float]`` for 2D positions."""

type SizeType = tuple[float, float]
"""Alias for ``tuple[float, float]`` for width and height."""

type SourceRectType = tuple[float, float, float, float]
"""Alias for ``tuple[float, float, float, float]`` for source rects
``(x, y, width, height)`` inside a texture."""

type PosFlatType = array.array[float] | Sequence[float]
"""Alias for a flat sequence of positions ``[x0, y0, x1, y1, ...]`` (batch submit)."""

type PosNestedType = Sequence[PosType]
"""Alias for a nested sequence of positions ``[(x0, y0), (x1, y1), ...]``."""


class Texture(Protocol):
    """Protocol for GPU texture objects.

    Objects satisfying this protocol must expose the GPU texture ID,
    dimensions, mipmap count, and internal format.
    """

    id: int
    width: int
    height: int
    mipmaps: int
    format: int


class RectangleType(Protocol):
    """Protocol for rectangle objects (x, y, width, height)."""

    x: float
    y: float
    width: float
    height: float


class NPatchInfoType(Protocol):
    """Protocol for NPatch (nine-patch) layout info."""

    source: RectangleType
    left: int
    top: int
    right: int
    bottom: int
    layout: int


class FontType(Protocol):
    """Protocol for font objects (glyph atlas + metrics)."""

    baseSize: int
    glyphCount: int
    glyphPadding: int
    texture: Texture
    recs: Any
    glyphs: Any


class PrColor(Protocol):
    """Protocol for 4-component R8G8B8A8 (32-bit) colors."""

    r: int
    g: int
    b: int
    a: int


class Vector2Type(Protocol):
    """Protocol for 2D vectors (2 components)."""

    x: float
    y: float


class ShaderType(Protocol):
    """Protocol for GPU shaders."""

    id: int
    locs: Any


class RenderTexture(Protocol):
    """Protocol for RenderTexture (FBO for render-to-texture)."""

    id: int
    texture: Texture
    depth: Texture
