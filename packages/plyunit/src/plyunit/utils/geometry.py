"""Geometry utilities — AABB, intersection, frustum culling."""

from __future__ import annotations

from plyunit.core.types import RectType


def aabb_intersects(a: RectType, b: RectType) -> bool:
    """Check whether two axis-aligned bounding boxes overlap.

    Each rect is a tuple ``(x, y, width, height)``.

    Args:
        a: First rect.
        b: Second rect.

    Returns:
        bool: ``True`` if the two rects intersect, ``False`` otherwise.
    """
    return (
        a[0] < b[0] + b[2]
        and a[0] + a[2] > b[0]
        and a[1] < b[1] + b[3]
        and a[1] + a[3] > b[1]
    )


def aabb_contains(a: RectType, b: RectType) -> bool:
    """Check whether rect A fully contains rect B.

    Args:
        a: Container rect (A).
        b: Rect being tested (B).

    Returns:
        bool: ``True`` if A fully contains B, ``False`` otherwise.
    """
    return (
        a[0] <= b[0]
        and a[1] <= b[1]
        and a[0] + a[2] >= b[0] + b[2]
        and a[1] + a[3] >= b[1] + b[3]
    )


def aabb_from_center(
    cx: float, cy: float, half_w: float, half_h: float
) -> RectType:
    """Create an AABB from a center point and half-extents.

    Args:
        cx: Center X coordinate.
        cy: Center Y coordinate.
        half_w: Half width.
        half_h: Half height.

    Returns:
        RectType: Tuple ``(x, y, width, height)``.
    """
    return (cx - half_w, cy - half_h, half_w * 2, half_h * 2)


def aabb_intersection(a: RectType, b: RectType) -> RectType:
    """Compute the intersection of two AABBs.

    Args:
        a: First rect.
        b: Second rect.

    Returns:
        RectType: Tuple ``(x, y, w, h)`` of the intersection. ``w``/``h``
            are ``0`` if there is no overlap.
    """
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))


def aabb_union(a: RectType, b: RectType) -> RectType:
    """Compute the union of two AABBs.

    Args:
        a: First rect.
        b: Second rect.

    Returns:
        RectType: The smallest AABB covering both ``a`` and ``b``.
    """
    x1 = min(a[0], b[0])
    y1 = min(a[1], b[1])
    x2 = max(a[0] + a[2], b[0] + b[2])
    y2 = max(a[1] + a[3], b[1] + b[3])
    return (x1, y1, x2 - x1, y2 - y1)


def expand_aabb(rect: RectType, margin: float) -> RectType:
    """Expand an AABB by a uniform margin on all sides.

    Args:
        rect: Source rect ``(x, y, w, h)``.
        margin: Pixel margin added to each side.

    Returns:
        RectType: The expanded rect.
    """
    return (
        rect[0] - margin,
        rect[1] - margin,
        rect[2] + margin * 2,
        rect[3] + margin * 2,
    )
