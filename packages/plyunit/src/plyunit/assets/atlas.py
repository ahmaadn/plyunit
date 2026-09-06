"""Shelf (row) packer for in-memory texture atlases.

This module is backend-agnostic: it only computes atlas page dimensions
and the placement of each asset. Pixel composition (image blit) remains
the backend's responsibility via
:class:`~plyunit.backends.interfaces.i_assets_loader.IAssetsLoader`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["AtlasPage", "AtlasPlacement", "pack_shelf"]


@dataclass(frozen=True, slots=True)
class AtlasPage:
    """Final dimensions of a single atlas page.

    Attributes:
        width: Page width in pixels (cropped to content).
        height: Page height in pixels (cropped to content).
    """

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class AtlasPlacement:
    """Placement of a single asset within an atlas page.

    Attributes:
        page: Atlas page index (0-based).
        x: X coordinate of the asset's top-left corner on the page.
        y: Y coordinate of the asset's top-left corner on the page.
        width: Asset width (excluding padding) in pixels.
        height: Asset height (excluding padding) in pixels.
    """

    page: int
    x: int
    y: int
    width: int
    height: int


def pack_shelf(
    entries: Sequence[tuple[str, int, int]],
    *,
    max_size: int = 2048,
    padding: int = 2,
) -> tuple[list[AtlasPage], dict[str, AtlasPlacement]]:
    """Pack a list of ``(asset_id, width, height)`` into atlas pages.

    Uses the shelf algorithm: items are sorted by height (descending),
    then placed row by row. Pages are cropped to the content extents so
    no VRAM is wasted at the edges. Assets that do not fit on one page
    flow automatically to the next page.

    Args:
        entries: The list of ``(asset_id, width, height)`` to pack.
        max_size: Maximum side of a single atlas page.
        padding: Pixel spacing between assets (prevents bleeding during
            bilinear filtering).

    Returns:
        Tuple ``(pages, placements)``: the list of page dimensions and
        the mapping of ``asset_id`` -> :class:`AtlasPlacement`.

    Raises:
        ValueError: If ``max_size``/``padding`` is invalid, or if any
            asset has invalid dimensions / is larger than ``max_size``
            (the caller must filter those out beforehand).
    """
    if max_size <= 0:
        raise ValueError(f"max_size harus > 0, dapat: {max_size}")
    if padding < 0:
        raise ValueError(f"padding tidak boleh negatif, dapat: {padding}")

    ordered = sorted(entries, key=lambda item: (-item[2], -item[1], item[0]))

    pages_shelves: list[list[dict[str, int]]] = []
    page_heights: list[int] = []
    extents: list[tuple[int, int]] = []
    placements: dict[str, AtlasPlacement] = {}

    for asset_id, width, height in ordered:
        if width <= 0 or height <= 0:
            raise ValueError(f"Dimensi aset '{asset_id}' tidak valid: {width}x{height}")
        if width > max_size or height > max_size:
            raise ValueError(
                f"Aset '{asset_id}' ({width}x{height}) tidak muat dalam "
                f"max_size={max_size}"
            )

        placement = _place(
            pages_shelves, page_heights, width, height, max_size, padding
        )
        if placement is None:
            pages_shelves.append([{"x": width + padding, "y": 0, "h": height}])
            page_heights.append(height + padding)
            extents.append((0, 0))
            placement = AtlasPlacement(
                page=len(pages_shelves) - 1, x=0, y=0, width=width, height=height
            )
        placements[asset_id] = placement

        page = placement.page
        used_w, used_h = extents[page]
        extents[page] = (
            max(used_w, placement.x + width),
            max(used_h, placement.y + height),
        )

    pages = [AtlasPage(width=w, height=h) for w, h in extents]
    return pages, placements


def _place(
    pages_shelves: list[list[dict[str, int]]],
    page_heights: list[int],
    width: int,
    height: int,
    max_size: int,
    padding: int,
) -> AtlasPlacement | None:
    """Find a slot for a single item on the existing pages.

    Tries already-formed shelves first, then opens a new shelf on a page
    that still fits vertically.

    Args:
        pages_shelves: Shelf state per page (mutated).
        page_heights: Used height per page (mutated).
        width: Item width.
        height: Item height.
        max_size: Maximum page side.
        padding: Pixel spacing between items.

    Returns:
        The item placement, or ``None`` if a new page is needed.
    """
    for page, shelves in enumerate(pages_shelves):
        for shelf in shelves:
            if shelf["h"] >= height and shelf["x"] + width <= max_size:
                placement = AtlasPlacement(
                    page=page, x=shelf["x"], y=shelf["y"], width=width, height=height
                )
                shelf["x"] += width + padding
                return placement

        next_y = page_heights[page]
        if next_y + height <= max_size:
            shelves.append({"x": width + padding, "y": next_y, "h": height})
            page_heights[page] = next_y + height + padding
            return AtlasPlacement(page=page, x=0, y=next_y, width=width, height=height)

    return None
