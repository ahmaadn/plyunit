"""Frame buffer SoA + run builder (data layer only — no GPU math).

Allocated once; reset per frame. UV is resolved at submit time. Vertex
expansion happens only in the C extension.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

# Single default capacity constant (configurable via init max_sprites).
MAX_SPRITES = 16384

_DEPTH_SORT_LAYERS: frozenset[int] = frozenset()


def set_depth_sort_layers(layers: set[int] | frozenset[int]) -> None:
    """Sets the layers that require depth sorting.

    Args:
        layers: Layer IDs whose sprites must be depth-sorted.
    """
    global _DEPTH_SORT_LAYERS
    _DEPTH_SORT_LAYERS = frozenset(x for x in layers)


def resolve_uv(
    source: tuple[float, float, float, float] | None,
    tex_w: float,
    tex_h: float,
) -> tuple[float, float, float, float]:
    """Source texels → UV. ``None`` → full (0,0,1,1)."""
    tw = float(tex_w) or 1.0
    th = float(tex_h) or 1.0
    if source is None:
        return 0.0, 0.0, 1.0, 1.0
    sx, sy, sw, sh = (
        float(source[0]),
        float(source[1]),
        float(source[2]),
        float(source[3]),
    )
    return sx / tw, sy / th, (sx + sw) / tw, (sy + sh) / th


def runs_from_ordered(tex_id: np.ndarray, count: int) -> np.ndarray:
    """Runs from an already-ordered texture array: (start, count, tex_id)."""
    if count <= 0:
        return np.empty((0, 3), dtype=np.int32)
    tex = tex_id[:count]
    if count == 1:
        return np.array([[0, 1, int(tex[0])]], dtype=np.int32)
    # Fast path: single texture run (bunny / homogen batch).
    if count >= 1 and not bool(np.any(tex != tex[0])):
        return np.array([[0, count, int(tex[0])]], dtype=np.int32)
    change = np.flatnonzero(np.diff(tex)) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [count]))
    return np.stack(
        [starts, ends - starts, tex[starts].astype(np.int32, copy=False)],
        axis=1,
    ).astype(np.int32, copy=False)


def build_runs(tex_id: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Stable sort by tex_id → (order, runs)."""
    if count <= 0:
        return np.empty(0, dtype=np.int64), np.empty((0, 3), dtype=np.int32)
    order = np.argsort(tex_id[:count], kind="stable")
    return order, runs_from_ordered(tex_id[:count][order], count)


def build_depth_runs(
    tex_id: np.ndarray,
    sort_key: np.ndarray,
    count: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sort by sort_key (stable), runs consecutive same texture."""
    if count <= 0:
        return np.empty(0, dtype=np.int64), np.empty((0, 3), dtype=np.int32)
    order = np.argsort(sort_key[:count], kind="stable")
    return order, runs_from_ordered(tex_id[:count][order], count)


def is_depth_sorted_layer(layer: int, y_sort: bool) -> bool:
    """Returns whether ``layer`` requires depth sorting.

    Args:
        layer: Layer ID to check.
        y_sort: Global y-sort flag; when ``True`` every layer is sorted.

    Returns:
        ``True`` if ``y_sort`` is set or ``layer`` is a registered
        depth-sorted layer.
    """
    return bool(y_sort) or int(layer) in _DEPTH_SORT_LAYERS


_PASS_HASH_CACHE: dict[str, int] = {}
_PASS_HASH_CACHE_LIMIT = 256


def pass_name_hash(name: str) -> int:
    """FNV-1a hash of a pass name, with a memo dict.

    Pass names are a small, stable set (``world``/``ui``/custom user
    passes); without the memo, strings would be re-hashed per sprite
    per frame.
    """
    cached = _PASS_HASH_CACHE.get(name)
    if cached is not None:
        return cached
    h = 2166136261
    for ch in name.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    h = int(h)
    if len(_PASS_HASH_CACHE) < _PASS_HASH_CACHE_LIMIT:
        _PASS_HASH_CACHE[name] = h
    return h


class FrameBuffer:
    """Preallocated SoA — written in place at submit time."""

    __slots__ = (
        "_g_origin",
        "_g_pos",
        "_g_rgba",
        "_g_rot",
        "_g_run_counts",
        "_g_run_starts",
        "_g_run_tex",
        "_g_size",
        "_g_tex",
        "_g_uv",
        "_native",
        "_native_append",
        "_on_full",
        "capacity",
        "count",
        "depth_sorted",
        "layer",
        "origin_xy",
        "pass_hash",
        "pos_xy",
        "rgba",
        "rotation_deg",
        "screen_space",
        "size_wh",
        "sort_key",
        "state_id",
        "submit_index",
        "tex_id",
        "uv_rect",
    )

    def __init__(self, capacity: int = MAX_SPRITES) -> None:
        """Allocates all SoA arrays for ``capacity`` sprites.

        Args:
            capacity: Maximum number of sprites the buffer can hold.
        """
        self.capacity = capacity
        c = self.capacity
        self.pos_xy = np.empty((c, 2), dtype=np.float32)
        self.size_wh = np.empty((c, 2), dtype=np.float32)
        self.origin_xy = np.empty((c, 2), dtype=np.float32)
        self.rotation_deg = np.empty(c, dtype=np.float32)
        self.rgba = np.empty((c, 4), dtype=np.uint8)
        self.uv_rect = np.empty((c, 4), dtype=np.float32)
        self.tex_id = np.empty(c, dtype=np.int32)
        self.sort_key = np.empty(c, dtype=np.float32)
        self.layer = np.empty(c, dtype=np.int32)
        self.state_id = np.empty(c, dtype=np.int32)
        self.pass_hash = np.empty(c, dtype=np.int32)
        self.submit_index = np.empty(c, dtype=np.int32)
        self.depth_sorted = np.empty(c, dtype=np.bool_)
        self.screen_space = np.empty(c, dtype=np.bool_)
        self.count = 0
        self._on_full: Callable[[], None] | None = None
        # Preallocated gather targets for flush (avoid per-frame alloc).
        self._g_pos = np.empty((c, 2), dtype=np.float32)
        self._g_size = np.empty((c, 2), dtype=np.float32)
        self._g_origin = np.empty((c, 2), dtype=np.float32)
        self._g_rot = np.empty(c, dtype=np.float32)
        self._g_rgba = np.empty((c, 4), dtype=np.uint8)
        self._g_uv = np.empty((c, 4), dtype=np.float32)
        self._g_tex = np.empty(c, dtype=np.int32)
        self._g_run_starts = np.empty(c, dtype=np.int32)
        self._g_run_counts = np.empty(c, dtype=np.int32)
        self._g_run_tex = np.empty(c, dtype=np.uint32)
        # C fast path (plyunit._fb_fast): writes the SoA via raw pointer.
        # Arrays are fixed-capacity (never reallocated), so views are safe
        # to hold for the buffer's lifetime. Falls back to numpy if the
        # module is absent.
        self._native = None
        self._native_append = None
        try:
            from plyunit import _fb_fast as _ext

            self._native = _ext.fb_bind_buffers(
                self.pos_xy,
                self.size_wh,
                self.origin_xy,
                self.rotation_deg,
                self.rgba,
                self.uv_rect,
                self.tex_id,
                self.sort_key,
                self.layer,
                self.state_id,
                self.pass_hash,
                self.submit_index,
                self.depth_sorted,
                self.screen_space,
                c,
            )
            self._native_append = _ext.fb_append
        except Exception:  # pragma: no cover - fallback numpy path
            self._native = None
            self._native_append = None

    def set_on_full(self, cb: Callable[[], None] | None) -> None:
        """Sets the force-flush callback fired when the buffer is full.

        Args:
            cb: Callback that uploads and draws the buffer, then resets
                the count; ``None`` disables it.
        """
        self._on_full = cb

    def reset(self) -> None:
        """Resets the sprite count to zero without freeing storage."""
        self.count = 0

    def remaining(self) -> int:
        """Returns the number of free sprite slots left."""
        return self.capacity - self.count

    def _ensure_space(self, need: int = 1) -> None:
        """Ensures room for ``need`` more sprites, flushing if full.

        Args:
            need: Number of additional sprite slots required.

        Raises:
            RuntimeError: If the force-flush callback did not free
                enough space.
        """
        if self.count + need <= self.capacity:
            return
        if self._on_full is not None and self.count > 0:
            self._on_full()
        if self.count + need > self.capacity:
            raise RuntimeError(
                f"FrameBuffer full ({self.capacity}); force-flush did not free space"
            )

    def append(
        self,
        *,
        pos: tuple[float, float],
        size: tuple[float, float],
        origin: tuple[float, float],
        rotation: float,
        rgba: tuple[int, int, int, int],
        uv: tuple[float, float, float, float],
        tex_id: int,
        sort_key: float,
        layer: int,
        state_id: int,
        pass_hash: int,
        submit_index: int,
        depth_sorted: bool,
        screen_space: bool,
    ) -> int:
        """Appends a single sprite's SoA fields.

        Uses the C fast path when available, otherwise numpy.

        Args:
            pos: Sprite position ``(x, y)``.
            size: Sprite size ``(w, h)``.
            origin: Rotation origin ``(x, y)``.
            rotation: Rotation in degrees.
            rgba: Tint color ``(r, g, b, a)``.
            uv: UV rect ``(u0, v0, u1, v1)``.
            tex_id: Texture slot index.
            sort_key: Depth sort key.
            layer: Layer ID.
            state_id: Render state slot index.
            pass_hash: Hashed pass name.
            submit_index: Submission order index.
            depth_sorted: Whether this sprite participates in depth sort.
            screen_space: Whether this sprite renders in screen space.

        Returns:
            The index the sprite was written to.

        Raises:
            RuntimeError: If the buffer is still full after force-flush.
        """
        self._ensure_space(1)
        i = self.count
        native_append = self._native_append
        if native_append is not None:
            # C fast path — a single FASTCALL writes all 14 SoA fields via
            # raw pointer (vs ~17 numpy __setitem__, ~3-4us per sprite).
            native_append(
                self._native,
                i,
                pos[0],
                pos[1],
                size[0],
                size[1],
                origin[0],
                origin[1],
                rotation,
                rgba[0],
                rgba[1],
                rgba[2],
                rgba[3],
                uv[0],
                uv[1],
                uv[2],
                uv[3],
                tex_id,
                sort_key,
                layer,
                state_id,
                pass_hash,
                submit_index,
                depth_sorted,
                screen_space,
            )
            self.count = i + 1
            return i

        # Numpy fallback. Per-field strategy from microbenchmarks: scalars
        # for 2-element fields (pos/size/origin), row-tuples for 4-element
        # fields (rgba/uv).
        self.pos_xy[i, 0] = pos[0]
        self.pos_xy[i, 1] = pos[1]
        self.size_wh[i, 0] = size[0]
        self.size_wh[i, 1] = size[1]
        self.origin_xy[i, 0] = origin[0]
        self.origin_xy[i, 1] = origin[1]
        self.rotation_deg[i] = rotation
        self.rgba[i] = rgba
        self.uv_rect[i] = uv
        self.tex_id[i] = tex_id
        self.sort_key[i] = sort_key
        self.layer[i] = layer
        self.state_id[i] = state_id
        self.pass_hash[i] = pass_hash
        self.submit_index[i] = submit_index
        self.depth_sorted[i] = depth_sorted
        self.screen_space[i] = screen_space
        self.count = i + 1
        return i

    def append_batch(
        self,
        *,
        pos_xy: np.ndarray,
        size_wh: np.ndarray | tuple[float, float],
        origin_xy: tuple[float, float],
        rotation: float,
        rgba: tuple[int, int, int, int],
        uv: tuple[float, float, float, float],
        tex_id: int,
        sort_key: float,
        layer: int,
        state_id: int,
        pass_hash: int,
        submit_index_start: int,
        depth_sorted: bool,
        screen_space: bool,
    ) -> int:
        """Appends many sprites at once, flushing when the buffer fills.

        Args:
            pos_xy: ``(N, 2)`` array of sprite positions.
            size_wh: Per-sprite ``(N, 2)`` array or one shared ``(w, h)``.
            origin_xy: Shared rotation origin ``(x, y)``.
            rotation: Shared rotation in degrees.
            rgba: Shared tint color ``(r, g, b, a)``.
            uv: Shared UV rect ``(u0, v0, u1, v1)``.
            tex_id: Texture slot index.
            sort_key: Shared depth sort key.
            layer: Layer ID.
            state_id: Render state slot index.
            pass_hash: Hashed pass name.
            submit_index_start: First submission order index.
            depth_sorted: Whether these sprites participate in depth sort.
            screen_space: Whether these sprites render in screen space.

        Returns:
            The number of sprites written.
        """
        arr = np.ascontiguousarray(pos_xy, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 2)
        n_total = int(arr.shape[0])
        if n_total <= 0:
            return 0
        written = 0
        offset = 0
        while offset < n_total:
            space = self.remaining()
            if space <= 0:
                self._ensure_space(1)
                space = self.remaining()
            n = min(n_total - offset, space)
            i0 = self.count
            i1 = i0 + n
            self.pos_xy[i0:i1] = arr[offset : offset + n]
            if isinstance(size_wh, np.ndarray):
                sw = np.ascontiguousarray(size_wh, dtype=np.float32)
                self.size_wh[i0:i1] = sw[offset : offset + n]
            else:
                self.size_wh[i0:i1, 0] = size_wh[0]
                self.size_wh[i0:i1, 1] = size_wh[1]
            self.origin_xy[i0:i1, 0] = origin_xy[0]
            self.origin_xy[i0:i1, 1] = origin_xy[1]
            self.rotation_deg[i0:i1] = rotation
            self.rgba[i0:i1, 0] = rgba[0]
            self.rgba[i0:i1, 1] = rgba[1]
            self.rgba[i0:i1, 2] = rgba[2]
            self.rgba[i0:i1, 3] = rgba[3]
            self.uv_rect[i0:i1, 0] = uv[0]
            self.uv_rect[i0:i1, 1] = uv[1]
            self.uv_rect[i0:i1, 2] = uv[2]
            self.uv_rect[i0:i1, 3] = uv[3]
            self.tex_id[i0:i1] = tex_id
            self.sort_key[i0:i1] = sort_key
            self.layer[i0:i1] = layer
            self.state_id[i0:i1] = state_id
            self.pass_hash[i0:i1] = pass_hash
            self.submit_index[i0:i1] = np.arange(
                submit_index_start + written,
                submit_index_start + written + n,
                dtype=np.int32,
            )
            self.depth_sorted[i0:i1] = depth_sorted
            self.screen_space[i0:i1] = screen_space
            self.count = i1
            written += n
            offset += n
            if offset < n_total and self.remaining() == 0:
                self._ensure_space(1)
        return written


__all__ = [
    "MAX_SPRITES",
    "FrameBuffer",
    "build_depth_runs",
    "build_runs",
    "is_depth_sorted_layer",
    "pass_name_hash",
    "resolve_uv",
    "runs_from_ordered",
    "set_depth_sort_layers",
]
