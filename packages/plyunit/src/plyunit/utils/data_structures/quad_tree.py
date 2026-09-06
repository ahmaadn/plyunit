"""Quad Tree — recursive spatial partitioning for static geometry queries.

Well suited to data that rarely changes (tiles, walls, trees) because
insert/remove require split/merge. Queries for regions and points are very fast.

Usage example:
    >>> from plyunit.utils.data_structures import QuadTree
    >>> qt = QuadTree[str](0, 0, 1000, 1000)
    >>> qt.insert("tile_0", 10, 10, 42, 42)
    True
    >>> qt.query(0, 0, 50, 50)
    ['tile_0']
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class _Entry[T]:
    """Internal entry that stores an item along with its AABB."""

    __slots__ = ("item", "max_x", "max_y", "min_x", "min_y")

    def __init__(
        self, item: T, min_x: float, min_y: float, max_x: float, max_y: float
    ) -> None:
        """Initialize the entry with an item and its AABB.

        Args:
            item: The stored object.
            min_x: Left edge of the AABB.
            min_y: Top edge of the AABB.
            max_x: Right edge of the AABB.
            max_y: Bottom edge of the AABB.
        """
        self.item = item
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y


class _Node[T]:
    """Internal quad tree node."""

    __slots__ = (
        "children",
        "depth",
        "entries",
        "max_depth",
        "max_items",
        "max_x",
        "max_y",
        "min_x",
        "min_y",
    )

    def __init__(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        depth: int,
        max_items: int,
        max_depth: int,
    ) -> None:
        """Initialize the node with bounds, depth, and capacity.

        Args:
            min_x: Left edge of the node.
            min_y: Top edge of the node.
            max_x: Right edge of the node.
            max_y: Bottom edge of the node.
            depth: Depth of the node in the tree (``0`` for the root).
            max_items: Entry capacity before subdividing.
            max_depth: Maximum depth of the tree.
        """
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.depth = depth
        self.max_items = max_items
        self.max_depth = max_depth
        self.entries: list[_Entry[T]] = []
        self.children: list[_Node[T]] | None = None

    @property
    def is_leaf(self) -> bool:
        """True when the node has not been subdivided (no children)."""
        return self.children is None

    def _subdivide(self) -> None:
        """Split the node into 4 quadrants."""
        mid_x = (self.min_x + self.max_x) * 0.5
        mid_y = (self.min_y + self.max_y) * 0.5
        d = self.depth + 1
        mi = self.max_items
        md = self.max_depth

        self.children = [
            _Node(self.min_x, self.min_y, mid_x, mid_y, d, mi, md),  # TL
            _Node(mid_x, self.min_y, self.max_x, mid_y, d, mi, md),  # TR
            _Node(self.min_x, mid_y, mid_x, self.max_y, d, mi, md),  # BL
            _Node(mid_x, mid_y, self.max_x, self.max_y, d, mi, md),  # BR
        ]

        # Redistribute entries to children
        old_entries = self.entries
        self.entries = []
        for entry in old_entries:
            placed = False
            for child in self.children:
                if _fully_contains(child, entry):
                    child.entries.append(entry)
                    placed = True
                    break
            if not placed:
                # Entry straddles quadrant boundaries — stays in the parent
                self.entries.append(entry)

    def insert(self, entry: _Entry[T]) -> bool:
        """Insert the entry into this node or the appropriate child."""
        # Check whether the entry AABB overlaps this node
        if not _overlaps_node(self, entry):
            return False

        # If leaf and not full yet, store directly
        if self.is_leaf:
            self.entries.append(entry)
            # Subdivide if capacity is exceeded and max depth not reached
            if len(self.entries) > self.max_items and self.depth < self.max_depth:
                self._subdivide()
            return True

        # Already subdivided: try to insert into a child
        assert self.children is not None
        for child in self.children:
            if _fully_contains(child, entry):
                return child.insert(entry)

        # Entry straddles boundaries — store it in this node
        self.entries.append(entry)
        return True

    def remove(self, item: T) -> bool:
        """Remove the item from this node or its children. Returns True if found."""
        # Check entries in this node
        for i, entry in enumerate(self.entries):
            if entry.item is item:
                self.entries.pop(i)
                return True

        # Check children
        if self.children is not None:
            for child in self.children:
                if child.remove(item):
                    # Try merging children back into a leaf
                    self._try_merge()
                    return True
        return False

    def _try_merge(self) -> None:
        """Merge children back into a leaf if the total item count is small enough."""
        if self.children is None:
            return
        total = len(self.entries)
        for child in self.children:
            if child.children is not None:
                return  # Has grandchildren, cannot merge
            total += len(child.entries)

        if total <= self.max_items:
            for child in self.children:
                self.entries.extend(child.entries)
            self.children = None

    def query(
        self,
        qmin_x: float,
        qmin_y: float,
        qmax_x: float,
        qmax_y: float,
        result: list[T],
    ) -> None:
        """Collect items overlapping the AABB region into ``result``.

        Args:
            qmin_x, qmin_y: Top-left corner of the region.
            qmax_x, qmax_y: Bottom-right corner of the region.
            result: Output list to append to.
        """
        # Check overlap with this node
        if (
            qmax_x < self.min_x
            or qmin_x > self.max_x
            or qmax_y < self.min_y
            or qmin_y > self.max_y
        ):
            return  # No overlap

        # Check entries in this node
        for entry in self.entries:
            if (
                entry.max_x >= qmin_x
                and entry.min_x <= qmax_x
                and entry.max_y >= qmin_y
                and entry.min_y <= qmax_y
            ):
                result.append(entry.item)

        # Check children
        if self.children is not None:
            for child in self.children:
                child.query(qmin_x, qmin_y, qmax_x, qmax_y, result)

    def query_point(self, x: float, y: float, result: list[T]) -> None:
        """Collect items containing the point ``(x, y)`` into ``result``.

        Args:
            x: X coordinate of the point.
            y: Y coordinate of the point.
            result: Output list to append to.
        """
        if x < self.min_x or x > self.max_x or y < self.min_y or y > self.max_y:
            return

        for entry in self.entries:
            if (
                x >= entry.min_x
                and x <= entry.max_x
                and y >= entry.min_y
                and y <= entry.max_y
            ):
                result.append(entry.item)

        if self.children is not None:
            for child in self.children:
                child.query_point(x, y, result)

    def all_items(self, result: list[T]) -> None:
        """Collect all items in this subtree into ``result``.

        Args:
            result: Output list to append to.
        """
        for entry in self.entries:
            result.append(entry.item)
        if self.children is not None:
            for child in self.children:
                child.all_items(result)


def _overlaps_node[T](node: _Node[T], entry: _Entry[T]) -> bool:
    """Internal: check whether the entry AABB overlaps the node bounds.

    Returns:
        bool: True if the two AABBs overlap.
    """
    return not (
        entry.max_x < node.min_x
        or entry.min_x > node.max_x
        or entry.max_y < node.min_y
        or entry.min_y > node.max_y
    )


def _fully_contains[T](node: _Node[T], entry: _Entry[T]) -> bool:
    """Internal: check whether the node fully contains the entry AABB.

    Returns:
        bool: True if the entry AABB lies entirely inside the node.
    """
    return (
        entry.min_x >= node.min_x
        and entry.max_x <= node.max_x
        and entry.min_y >= node.min_y
        and entry.max_y <= node.max_y
    )


class QuadTree[T]:
    """Quad tree spatial partitioning for static geometry queries.

    Optimal for data that rarely changes (tiles, terrain, walls).
    Region queries are very fast: O(log n + k) where k = number of results.

    Args:
        min_x: Left edge of the world.
        min_y: Top edge of the world.
        max_x: Right edge of the world.
        max_y: Bottom edge of the world.
        max_items: Maximum number of items per node before subdividing.
        max_depth: Maximum depth of the tree.
    """

    __slots__ = ("_count", "_item_lookup", "_root")

    def __init__(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        max_items: int = 8,
        max_depth: int = 8,
    ) -> None:
        """Initialize the quad tree with world bounds and node capacity.

        Args:
            min_x: Left edge of the world.
            min_y: Top edge of the world.
            max_x: Right edge of the world.
            max_y: Bottom edge of the world.
            max_items: Entry capacity per node before subdividing.
            max_depth: Maximum depth of the tree.
        """
        self._root = _Node[T](min_x, min_y, max_x, max_y, 0, max_items, max_depth)
        self._count = 0
        # Lookup for fast remove by item identity
        self._item_lookup: dict[int, _Entry[T]] = {}

    def insert(
        self,
        item: T,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> bool:
        """Insert *item* with a bounding box into the quad tree.

        Returns:
            True on success (the AABB overlaps the world bounds),
                False if it lies outside the bounds.
        """
        item_id = id(item)
        if item_id in self._item_lookup:
            self.remove(item)

        entry = _Entry(item, min_x, min_y, max_x, max_y)
        if self._root.insert(entry):
            self._item_lookup[item_id] = entry
            self._count += 1
            return True
        return False

    def remove(self, item: T) -> bool:
        """Remove *item* from the quad tree.

        Returns:
            True if found and removed, False if absent.
        """
        item_id = id(item)
        if item_id not in self._item_lookup:
            return False

        if self._root.remove(item):
            del self._item_lookup[item_id]
            self._count -= 1
            return True
        return False

    def query(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> list[T]:
        """Return all items overlapping the AABB region.

        Args:
            min_x, min_y: Top-left corner of the region.
            max_x, max_y: Bottom-right corner of the region.

        Returns:
            list[T]: Items whose AABBs overlap the region.
        """
        result: list[T] = []
        self._root.query(min_x, min_y, max_x, max_y, result)
        return result

    def query_point(self, x: float, y: float) -> list[T]:
        """Return all items containing the point ``(x, y)``.

        Args:
            x: X coordinate of the point.
            y: Y coordinate of the point.

        Returns:
            list[T]: Items whose AABBs contain the point.
        """
        result: list[T] = []
        self._root.query_point(x, y, result)
        return result

    def clear(self) -> None:
        """Remove all items and reset the tree to an empty root node."""
        r = self._root
        self._root = _Node[T](
            r.min_x, r.min_y, r.max_x, r.max_y, 0, r.max_items, r.max_depth
        )
        self._item_lookup.clear()
        self._count = 0

    def rebuild(self) -> None:
        """Rebuild the tree from scratch. Useful after many remove operations."""
        items: list[T] = []
        self._root.all_items(items)

        # Rebuild using lookup for AABB info
        entries = list(self._item_lookup.values())
        self.clear()
        for entry in entries:
            self.insert(entry.item, entry.min_x, entry.min_y, entry.max_x, entry.max_y)

    @property
    def count(self) -> int:
        """Number of stored items."""
        return self._count

    def __len__(self) -> int:
        """Support ``len(tree)``."""
        return self._count

    def __contains__(self, item: T) -> bool:
        """Support ``item in tree`` (checks item identity)."""
        return id(item) in self._item_lookup
