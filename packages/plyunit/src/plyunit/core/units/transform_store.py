"""TransformStore: per-scene SoA storage for hierarchical 2D transforms."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from plyunit.core.units.node_unit import NodeUnit

_NONE = -1
"""Sentinel index meaning "no node" in the SoA link arrays."""

_INITIAL_CAPACITY = 64
"""Default initial slot capacity of a TransformStore."""

_SOA_SCALAR = (
    "_local_x",
    "_local_y",
    "_local_rot",
    "_local_sx",
    "_local_sy",
    "_world_x",
    "_world_y",
    "_world_rot",
    "_world_sx",
    "_world_sy",
    "_parent",
    "_first_child",
    "_next_sibling",
    "_dirty",
    "_fresh",
)
"""Per-slot fields copied one-by-one when relocating a slot."""


class TransformStore:
    """Per-SceneUnit numpy SoA for local/world transforms and hierarchy links.

    Topo invariant: parent index < child index. Sync scans linearly by index.
    Live slots are dense in ``[0, _count)`` via swap-with-last unbind.
    """

    __slots__ = (
        "_capacity",
        "_count",
        "_dirty",
        "_first_child",
        "_fresh",
        "_local_rot",
        "_local_sx",
        "_local_sy",
        "_local_x",
        "_local_y",
        "_next_sibling",
        "_nodes",
        "_parent",
        "_suppress_topo",
        "_world_rot",
        "_world_sx",
        "_world_sy",
        "_world_x",
        "_world_y",
    )

    def __init__(self, capacity: int = _INITIAL_CAPACITY) -> None:
        """Initialize an empty store with the given initial capacity.

        Args:
            capacity: Initial capacity (minimum 1).
        """
        self._capacity = max(1, capacity)
        self._count = 0
        self._nodes: list[NodeUnit | None] = [None] * self._capacity
        self._suppress_topo = False
        self._alloc_arrays(self._capacity)

    def _alloc_arrays(self, capacity: int) -> None:
        """Internal hook: allocate the SoA arrays.

        Float fields (local/world transforms) stay as numpy float64 because
        they are written back vectorized during sync. Int/bool fields
        (hierarchy links, dirty, fresh) use Python lists — all of their
        accesses are per-slot scalars, and list access is far cheaper than
        numpy scalar boxing in the hot loops (bind/mark_dirty/sync).
        """
        self._local_x = np.zeros(capacity, dtype=np.float64)
        self._local_y = np.zeros(capacity, dtype=np.float64)
        self._local_rot = np.zeros(capacity, dtype=np.float64)
        self._local_sx = np.ones(capacity, dtype=np.float64)
        self._local_sy = np.ones(capacity, dtype=np.float64)
        self._world_x = np.zeros(capacity, dtype=np.float64)
        self._world_y = np.zeros(capacity, dtype=np.float64)
        self._world_rot = np.zeros(capacity, dtype=np.float64)
        self._world_sx = np.ones(capacity, dtype=np.float64)
        self._world_sy = np.ones(capacity, dtype=np.float64)
        self._parent = [_NONE] * capacity
        self._first_child = [_NONE] * capacity
        self._next_sibling = [_NONE] * capacity
        self._dirty = [True] * capacity
        self._fresh = [False] * capacity

    def _grow(self) -> None:
        """Internal hook: double the store's capacity."""
        old = self._capacity
        new_cap = old * 2
        for name in (
            "_local_x",
            "_local_y",
            "_local_rot",
            "_local_sx",
            "_local_sy",
            "_world_x",
            "_world_y",
            "_world_rot",
            "_world_sx",
            "_world_sy",
        ):
            arr = getattr(self, name)
            new = np.empty(new_cap, dtype=arr.dtype)
            new[:old] = arr
            if name.endswith(("_sx", "_sy")):
                new[old:] = 1.0
            else:
                new[old:] = 0.0
            setattr(self, name, new)
        self._parent.extend([_NONE] * old)
        self._first_child.extend([_NONE] * old)
        self._next_sibling.extend([_NONE] * old)
        self._dirty.extend([True] * old)
        self._fresh.extend([False] * old)
        self._nodes.extend([None] * old)
        self._capacity = new_cap

    def _allocate_index(self) -> int:
        """Internal hook: allocate a new slot and return its index.

        Returns:
            int: The new slot's index.
        """
        if self._count >= self._capacity:
            self._grow()
        index = self._count
        self._count += 1
        return index

    def bind(self, node: NodeUnit) -> int:
        """Allocate a slot, copy local from TransformState, link hierarchy."""
        if node._transform_store is self and node._transform_index >= 0:
            return node._transform_index

        index = self._allocate_index()
        self._nodes[index] = node
        node._transform_index = index
        node._transform_store = self
        node.transform.bind_store(self, index)

        local = node.transform.local
        self._local_x[index] = local.position[0]
        self._local_y[index] = local.position[1]
        self._local_rot[index] = local.rotation
        self._local_sx[index] = local.scale[0]
        self._local_sy[index] = local.scale[1]
        self._world_x[index] = node.transform.world.position[0]
        self._world_y[index] = node.transform.world.position[1]
        self._world_rot[index] = node.transform.world.rotation
        self._world_sx[index] = node.transform.world.scale[0]
        self._world_sy[index] = node.transform.world.scale[1]
        self._dirty[index] = True
        self._fresh[index] = True
        self._first_child[index] = _NONE
        self._next_sibling[index] = _NONE
        self._parent[index] = _NONE

        parent = node.parent
        if (
            parent is not None
            and parent._transform_store is self
            and parent._transform_index >= 0
        ):
            self._link_child(parent._transform_index, index)
            if parent._transform_index >= index:
                self._ensure_topo(index)

        return index

    def unbind(self, node: NodeUnit) -> None:
        """Swap-with-last free; keep live slots dense in ``[0, _count)``."""
        index = node._transform_index
        if index < 0 or node._transform_store is not self:
            return

        parent_idx = int(self._parent[index])
        if parent_idx != _NONE:
            self._unlink_child(parent_idx, index)

        child = int(self._first_child[index])
        while child != _NONE:
            nxt = int(self._next_sibling[child])
            self._parent[child] = _NONE
            self._next_sibling[child] = _NONE
            child = nxt
        self._first_child[index] = _NONE

        node.transform.unbind_store()
        node._transform_index = -1
        node._transform_store = None
        self._nodes[index] = None
        self._parent[index] = _NONE
        self._next_sibling[index] = _NONE

        last = self._count - 1
        # Decrement BEFORE the cascade: _ensure_topo can trigger nested
        # unbinds that each compute ``last`` from _count. Without the early
        # decrement, a nested unbind relocates from the already-emptied
        # ``last`` slot (destination slot corruption — a latent bug, exposed
        # by a random-tree teardown stress test).
        self._count -= 1
        if index != last:
            self._relocate_slot(last, index)
            if self._nodes[index] is not None:
                self._ensure_topo(index)
        self._clear_slot(last)

    def reparent(self, node: NodeUnit, new_parent: NodeUnit | None) -> None:
        """Update parent links and restore parent_index < child topo."""
        index = node._transform_index
        if index < 0 or node._transform_store is not self:
            return

        old_parent = int(self._parent[index])
        if old_parent != _NONE:
            self._unlink_child(old_parent, index)

        self._parent[index] = _NONE
        self._next_sibling[index] = _NONE

        if (
            new_parent is not None
            and new_parent._transform_store is self
            and new_parent._transform_index >= 0
        ):
            pidx = new_parent._transform_index
            self._link_child(pidx, index)
            if pidx >= index:
                self._ensure_topo(index)

        self.mark_dirty_subtree(index)

    def _link_child(self, parent_idx: int, child_idx: int) -> None:
        """Internal hook: link ``child_idx`` as the first child of ``parent_idx``."""
        self._parent[child_idx] = parent_idx
        self._next_sibling[child_idx] = self._first_child[parent_idx]
        self._first_child[parent_idx] = child_idx

    def _unlink_child(self, parent_idx: int, child_idx: int) -> None:
        """Internal hook: unlink ``child_idx`` from ``parent_idx``'s child list."""
        prev = _NONE
        cur = int(self._first_child[parent_idx])
        while cur != _NONE:
            nxt = int(self._next_sibling[cur])
            if cur == child_idx:
                if prev == _NONE:
                    self._first_child[parent_idx] = nxt
                else:
                    self._next_sibling[prev] = nxt
                self._next_sibling[child_idx] = _NONE
                self._parent[child_idx] = _NONE
                return
            prev = cur
            cur = nxt

    def _relocate_slot(self, src: int, dst: int) -> None:
        """Move live slot ``src`` into ``dst`` and rewrite hierarchy refs.

        Rewrites O(degree) references — the children + sibling chain of
        ``src`` (previously an O(count) full scan per unbind, O(n²) during
        large-scene teardown).
        """
        if src == dst:
            return
        for name in _SOA_SCALAR:
            arr = getattr(self, name)
            arr[dst] = arr[src]
        node = self._nodes[src]
        self._nodes[dst] = node
        if node is not None:
            node._transform_index = dst
            node.transform._store_index = dst
        self._nodes[src] = None

        # src's children now point to dst.
        child = self._first_child[dst]
        while child != _NONE:
            self._parent[child] = dst
            child = self._next_sibling[child]

        # The parent's child-list link to src (first_child or the previous
        # sibling's next_sibling) now points to dst.
        parent = self._parent[dst]
        if parent != _NONE:
            if self._first_child[parent] == src:
                self._first_child[parent] = dst
            else:
                cur = self._first_child[parent]
                while cur != _NONE and self._next_sibling[cur] != src:
                    cur = self._next_sibling[cur]
                if cur != _NONE:
                    self._next_sibling[cur] = dst

    def _collect_subtree(self, root_idx: int) -> list[int]:
        """Internal hook: collect every index in ``root_idx``'s subtree (preorder)."""
        order: list[int] = []
        stack = [root_idx]
        while stack:
            cur = stack.pop()
            order.append(cur)
            kids: list[int] = []
            child = int(self._first_child[cur])
            while child != _NONE:
                kids.append(child)
                child = int(self._next_sibling[child])
            for k in reversed(kids):
                stack.append(k)
        return order

    def begin_suppress_topo(self) -> None:
        """Temporarily disable topology (parent < child) maintenance.

        Used for bulk teardown (scene unload): the store is discarded after
        the teardown, and every subtree reassignment during the unbind
        cascade is wasted work that cascades without bound (unbind →
        reassign → unbind …) on large scenes.

        Do NOT use for partial destroys — the topo invariant must hold
        before the next ``sync()``.
        """
        self._suppress_topo = True

    def end_suppress_topo(self) -> None:
        """Re-enable topology maintenance (pair of begin_*)."""
        self._suppress_topo = False

    def _ensure_topo(self, node_idx: int) -> None:
        """If parent index >= node, reassign subtree to high indices."""
        if self._suppress_topo:
            return
        parent_idx = int(self._parent[node_idx])
        if parent_idx == _NONE or parent_idx < node_idx:
            return
        self._reassign_subtree_high(node_idx)

    def _reassign_subtree_high(self, root_idx: int) -> None:
        """Move a subtree to dense high indices so ``parent_index < child``.

        Unbinds by node reference (swap-with-last shifts indices), then
        rebinds in preorder so parent slots are allocated before children.
        """
        order = self._collect_subtree(root_idx)
        if not order:
            return

        snapshots = [self._snapshot_slot(i) for i in order]
        nodes = [snap["node"] for snap in snapshots]
        if not any(n is not None for n in nodes):
            return

        # Children first so parent unbind does not orphan mid-store links oddly.
        for node in reversed(nodes):
            if node is not None and node._transform_store is self:
                self.unbind(node)

        for node, snap in zip(nodes, snapshots, strict=True):
            if node is None:
                continue
            ts = node.transform
            ts.local.position = (snap["local_x"], snap["local_y"])
            ts.local.rotation = snap["local_rot"]
            ts.local.scale = (snap["local_sx"], snap["local_sy"])
            ts.world.position = (snap["world_x"], snap["world_y"])
            ts.world.rotation = snap["world_rot"]
            ts.world.scale = (snap["world_sx"], snap["world_sy"])
            self.bind(node)
            idx = node._transform_index
            if idx >= 0:
                self._dirty[idx] = True
                ts.dirty = True

    def _snapshot_slot(self, index: int) -> dict:
        """Internal hook: snapshot the contents of slot ``index`` into a dict."""
        return {
            "node": self._nodes[index],
            "local_x": float(self._local_x[index]),
            "local_y": float(self._local_y[index]),
            "local_rot": float(self._local_rot[index]),
            "local_sx": float(self._local_sx[index]),
            "local_sy": float(self._local_sy[index]),
            "world_x": float(self._world_x[index]),
            "world_y": float(self._world_y[index]),
            "world_rot": float(self._world_rot[index]),
            "world_sx": float(self._world_sx[index]),
            "world_sy": float(self._world_sy[index]),
            "dirty": bool(self._dirty[index]),
        }

    def _clear_slot(self, index: int) -> None:
        """Internal hook: empty slot ``index`` (all fields back to defaults)."""
        self._nodes[index] = None
        self._parent[index] = _NONE
        self._first_child[index] = _NONE
        self._next_sibling[index] = _NONE
        self._dirty[index] = False
        self._fresh[index] = False

    def _restore_slot(self, index: int, snap: dict) -> None:
        """Internal hook: restore the contents of slot ``index`` from snapshot
        ``snap``."""
        self._nodes[index] = snap["node"]
        self._local_x[index] = snap["local_x"]
        self._local_y[index] = snap["local_y"]
        self._local_rot[index] = snap["local_rot"]
        self._local_sx[index] = snap["local_sx"]
        self._local_sy[index] = snap["local_sy"]
        self._world_x[index] = snap["world_x"]
        self._world_y[index] = snap["world_y"]
        self._world_rot[index] = snap["world_rot"]
        self._world_sx[index] = snap["world_sx"]
        self._world_sy[index] = snap["world_sy"]
        self._dirty[index] = snap["dirty"]

    def write_local(
        self,
        index: int,
        *,
        x: float | None = None,
        y: float | None = None,
        rot: float | None = None,
        sx: float | None = None,
        sy: float | None = None,
    ) -> None:
        """Rewrite local transform fields for slot ``index`` and mark the node
        dirty.

        Args:
            index: Slot index.
            x: New X position (``None`` = unchanged).
            y: New Y position (``None`` = unchanged).
            rot: New rotation (``None`` = unchanged).
            sx: New X scale (``None`` = unchanged).
            sy: New Y scale (``None`` = unchanged).
        """
        if index < 0:
            return
        if x is not None:
            self._local_x[index] = x
        if y is not None:
            self._local_y[index] = y
        if rot is not None:
            self._local_rot[index] = rot
        if sx is not None:
            self._local_sx[index] = sx
        if sy is not None:
            self._local_sy[index] = sy
        # Mark only this node — sync() cascades the world recompute to the
        # whole subtree via ``recomputed[parent]``, so marking the subtree
        # here would be redundant (O(subtree) per set_position).
        self._dirty[index] = True
        node = self._nodes[index]
        if node is not None:
            node.transform.dirty = True

    def mark_dirty_subtree(self, index: int) -> None:
        """Mark the entire subtree of ``index`` as dirty (world recompute needed)."""
        if index < 0:
            return
        dirty = self._dirty
        nodes = self._nodes
        first_child = self._first_child
        next_sibling = self._next_sibling
        stack = [index]
        while stack:
            cur = stack.pop()
            dirty[cur] = True
            node = nodes[cur]
            if node is not None:
                node.transform.dirty = True
            child = first_child[cur]
            while child != _NONE:
                stack.append(child)
                child = next_sibling[child]

    def apply_physics_state(
        self,
        index: int,
        local_pos: tuple[float, float],
        local_rot: float,
        world_pos: tuple[float, float],
        world_rot: float,
        previous_world_pos: tuple[float, float],
        previous_world_rot: float,
        *,
        previous_world_scale: tuple[float, float] | None = None,
        world_scale: tuple[float, float] | None = None,
    ) -> None:
        """Write local+world without dirty cascade (dynamic leaf physics)."""
        if index < 0:
            return
        self._local_x[index] = local_pos[0]
        self._local_y[index] = local_pos[1]
        self._local_rot[index] = local_rot
        self._world_x[index] = world_pos[0]
        self._world_y[index] = world_pos[1]
        self._world_rot[index] = world_rot
        if world_scale is not None:
            self._world_sx[index] = world_scale[0]
            self._world_sy[index] = world_scale[1]
        self._dirty[index] = False

        node = self._nodes[index]
        if node is None:
            return
        ts = node.transform
        ts.local.position = (float(local_pos[0]), float(local_pos[1]))
        ts.local.rotation = float(local_rot)
        ts.world.position = (float(world_pos[0]), float(world_pos[1]))
        ts.world.rotation = float(world_rot)
        if world_scale is not None:
            ts.world.scale = (float(world_scale[0]), float(world_scale[1]))
        ts.previous_world.position = (
            float(previous_world_pos[0]),
            float(previous_world_pos[1]),
        )
        ts.previous_world.rotation = float(previous_world_rot)
        if previous_world_scale is not None:
            ts.previous_world.scale = (
                float(previous_world_scale[0]),
                float(previous_world_scale[1]),
            )
        else:
            ts.previous_world.scale = ts.world.scale
        ts.dirty = False

    def sync(self) -> list[int]:
        """Linear dirty scan by index (``parent < child``), mirrored into
        ``TransformState``.

        Recomputes world transforms for dirty nodes and their children,
        then copies the results into each node's ``TransformState``.

        Hot-path optimization: float fields are snapshotted into Python
        lists once per call (``tolist`` = one C loop) so the main loop is
        free of numpy scalar boxing; the world results are then written
        back into the numpy arrays vectorized at the end. Float semantics
        are identical (float64 == Python float).

        Returns:
            list[int]: The indices whose world transforms were recomputed
            in this call (dirty + children of recomputed parents). Used by
            the caller (:class:`SceneUnit`) for incremental
            :class:`SpatialIndex` upserts without a second tree walk.
        """
        count = self._count
        if count == 0:
            return []

        nodes = self._nodes
        parent = self._parent[:count]
        dirty = self._dirty[:count]
        fresh = self._fresh[:count]
        lx = self._local_x[:count].tolist()
        ly = self._local_y[:count].tolist()
        lrot = self._local_rot[:count].tolist()
        lsx = self._local_sx[:count].tolist()
        lsy = self._local_sy[:count].tolist()
        wx = self._world_x[:count].tolist()
        wy = self._world_y[:count].tolist()
        wrot = self._world_rot[:count].tolist()
        wsx = self._world_sx[:count].tolist()
        wsy = self._world_sy[:count].tolist()

        recomputed = [False] * count
        recomputed_indices: list[int] = []
        radians = math.radians
        cos = math.cos
        sin = math.sin

        for i in range(count):
            node = nodes[i]
            if node is None:
                continue
            parent_idx = parent[i]
            need = dirty[i]
            if parent_idx != _NONE and recomputed[parent_idx]:
                need = True
            ts = node.transform
            if not need:
                # Clean node: its world did not change this substep, but
                # previous_world must be aligned with world so render
                # interpolation does not use a stale old pair
                # (interpolation "floating" forever).
                ts.previous_world.set_from(ts.world)
                fresh[i] = False
                continue

            ts.previous_world.set_from(ts.world)

            ilx = lx[i]
            ily = ly[i]
            ilr = lrot[i]
            ilsx = lsx[i]
            ilsy = lsy[i]

            if parent_idx == _NONE:
                iwx = ilx
                iwy = ily
                iwr = ilr
                iwsx = ilsx
                iwsy = ilsy
            else:
                pwx = wx[parent_idx]
                pwy = wy[parent_idx]
                pwr = wrot[parent_idx]
                pwsx = wsx[parent_idx]
                pwsy = wsy[parent_idx]
                scaled_x = ilx * pwsx
                scaled_y = ily * pwsy
                rad = radians(pwr)
                cos_r = cos(rad)
                sin_r = sin(rad)
                iwx = pwx + (scaled_x * cos_r - scaled_y * sin_r)
                iwy = pwy + (scaled_x * sin_r + scaled_y * cos_r)
                iwr = pwr + ilr
                iwsx = pwsx * ilsx
                iwsy = pwsy * ilsy

            wx[i] = iwx
            wy[i] = iwy
            wrot[i] = iwr
            wsx[i] = iwsx
            wsy[i] = iwsy
            dirty[i] = False
            recomputed[i] = True
            recomputed_indices.append(i)

            ts.local.position = (ilx, ily)
            ts.local.rotation = ilr
            ts.local.scale = (ilsx, ilsy)
            ts.world.position = (iwx, iwy)
            ts.world.rotation = iwr
            ts.world.scale = (iwsx, iwsy)
            if fresh[i]:
                # Newly bound slot: the previous world is still the default
                # (0, 0) and not a real position from the last frame. Align
                # previous_world with the new world so freshly spawned nodes
                # are not interpolated from the origin (a one-frame
                # "teleport" effect).
                ts.previous_world.set_from(ts.world)
                fresh[i] = False
            ts.dirty = False

        # Vectorized write-back: Python list -> numpy array (one C call
        # per field, not a scalar write per iteration).
        self._world_x[:count] = wx
        self._world_y[:count] = wy
        self._world_rot[:count] = wrot
        self._world_sx[:count] = wsx
        self._world_sy[:count] = wsy
        self._dirty[:count] = dirty
        self._fresh[:count] = fresh
        return recomputed_indices

    @property
    def count(self) -> int:
        """Number of live slots (dense ``[0, _count)``)."""
        return self._count
