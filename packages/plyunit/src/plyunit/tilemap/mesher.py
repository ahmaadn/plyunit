"""Tilemap Greedy Mesher — an algorithm for merging adjacent tiles.

Optimizes tilemap physics collision by turning a 2D grid of small
blocks (tiles) into a much smaller set of large rectangles (AABBs).
"""

from collections.abc import Callable, Hashable
from typing import Any


def generate_merged_rectangles(
    grid: list[list[int]],
    tile_size: float = 32.0,
    is_solid: Callable[[int], bool] = lambda v: v > 0,
) -> list[tuple[float, float, float, float]]:
    """Turns a 2D grid of tile indices into a set of merged rectangles (AABBs).

    Applies the 2D Greedy Meshing algorithm. Cells passing ``is_solid``
    are greedily merged into the largest possible rectangle (horizontal
    expansion first, then vertical).

    Args:
        grid: 2D list (row-major) of integer tile indices.
        tile_size: Pixel size of one tile edge.
        is_solid: Predicate deciding whether an index is solid.

    Returns:
        list[tuple[float, float, float, float]]: List of tuples
        ``(world_x, world_y, width, height)``. ``world_x`` and ``world_y``
        refer to the rectangle's top-left corner.
    """
    if not grid or not grid[0]:
        return []

    rows = len(grid)
    cols = len(grid[0])

    # Tracks which cells have already been merged
    visited = [[False for _ in range(cols)] for _ in range(rows)]

    rects: list[tuple[float, float, float, float]] = []

    for y in range(rows):
        for x in range(cols):
            # Skip if already processed or not a solid tile
            if visited[y][x] or not is_solid(grid[y][x]):
                continue

            # Step 1: expand horizontally as far right as possible
            w = 1
            while x + w < cols and not visited[y][x + w] and is_solid(grid[y][x + w]):
                w += 1

            # Step 2: expand vertically as far down as possible.
            # Requirement: the entire row below with width `w`
            # must be solid & unvisited
            h = 1
            can_expand_down = True
            while y + h < rows and can_expand_down:
                # Check every tile in that horizontal segment
                for dx in range(w):
                    check_x = x + dx
                    check_y = y + h
                    if visited[check_y][check_x] or not is_solid(
                        grid[check_y][check_x]
                    ):
                        can_expand_down = False
                        break

                if can_expand_down:
                    h += 1

            # Step 3: mark this whole block area as visited
            for dy in range(h):
                for dx in range(w):
                    visited[y + dy][x + dx] = True

            # Compute world position in pixels
            # Assumption: coordinates refer to the top-left corner
            world_x = x * tile_size
            world_y = y * tile_size
            world_w = w * tile_size
            world_h = h * tile_size

            rects.append((world_x, world_y, world_w, world_h))

    return rects


def generate_merged_rectangles_grouped(
    key_grid: list[list[Hashable | None]],
    tile_size: float = 32.0,
) -> list[tuple[float, float, float, float, Any]]:
    """Greedily merges adjacent cells that share an identical (non-None) key.

    Equivalent to :func:`generate_merged_rectangles`, but merging only
    happens between cells with the same key. Cells with value ``None``
    are skipped — used for tiles with shapes that must not be flattened
    (polygons/circles/non-full boxes).

    Args:
        key_grid: 2D grid (row-major) with one key per cell. ``None``
            means skip that cell.
        tile_size: Pixel size of one tile edge.

    Returns:
        list[tuple[float, float, float, float, Any]]: List of tuples
        ``(world_x, world_y, width, height, key)``. ``world_x`` and
        ``world_y`` refer to the rectangle's top-left corner;
        ``width``/``height`` are in pixels.
    """
    if not key_grid or not key_grid[0]:
        return []

    rows = len(key_grid)
    cols = len(key_grid[0])
    visited: list[list[bool]] = [[False] * cols for _ in range(rows)]
    rects: list[tuple[float, float, float, float, Any]] = []

    for y in range(rows):
        for x in range(cols):
            if visited[y][x]:
                continue
            key = key_grid[y][x]
            if key is None:
                continue

            w = 1
            while x + w < cols and not visited[y][x + w] and key_grid[y][x + w] == key:
                w += 1

            h = 1
            can_expand_down = True
            while y + h < rows and can_expand_down:
                for dx in range(w):
                    cx = x + dx
                    cy = y + h
                    if visited[cy][cx] or key_grid[cy][cx] != key:
                        can_expand_down = False
                        break
                if can_expand_down:
                    h += 1

            for dy in range(h):
                for dx in range(w):
                    visited[y + dy][x + dx] = True

            rects.append(
                (
                    x * tile_size,
                    y * tile_size,
                    w * tile_size,
                    h * tile_size,
                    key,
                )
            )

    return rects
