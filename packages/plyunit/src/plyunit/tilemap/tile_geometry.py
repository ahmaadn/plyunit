"""Tile placement geometry: native size + bottom-left anchor point.

An image does not have to be the same size as a grid cell. Assets like
trees, poles, or 100x90 buildings still sit on a 16x16 grid, but are
**drawn at their original size** and never force-shrunk to the cell size.

The anchor point is the cell's **bottom-left corner**, not the center or
the top-left. The reason: what determines "where an object stands" is its
feet. With a bottom-left anchor, picking the same cell always yields the
same foot position no matter how tall the image is; excess height grows
**upward** and excess width grows **rightward**::

    height 90, cell 16              height 16, cell 16
    +----------+  <- y = bottom - 90
    |          |
    |  image   |
    |          |
    |          |   +----------+  <- y = bottom - 16
    +----------+   +----------+  <- y = bottom (same for both)
    ^ x = cell left

An image sized exactly one cell produces a rect identical to the old
computation ``(col * ts, row * ts, ts, ts)``, so tilesets already cut
per tile keep their appearance unchanged.

This module is the shared source of truth: the editor imports the same
functions so the editor view and the in-game result never diverge.
"""

from __future__ import annotations

__all__ = [
    "TILE_ANCHOR",
    "source_size",
    "tile_dest_rect",
    "tile_is_oversized",
    "tile_overhang",
]

TILE_ANCHOR = "bottom_left"
"""Tile placement anchor point on the grid cell."""


def source_size(
    tile_size: int,
    source_w: float,
    source_h: float,
) -> tuple[float, float]:
    """Effective image size, with a fallback to the cell size.

    The source rect may be negative (raylib's vertical-flip convention),
    so the absolute value is used. Degenerate (zero) rects fall back to
    ``tile_size`` so the tile still draws instead of disappearing.

    Args:
        tile_size: Size of one grid cell in pixels.
        source_w: Source rect width.
        source_h: Source rect height.

    Returns:
        A ``(width, height)`` tuple that is always positive.
    """
    ts = float(max(1, tile_size))
    w = abs(float(source_w))
    h = abs(float(source_h))
    return (w if w > 0.0 else ts, h if h > 0.0 else ts)


def tile_dest_rect(
    col: float,
    row: float,
    tile_size: int,
    source_w: float,
    source_h: float,
) -> tuple[float, float, float, float]:
    """Destination rect for a tile: native size, anchored at the cell's
    bottom-left corner.

    Args:
        col: Cell column (absolute grid or chunk-local coordinates both work).
        row: Cell row, with the Y axis pointing down.
        tile_size: Size of one grid cell in pixels.
        source_w: Source image width.
        source_h: Source image height.

    Returns:
        Rect ``(x, y, w, h)``. ``x`` aligns with the cell's left edge and
        ``y + h`` aligns with the cell's bottom edge.
    """
    ts = float(max(1, tile_size))
    w, h = source_size(tile_size, source_w, source_h)
    x = float(col) * ts
    bottom = (float(row) + 1.0) * ts
    return (x, bottom - h, w, h)


def tile_is_oversized(tile_size: int, source_w: float, source_h: float) -> bool:
    """True when the image exceeds one grid cell.

    Such tiles must not be baked into the per-chunk ``RenderTexture``: an
    RT is exactly one chunk in size, so image parts spilling up or right
    would be cut by the RT scissor at the chunk boundary.
    """
    w, h = source_size(tile_size, source_w, source_h)
    ts = float(max(1, tile_size))
    return w > ts or h > ts


def tile_overhang(
    tile_size: int, source_w: float, source_h: float
) -> tuple[float, float]:
    """Image overhang beyond the cell, as ``(right, up)``.

    Used to widen the culling margin so tall images do not flicker out
    of existence when their owning cell leaves the camera view.
    """
    w, h = source_size(tile_size, source_w, source_h)
    ts = float(max(1, tile_size))
    return (max(0.0, w - ts), max(0.0, h - ts))
