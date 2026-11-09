"""Backend-neutral geometry, identifiers, and rendering values."""

import array
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

type ColorType = tuple[int, int, int, int]
"""RGBA color components from zero to 255."""

type Vec2Type = tuple[float, float]
"""Two-dimensional coordinates or vector components."""

type RectType = tuple[float, float, float, float]
"""Rectangle represented by ``(x, y, width, height)``."""

type PosType = Vec2Type
"""Two-dimensional position."""

type SizeType = Vec2Type
"""Width and height."""

type PosFlatType = array.array[float] | Sequence[float]
"""Flat position components ``[x0, y0, x1, y1, ...]``."""

type PosNestedType = Sequence[PosType]
"""Sequence of two-dimensional positions."""

type TextureID = str
"""Logical asset identity, independent of a backend's GPU resource name."""

type UniformValue = float | int | Sequence[float] | Sequence[int]
"""Numeric scalar or vector supplied to a shader uniform."""


@dataclass(frozen=True, slots=True)
class NPatchInfo:
    """Portable layout for resizable nine-slice or three-slice textures.

    Attributes:
        source: Source rectangle on the whole texture in pixels.
        left: Fixed left border width.
        top: Fixed top border height.
        right: Fixed right border width.
        bottom: Fixed bottom border height.
        layout: Nine-slice or vertical/horizontal three-slice layout.
    """

    source: RectType
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    layout: Literal["nine_patch", "three_patch_vertical", "three_patch_horizontal"] = (
        "nine_patch"
    )
