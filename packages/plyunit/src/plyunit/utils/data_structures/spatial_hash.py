"""Spatial Hash — grid-based spatial partitioning for fast neighbor queries.

Well suited to dynamic entities that move often: insert/update/remove are
O(1) amortized, query is O(k) where k = number of items in overlapping cells.

Usage example:
    >>> sh = SpatialHash[str](cell_size=64.0)
    >>> sh.insert("enemy_1", 100.0, 100.0, 132.0, 132.0)
    >>> sh.query(90.0, 90.0, 200.0, 200.0)
    ['enemy_1']
"""

from __future__ import annotations

import math
from typing import TypeVar

T = TypeVar("T")


class SpatialHash[T]:
    """Grid-based spatial partitioning for fast neighbor queries.

    Each item is stored in every cell that overlaps its AABB.
    Cell keys are (col, row) tuples derived from ``cell_size``.

    Args:
        cell_size: Cell side length (pixels/units). Larger means fewer cells
            but more items per cell. Rule of thumb: 2-4x the size of an
            average entity.
    """

    __slots__ = ("_cells", "_inv_cell_size", "_item_cells", "cell_size")

    def __init__(self, cell_size: float = 64.0) -> None:
        """Initialize an empty spatial hash with the given cell size.

        Args:
            cell_size: Cell side length (pixels/units). Rule of thumb: 2-4x
                the size of an average entity.

        Raises:
            ValueError: If ``cell_size`` is not greater than zero.
        """
        if cell_size <= 0:
            raise ValueError("cell_size must be > 0")
        self.cell_size = float(cell_size)
        self._inv_cell_size = 1.0 / self.cell_size

        # cell key → set of items
        self._cells: dict[tuple[int, int], set[T]] = {}

        # item → set of cell keys (for fast remove/update)
        self._item_cells: dict[int, tuple[T, set[tuple[int, int]]]] = {}

    def _cell_range(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> tuple[int, int, int, int]:
        """Compute the range of cells overlapping the AABB.

        Args:
            min_x: Minimum X coordinate of the AABB.
            min_y: Minimum Y coordinate of the AABB.
            max_x: Maximum X coordinate of the AABB.
            max_y: Maximum Y coordinate of the AABB.

        Returns:
            tuple[int, int, int, int]: ``(col_min, row_min, col_max, row_max)``
            computed by floor division with ``cell_size``.
        """
        inv = self._inv_cell_size
        return (
            math.floor(min_x * inv),
            math.floor(min_y * inv),
            math.floor(max_x * inv),
            math.floor(max_y * inv),
        )

    def insert(
        self,
        item: T,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> None:
        """Insert an item with the given bounding box.

        The item is stored in every cell that overlaps its AABB. If the item
        already exists, it is removed first and then re-inserted.

        Args:
            item: The item to insert.
            min_x: Minimum X coordinate of the AABB.
            min_y: Minimum Y coordinate of the AABB.
            max_x: Maximum X coordinate of the AABB.
            max_y: Maximum Y coordinate of the AABB.

        Returns:
            None: No return value.
        """
        item_id = id(item)
        if item_id in self._item_cells:
            self.remove(item)

        col_min, row_min, col_max, row_max = self._cell_range(
            min_x, min_y, max_x, max_y
        )
        keys: set[tuple[int, int]] = set()

        for col in range(col_min, col_max + 1):
            for row in range(row_min, row_max + 1):
                key = (col, row)
                keys.add(key)
                cell = self._cells.get(key)
                if cell is None:
                    cell = set()
                    self._cells[key] = cell
                cell.add(item)

        self._item_cells[item_id] = (item, keys)

    def remove(self, item: T) -> None:
        """Remove the item from every cell it occupies.

        Does nothing if the item is not found.

        Args:
            item: The item to remove.

        Returns:
            None: No return value.
        """
        item_id = id(item)
        entry = self._item_cells.pop(item_id, None)
        if entry is None:
            return
        _, keys = entry
        for key in keys:
            cell = self._cells.get(key)
            if cell is not None:
                cell.discard(item)
                if not cell:
                    del self._cells[key]

    def update(
        self,
        item: T,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> None:
        """Update the item's position with a new AABB.

        Shortcut for ``remove(item)`` followed by ``insert(item, ...)``.

        Args:
            item: The item to update.
            min_x: Minimum X coordinate of the new AABB.
            min_y: Minimum Y coordinate of the new AABB.
            max_x: Maximum X coordinate of the new AABB.
            max_y: Maximum Y coordinate of the new AABB.

        Returns:
            None: No return value.
        """
        self.remove(item)
        self.insert(item, min_x, min_y, max_x, max_y)

    def query(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> list[T]:
        """Return all items overlapping the query AABB.

        Returns:
            Unique list of items (no duplicates).
        """
        col_min, row_min, col_max, row_max = self._cell_range(
            min_x, min_y, max_x, max_y
        )
        result_ids: set[int] = set()
        result: list[T] = []

        for col in range(col_min, col_max + 1):
            for row in range(row_min, row_max + 1):
                cell = self._cells.get((col, row))
                if cell is not None:
                    for item in cell:
                        iid = id(item)
                        if iid not in result_ids:
                            result_ids.add(iid)
                            result.append(item)
        return result

    def query_point(self, x: float, y: float) -> list[T]:
        """Return all items in the cell containing the point (x, y).

        Args:
            x: X coordinate of the point.
            y: Y coordinate of the point.

        Returns:
            list[T]: Items in the target cell. Empty list if the cell is empty.
        """
        inv = self._inv_cell_size
        key = (math.floor(x * inv), math.floor(y * inv))
        cell = self._cells.get(key)
        if cell is None:
            return []
        return list(cell)

    def clear(self) -> None:
        """Remove all items from the hash.

        Returns:
            None: No return value.
        """
        self._cells.clear()
        self._item_cells.clear()

    @property
    def count(self) -> int:
        """Number of unique stored items."""
        return len(self._item_cells)

    def __len__(self) -> int:
        """Return the number of unique stored items.

        Returns:
            int: The registered item ``count``.
        """
        return self.count

    def __contains__(self, item: T) -> bool:
        """Check whether the item is in the hash (based on ``id(item)``).

        Args:
            item: The item to check.

        Returns:
            bool: ``True`` if the item's id is registered.
        """
        return id(item) in self._item_cells
