"""Opt-in spatial index service (does not replace frustum cull or physics)."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils.data_structures.spatial_hash import SpatialHash

if TYPE_CHECKING:
    from plyunit.core.units.node_unit import NodeUnit
    from plyunit.core.units.scene_unit import SceneUnit


class SpatialIndexStats:
    """Opt-in counters for the incremental path. Only allocated when
    ``SpatialIndex(stats_enabled=True)``. Zero cost when absent."""

    __slots__ = ("last_dirty_count", "last_full_count", "last_update_ms")

    def __init__(self) -> None:
        """Initialize all counters to zero."""
        self.last_dirty_count: int = 0
        self.last_full_count: int = 0
        self.last_update_ms: float = 0.0


class SpatialIndex(ServiceUnit):
    """Explicit-bounds spatial hash wrapper for gameplay queries.

    Opt-in via ``SpatialIndex()``. When registered,
    ``SceneUnit`` drives an **incremental** refresh after transform sync
    (PLAN §6): only nodes that moved / attached / detached are upserted, with
    a full ``refresh_scene`` rebuild still available for debug / teleport.

    Incremental sources of dirty:
      - ``TransformStore.sync()`` recomputed indices (gameplay moves)
      - ``apply_physics_state`` (dynamic bodies — flagged by
        :class:`Physics._post_step_sync`)
      - ``attach`` / ``detach`` (immediate upsert / remove)
      - ``EntityPool.release`` (already calls ``remove``)

    Set ``stats_enabled=True`` to populate ``self.stats`` counters for
    measurement. Leave it off in shipping builds.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        cell_size: float = 64.0,
        tags: set[str] | None = None,
        stats_enabled: bool = False,
    ) -> None:
        """Initialize the spatial index service.

        Args:
            name: Service name; defaults to ``"SpatialIndex"``.
            cell_size: Hash grid cell size in world units.
            tags: Optional tags passed to the ServiceUnit registry.
            stats_enabled: Populate ``self.stats`` counters for measurement.
        """
        super().__init__(name or "SpatialIndex", tags=tags)
        self._hash: SpatialHash[Any] = SpatialHash(cell_size=cell_size)
        # id(node) set of nodes currently inserted into the hash.
        self._attached: set[int] = set()
        # id(node) set of nodes pending an upsert on the next flush_dirty().
        self._dirty: set[int] = set()
        # id(node) -> NodeUnit, so flush_dirty can resolve back-references
        # without relying on SpatialHash internals.
        self._nodes_by_id: dict[int, NodeUnit] = {}
        # True once a full refresh_scene has populated the index for the
        # current scene; SceneUnit bootstraps once then goes incremental.
        self._bootstrapped: bool = False
        self.stats: SpatialIndexStats | None = (
            SpatialIndexStats() if stats_enabled else None
        )

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def set_bounds(
        self,
        key: Any,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> None:
        """Set the bounds of a key (low-level alternative to ``attach``).

        Args:
            key: Key object (usually a ``NodeUnit``).
            min_x, min_y: Top-left corner.
            max_x, max_y: Bottom-right corner.
        """
        self._hash.insert(key, min_x, min_y, max_x, max_y)
        self._attached.add(id(key))
        if isinstance(key, object):
            self._nodes_by_id[id(key)] = key  # type: ignore[assignment]

    def attach(self, node: NodeUnit) -> None:
        """Insert a freshly-attached node (idempotent)."""
        iid = id(node)
        if iid in self._attached:
            self._dirty.discard(iid)
            self._upsert(node)
            return
        self._upsert(node)
        self._attached.add(iid)
        self._nodes_by_id[iid] = node

    def detach(self, node: NodeUnit) -> None:
        """Remove a detached node (silent if absent)."""
        iid = id(node)
        self._hash.remove(node)
        self._attached.discard(iid)
        self._dirty.discard(iid)
        self._nodes_by_id.pop(iid, None)

    def remove(self, key: Any) -> None:
        """Back-compat alias for :meth:`detach`."""
        self._hash.remove(key)
        iid = id(key)
        self._attached.discard(iid)
        self._dirty.discard(iid)
        self._nodes_by_id.pop(iid, None)

    def mark_dirty(self, node: NodeUnit) -> None:
        """Queue an upsert for ``node`` on the next ``flush_dirty()``.

        No-op if the node is not currently attached (e.g. mid-flush attach
        before ``attach`` ran). The ``attach`` path handles initial insert.
        """
        if id(node) in self._attached:
            self._dirty.add(id(node))

    def mark_dirty_many(self, nodes: Iterable[NodeUnit]) -> None:
        """Queue upserts for multiple nodes on the next ``flush_dirty()``.

        Args:
            nodes: Nodes to mark dirty; non-attached nodes are skipped.
        """
        for n in nodes:
            if id(n) in self._attached:
                self._dirty.add(id(n))

    def flush_dirty(self) -> int:
        """Upsert bounds for every node queued via ``mark_dirty``.

        Returns the number of nodes re-inserted. No-op when the dirty set is
        empty. Idempotent: the SpatialHash already removes-then-inserts on
        duplicate keys, so calling this twice with the same dirty set is safe.
        """
        if not self._dirty:
            return 0
        start = time.perf_counter() if self.stats is not None else 0.0
        ids = self._dirty
        self._dirty = set()
        count = 0
        for iid in ids:
            node = self._nodes_by_id.get(iid)
            if node is None:
                continue
            self._upsert(node)
            count += 1
        if self.stats is not None:
            self.stats.last_dirty_count = count
            self.stats.last_update_ms = (time.perf_counter() - start) * 1000.0
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query_aabb(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> list[Any]:
        """Return all keys whose bounds overlap the query AABB.

        Args:
            min_x, min_y: Top-left corner of the AABB.
            max_x, max_y: Bottom-right corner of the AABB.

        Returns:
            list[Any]: Keys whose AABBs overlap (deduplicated).
        """
        return self._hash.query(min_x, min_y, max_x, max_y)

    # ------------------------------------------------------------------
    # Full rebuild (debug / teleport)
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all entries and reset the bootstrap flag."""
        self._hash.clear()
        self._attached.clear()
        self._dirty.clear()
        self._nodes_by_id.clear()
        self._bootstrapped = False

    def refresh_scene(self, scene: SceneUnit) -> None:
        """Clear and rebuild bounds for every in-scene node after transform sync.

        Full rebuild path — use for debug overlay, teleport-all, or when the
        incremental dirty set may be inconsistent. The default SceneUnit path
        is incremental (``mark_dirty_many`` + ``flush_dirty``); SceneUnit calls
        this once on first encounter to bootstrap the index (inserting the
        scene root + pre-existing nodes that were never individually
        ``attach``-ed).
        """
        start = time.perf_counter() if self.stats is not None else 0.0
        self._hash.clear()
        self._attached.clear()
        self._dirty.clear()
        self._nodes_by_id.clear()
        root = scene.root
        if root is None:
            self._bootstrapped = True
            return
        count = 0
        for node in root.traverse_preorder():
            self._upsert(node)
            iid = id(node)
            self._attached.add(iid)
            self._nodes_by_id[iid] = node
            count += 1
        self._bootstrapped = True
        if self.stats is not None:
            self.stats.last_full_count = count
            self.stats.last_update_ms = (time.perf_counter() - start) * 1000.0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _upsert(self, node: NodeUnit) -> None:
        """Reinsert ``node`` using its render bounds or a degenerate point AABB."""
        bounds = node.get_render_bounds()
        if bounds is None:
            pos = node.transform.world.position
            x = float(pos[0])
            y = float(pos[1])
            # Degenerate point AABB (xywh → min/max).
            self._hash.insert(node, x, y, x, y)
            return
        # get_render_bounds is (x, y, w, h) world-space.
        x, y, w, h = (
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        )
        self._hash.insert(node, x, y, x + w, y + h)

    @property
    def count(self) -> int:
        """Number of keys currently tracked."""
        return len(self._attached)
