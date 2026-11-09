"""Rectangle helpers for textures, spritesheets and atlases.

All rectangles are ``(x, y, w, h)`` float tuples (:data:`RectType`) in pixels,
with the origin at the top-left corner.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from math import isfinite
from typing import Any

from plyunit.core.types import RectType

__all__ = ("full_rect", "iter_region_rects", "parse_rect", "shift_rect")


def full_rect(width: int, height: int) -> RectType:
    """Return the ``(0, 0, w, h)`` rect covering a whole texture.

    Args:
        width: Texture width in pixels.
        height: Texture height in pixels.

    Returns:
        ``(0.0, 0.0, float(width), float(height))``.

    Example:
        >>> full_rect(8, 4)
        (0.0, 0.0, 8.0, 4.0)
    """
    return 0.0, 0.0, float(width), float(height)


def shift_rect(rect: RectType, dx: float, dy: float) -> RectType:
    """Return ``rect`` moved by ``(dx, dy)``; its size is unchanged.

    Args:
        rect: The ``(x, y, w, h)`` rectangle to move.
        dx: Horizontal offset in pixels (positive moves right).
        dy: Vertical offset in pixels (positive moves down).

    Returns:
        A new rectangle; ``rect`` itself is not modified.

    Example:
        >>> shift_rect((4.0, 0.0, 4.0, 4.0), 10.0, 2.0)
        (14.0, 2.0, 4.0, 4.0)
    """
    return rect[0] + dx, rect[1] + dy, rect[2], rect[3]


def parse_rect(region_id: str, region_data: Any) -> RectType:
    """Parse a spritesheet rectangle into four finite pixel coordinates.

    Args:
        region_id: Region ID used in error messages.
        region_data: A list or tuple containing ``(x, y, width, height)``.

    Returns:
        The rectangle with every coordinate converted to ``float``.

    Raises:
        ValueError: If the rectangle does not contain four finite numbers.
    """
    if isinstance(region_data, Mapping):
        if "rect" not in region_data:
            raise ValueError(f"Region '{region_id}' must contain a rect")
        region_data = region_data["rect"]
    if not isinstance(region_data, (list, tuple)):
        raise ValueError(f"Region '{region_id}' rect must be a list or tuple")
    if len(region_data) != 4:
        raise ValueError(f"Region '{region_id}' must have 4 values for rect")
    try:
        x, y, width, height = (float(value) for value in region_data)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Region '{region_id}' rect must contain numbers") from error
    if not all(isfinite(value) for value in (x, y, width, height)):
        raise ValueError(f"Region '{region_id}' rect must contain finite numbers")
    return x, y, width, height


def iter_region_rects(regions: Any) -> Iterator[tuple[str, RectType]]:
    """Yield ``(region_id, rect)`` pairs from either ``regions`` form.

    This is a generator: nothing is parsed until it is iterated, so errors
    are raised during iteration, not at the call.

    Args:
        regions: Either a mapping of ``region_id`` -> rect data, or a list of
            ``{"name": ..., "rect": ...}`` entries. Rect data follows
            :func:`parse_rect`.

    Yields:
        ``(region_id, rect)`` in the order of ``regions``.

    Raises:
        ValueError: If the container, region name, or rectangle is invalid,
            or if a region name is repeated.

    Example:
        >>> list(iter_region_rects({"a": [0, 0, 4, 4], "b": [4, 0, 4, 4]}))
        [('a', (0.0, 0.0, 4.0, 4.0)), ('b', (4.0, 0.0, 4.0, 4.0))]
        >>> list(iter_region_rects([{"name": "a", "rect": [0, 0, 4, 4]}]))
        [('a', (0.0, 0.0, 4.0, 4.0))]
    """
    if isinstance(regions, Mapping):
        items = regions.items()
    elif isinstance(regions, (list, tuple)):
        for item in regions:
            if (
                not isinstance(item, Mapping)
                or "name" not in item
                or "rect" not in item
            ):
                raise ValueError("Region entries must contain 'name' and 'rect'")
        items = ((item["name"], item["rect"]) for item in regions)
    else:
        raise ValueError("Regions must be a mapping or a list of named rectangles")

    seen: set[str] = set()
    for region_id, region_data in items:
        if not isinstance(region_id, str) or not region_id.strip():
            raise ValueError("Region names must be non-empty strings")
        if region_id in seen:
            raise ValueError(f"Duplicate region name: '{region_id}'")
        seen.add(region_id)
        yield region_id, parse_rect(region_id, region_data)
