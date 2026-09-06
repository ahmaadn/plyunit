"""TileMapNode — the runtime tilemap node for plyunit.

Rules:
- Tile mutation (set_tile/fill/remove_tile) is supported for the editor
  and gameplay tile editing; there is no RT re-bake / autotile in the
  mutation hot path.
- Bake RTs for layers with ``render_mode=baked`` (default for the base layer).
- Per-tile drawing only when a layer has ``render_mode=tiles``.
- Physics merging (mesher) still goes through physics_baker.
"""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plyunit.backends.interfaces.i_renderer import ICanvas2D
from plyunit.core.types import RenderTexture
from plyunit.core.units.node_unit import NodeUnit
from plyunit.events.signal import Signal
from plyunit.tilemap.map_data import LayerMeta, ObjectData

from .chunk_tile import ChunkTile
from .encoding import get_decoder
from .map_data import (
    GID,
    BakedStaticBody,
    ChunkKey,
    ChunkRT,
    LayerID,
    MapConfig,
    MapSettingsRT,
    TilesetRuntime,
)
from .physics_baker import bake_all_chunks_runtime
from .physics_bridge import TileMapPhysicsBridge
from .tile_geometry import tile_dest_rect, tile_is_oversized, tile_overhang

if TYPE_CHECKING:
    from plyunit.rendering.renderer import Renderer

logger = logging.getLogger(__name__)

_LAYER_WORLD = 100
"""Z-layer constant for all tiles rendered to the world."""

_LAYER_BAKED_BASE = -1000
"""Default z-layer for the baked base layer (``layer_id == "1"``)."""


class _GidEntry:
    """Cached lookup GID -> (texture, source rect, asset_id).

    Attributes:
        texture: Backend-specific texture handle.
        source_rect: The portion of the texture used, tuple ``(x, y, w, h)``.
        asset_id: Texture asset ID in the Assets service.
        oversized: True if the image is larger than one grid cell. Such
            tiles must not be baked into a chunk RT because they would be
            clipped at the chunk boundary; see
            :mod:`plyunit.tilemap.tile_geometry`.
    """

    __slots__ = ("asset_id", "oversized", "source_rect", "texture")

    def __init__(
        self,
        texture: Any,
        source_rect: tuple[float, float, float, float],
        asset_id: str,
        oversized: bool = False,
    ) -> None:
        """Initializes a GID cache entry.

        Args:
            texture: Backend texture handle.
            source_rect: Source rectangle ``(x, y, w, h)`` inside the texture.
            asset_id: Texture asset ID.
            oversized: True if the image exceeds one grid cell.
        """
        self.texture = texture
        self.source_rect = source_rect
        self.asset_id = asset_id
        self.oversized = oversized

    def is_oversized(self, tile_size: int):
        """True if the entry marks an image larger than one cell.

        Recomputed from ``source_rect`` when the ``oversized`` attribute is
        missing: ``_gid_map`` can be filled directly by tests or other code
        with duck-typed objects that only have ``texture`` and
        ``source_rect``.
        """
        flag = self.oversized
        if flag is not None:
            return flag
        src = self.source_rect
        return tile_is_oversized(tile_size, src[2], src[3])


def parse_map_config(raw: dict) -> MapConfig:
    """Parses a raw JSON dict into a :class:`MapConfig`.

    Args:
        raw: Dict from ``json.load`` of a map file.
        decoders: Custom decoder registry. Currently reserved for
            extensions only; not used in basic parsing.

    Returns:
        MapConfig: The strongly-typed map structure ready for runtime use.
    """
    settings_raw = raw.get("settings", {})
    ts = settings_raw.get("tile_size", [16, 16])
    tile_size = (int(ts[0]), int(ts[1])) if len(ts) >= 2 else (16, 16)
    bg = settings_raw.get("background_color", [0, 0, 0, 255])
    settings = MapSettingsRT(
        tile_size=tile_size,
        chunk_size=int(settings_raw.get("chunk_size", 16)),
        encoding=settings_raw.get("encoding", "csv"),
        background_color=(
            int(bg[0]),
            int(bg[1]),
            int(bg[2]),
            int(bg[3]),
        )
        if len(bg) >= 4
        else (0, 0, 0, 255),
    )

    tilesets: dict[GID, TilesetRuntime] = {}
    for entry in raw.get("tilesets", {}).values():
        gid = entry.get("gid")
        if gid is None:
            continue
        tilesets[gid] = TilesetRuntime(
            gid=gid,
            asset_id=entry.get("asset_id"),
            physics=entry.get("physics"),
        )

    chunks: dict[ChunkKey, ChunkRT] = {}
    for key, cd in raw.get("chunks", {}).items():
        chunks[key] = ChunkRT(
            chunk_x=int(cd.get("chunk_x", 0)),
            chunk_y=int(cd.get("chunk_y", 0)),
            encoding=cd.get("encoding"),
            baked_physics=dict(cd.get("baked_physics", {})),
            raw_layers=dict(cd.get("layers", {})),
        )

    map_type = raw.get("map_type", "orthogonal")
    if map_type != "orthogonal":
        logger.debug(
            "map_type %r tidak didukung — dinormalisasi ke orthogonal.",
            map_type,
        )
        map_type = "orthogonal"

    return MapConfig(
        version=str(raw.get("version", "1")),
        map_type=map_type,
        settings=settings,
        tilesets=tilesets,
        layers=dict(raw.get("layers", {})),
        objects=list(raw.get("objects", [])),
        chunks=chunks,
        raw=raw,
    )


def load_map_file(config_path: str | Path) -> MapConfig:
    """Loads a map JSON file from the filesystem into a :class:`MapConfig`.

    Args:
        config_path: Path to the map JSON file.

    Returns:
        MapConfig: The parsed map structure.
    """
    path = Path(config_path)
    with open(path, encoding="utf-8") as f:
        raw: dict = json.load(f)
    return parse_map_config(raw)


class TileMapNode(NodeUnit):
    """Tilemap node: load, bake RTs, spawn physics, submit draws."""

    def __init__(
        self,
        name: str = "TileMapNode",
        config_path: str | Path | None = None,
        on_objects: Callable[[list[ObjectData]], None] | None = None,
    ) -> None:
        """Initializes TileMapNode; optionally loads a map from a path right away.

        Args:
            name: Node name (for debugging / registry).
            config_path: Path to the map JSON. When given, ``load_map``
                is called immediately.
            on_objects: Object hook forwarded to ``load_map``.
        """
        super().__init__(name=name)

        self.config: MapConfig | None = None
        self.tile_size: int = 16
        self.chunk_size: int = 16

        self._gid_map: dict[GID, _GidEntry] = {}
        self._baked_render: dict[tuple[ChunkKey, LayerID], RenderTexture] = {}
        self._spawned_physics: dict[ChunkKey, list[object]] = {}
        #: Largest overhang ``(right, up)`` across all oversized tiles.
        #: Widens culling so tall images do not flicker out when their
        #: owning chunk leaves the camera view.
        self._max_overhang: tuple[float, float] = (0.0, 0.0)

        self.margin_chunks: int = 1
        self._max_loaded_chunks = 64
        self._max_loads_per_update: int = 0

        self._chunk_tile = ChunkTile(
            self,
            max_loaded=self._max_loaded_chunks,
            margin=self.margin_chunks,
            max_loads_per_update=int(self.max_loads_per_update or 0),
        )

        self._bridge: TileMapPhysicsBridge | None = None

        self.tile_changed = Signal("tile_changed")
        """Signal emitted when a tile changes via the mutation API."""

        self._physics_baking = False
        self._background_bake_enabled = True

        if config_path is not None:
            self.load_map(config_path, on_objects=on_objects)

    def _canvas(self) -> ICanvas2D:
        """Gets the canvas of the active Renderer (via a one() query)."""
        return self.one("@Renderer").canvas

    @property
    def max_loaded_chunks(self) -> int:
        """Maximum capacity of chunks active in memory.

        Returns:
            int: The ``_max_loaded_chunks`` value.
        """
        return self._max_loaded_chunks

    @max_loaded_chunks.setter
    def max_loaded_chunks(self, value: int) -> None:
        """Sets the maximum capacity of active chunks (auto-propagates to ChunkTile).

        Args:
            value: New capacity (``>= 1`` will be used).
        """
        self._max_loaded_chunks = max(1, int(value))
        self._chunk_tile._max_loaded = max(1, int(value))

    @property
    def max_loads_per_update(self) -> int:
        """Limit on how many chunks are loaded per update (``0`` = unlimited)."""
        return self._max_loads_per_update

    @max_loads_per_update.setter
    def max_loads_per_update(self, value: int) -> None:
        """Sets the load limit per update (auto-propagates to ChunkTile).

        Args:
            value: New limit (``>= 0`` will be used).
        """
        clipped = max(0, int(value))
        self._max_loads_per_update = clipped
        self._chunk_tile._max_loads_per_update = clipped

    def on_ready(self) -> None:
        """Lifecycle hook: resolve the GID map, decode chunks, bake renders.

        Called by the engine when the node is ready.
        """
        if self.config is None:
            return

        self._resolve_gid_map()
        self._decode_all_chunks()
        self._bake_all_chunks()
        self._chunk_tile.update(self._visible_chunk_keys())

    def destroy(self) -> None:
        """Tear-down: removes physics bodies, unloads RTs, calls the parent destroy."""
        physics = self.one_or_none("@Physics")
        if physics is not None:
            for ids in self._spawned_physics.values():
                for sid in ids:
                    if isinstance(sid, int):
                        physics.remove_static(sid)

        self._spawned_physics.clear()

        if self._baked_render:
            canvas = self._canvas()
            for rt in self._baked_render.values():
                canvas.unload_render_texture(rt)
        self._baked_render.clear()
        super().destroy()

    def get_render_bounds(self) -> tuple[float, float, float, float] | None:
        """Computes the world bounding box containing every map chunk.

        Bounds are widened by the oversized-tile overhang: bottom-left
        anchored images can extend past the map's top and right edges, and
        these bounds feed spatial culling, so they must contain every pixel
        actually drawn.

        Returns:
            tuple[float, float, float, float] | None: World ``(x, y, w, h)``
            in pixels, or ``None`` when there is no config / chunks.
        """
        if self.config is None or not self.config.chunks:
            return None
        px = float(self.chunk_size * self.tile_size)
        min_cx = min_cy = 10**9
        max_cx = max_cy = -(10**9)
        for chunk in self.config.chunks.values():
            min_cx = min(min_cx, chunk.chunk_x)
            min_cy = min(min_cy, chunk.chunk_y)
            max_cx = max(max_cx, chunk.chunk_x)
            max_cy = max(max_cy, chunk.chunk_y)
        x = float(min_cx) * px
        y = float(min_cy) * px
        w = float(max_cx - min_cx + 1) * px
        h = float(max_cy - min_cy + 1) * px
        over_x, over_y = self._max_overhang
        # Spillage to the right adds width; spillage upward shifts the top
        # edge up while adding height.
        return (x, y - over_y, w + over_x, h + over_y)

    # ------------------------------------------------------------------
    # Load / decode
    # ------------------------------------------------------------------

    def load_map(
        self,
        config_path: str | Path,
        on_objects: Callable[[list[ObjectData]], None] | None = None,
    ) -> None:
        """Loads and parses a map JSON file; triggers the baked-physics
        fallback if needed.

        Args:
            config_path: Path to the map JSON file.
            on_objects: Hook called exactly once after the whole load
                finishes (parse, tile/chunk sizes, and the baked-physics
                fallback), receiving the list of map objects
                (``config.objects``). There is no fallback implementation —
                when ``None``, objects are only stored in ``config.objects``
                without processing.
        """
        path = Path(config_path)
        with open(path, encoding="utf-8") as f:
            raw: dict = json.load(f)

        self.config = parse_map_config(raw)
        self.tile_size = self.config.settings.tile_size[0]
        self.chunk_size = self.config.settings.chunk_size
        self._ensure_baked_physics()
        logger.info("Map dimuat dari: %s", path.name)
        if on_objects is not None:
            on_objects(self.config.objects)

    def _decode_chunk_layers(self, chunk: ChunkRT) -> None:
        """Decodes every layer of a chunk into ``gid_arrays`` (idempotent)."""
        if chunk.decoded:
            return
        default_enc = self.config.settings.encoding if self.config else "csv"
        enc = chunk.encoding or default_enc
        decoder = get_decoder(enc)
        for layer_id, raw in chunk.raw_layers.items():
            if layer_id not in chunk.gid_arrays:
                chunk.gid_arrays[layer_id] = decoder(raw)
        chunk.decoded = True

    def _decode_chunk_layer(
        self, chunk: ChunkRT, layer_id: LayerID
    ) -> list[GID] | None:
        """Decodes a single layer of a chunk, caching into ``gid_arrays``.

        Args:
            chunk: Target chunk.
            layer_id: Layer ID.

        Returns:
            list[GID] | None: The GID array for the layer, or ``None`` if
            the layer is absent from the chunk.
        """
        arr = chunk.gid_arrays.get(layer_id)
        if arr is not None:
            return arr
        raw = chunk.raw_layers.get(layer_id)
        if raw is None:
            return None
        default_enc = self.config.settings.encoding if self.config else "csv"
        enc = chunk.encoding or default_enc
        arr = get_decoder(enc)(raw)
        chunk.gid_arrays[layer_id] = arr
        return arr

    def _resolve_gid_map(self) -> None:
        """Builds the GID -> texture cache from the Assets service."""
        if self.config is None:
            return

        assets = self.one_or_none("@Assets", scope="global")
        if assets is None:
            assets = self.one_or_none("@Assets")
        if assets is None:
            logger.warning("Assets service not available; GID map empty.")
            return

        ts = self.tile_size
        max_over_x = max_over_y = 0.0
        for entry in self.config.tilesets.values():
            gid = entry.gid
            asset_id = entry.asset_id
            if asset_id is None:
                continue
            try:
                t_data = assets.get_texture_data(asset_id)
                src = t_data.source_rect
                oversized = tile_is_oversized(ts, src[2], src[3])
                if oversized:
                    over_x, over_y = tile_overhang(ts, src[2], src[3])
                    max_over_x = max(max_over_x, over_x)
                    max_over_y = max(max_over_y, over_y)
                self._gid_map[gid] = _GidEntry(
                    texture=t_data.texture,
                    source_rect=src,
                    asset_id=asset_id,
                    oversized=oversized,
                )
            except KeyError:
                logger.warning("Asset '%s' (GID %d) tidak ditemukan.", asset_id, gid)

        self._max_overhang = (max_over_x, max_over_y)
        logger.debug("GID map: %d entries.", len(self._gid_map))
        if max_over_x or max_over_y:
            logger.debug(
                "Tile oversized terdeteksi; overhang maks (kanan, atas)=%s",
                self._max_overhang,
            )

    def get_gid_at(
        self, world_x: float, world_y: float, layer_id: LayerID = "1"
    ) -> GID | None:
        """Queries the GID at given world coordinates and layer.

        Args:
            world_x: World X position in pixels.
            world_y: World Y position in pixels.
            layer_id: Layer ID to query (default ``"1"``).

        Returns:
            GID | None: The GID value, or ``None`` when outside the map / GID 0.
        """
        if self.config is None:
            return None

        ts = self.tile_size
        cs = self.chunk_size
        grid_x = int(world_x // ts)
        grid_y = int(world_y // ts)
        cx = grid_x // cs
        cy = grid_y // cs
        lx = grid_x % cs
        ly = grid_y % cs
        key: ChunkKey = f"{cx},{cy}"

        chunk = self.config.chunks.get(key)
        if chunk is None:
            return None

        gid_array = self._decode_chunk_layer(chunk, layer_id)
        if gid_array is None:
            return None

        idx = ly * cs + lx
        if idx < 0 or idx >= len(gid_array):
            return None

        gid = gid_array[idx]
        return gid if gid != 0 else None

    def get_physics_bodies_in_chunk(
        self, chunk_key: ChunkKey, layer_id: LayerID | None = None
    ) -> list[BakedStaticBody]:
        """Collects every baked static body in a chunk.

        Args:
            chunk_key: Target chunk key.
            layer_id: Optional layer filter. If ``None``, all layers are
                collected.

        Returns:
            list[BakedStaticBody]: The bodies in the chunk (possibly empty).
        """
        if self.config is None:
            return []

        chunk = self.config.chunks.get(chunk_key)
        if chunk is None:
            return []

        result: list[BakedStaticBody] = []
        for lid, baked_chunk in chunk.baked_physics.items():
            if layer_id is not None and lid != layer_id:
                continue
            result.extend(baked_chunk.get("bodies", []))
        return result

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_tile(
        self,
        world_x: float,
        world_y: float,
        gid: GID,
        layer_id: LayerID = "1",
    ) -> bool:
        """Sets a GID at world coordinates (for the editor / gameplay tile editing).

        Args:
            world_x: World X position in pixels.
            world_y: World Y position in pixels.
            gid: New GID value (``0`` means empty).
            layer_id: Target layer ID.

        Returns:
            bool: ``True`` if the value changed.

        Note:
            No automatic re-bake: the ``baked`` layer render textures and
            the physics static bodies keep using the old data until
            refreshed (see ``_rebake_chunk_physics`` for physics;
            ``baked`` layers need a manual re-bake).
        """
        if self.config is None:
            return False

        ts = self.tile_size
        cs = self.chunk_size
        grid_x = int(world_x // ts)
        grid_y = int(world_y // ts)
        cx = grid_x // cs
        cy = grid_y // cs
        lx = grid_x % cs
        ly = grid_y % cs
        key: ChunkKey = f"{cx},{cy}"

        chunk = self.config.chunks.get(key)
        if chunk is None:
            return False

        gid_array = self._decode_chunk_layer(chunk, layer_id)
        if gid_array is None:
            gid_array = [0] * (cs * cs)
            chunk.gid_arrays[layer_id] = gid_array
            chunk.raw_layers[layer_id] = gid_array

        idx = ly * cs + lx
        if idx < 0 or idx >= len(gid_array):
            return False

        old_gid = gid_array[idx]
        if old_gid == gid:
            return False

        gid_array[idx] = gid
        chunk.raw_layers[layer_id] = gid_array
        chunk.decoded = True
        self.tile_changed.emit(key, layer_id, grid_x, grid_y, old_gid, gid)
        return True

    def fill(
        self,
        rect: tuple[float, float, float, float],
        gid: GID,
        layer_id: LayerID = "1",
    ) -> int:
        """Fills a rectangular area with a GID.

        Args:
            rect: Rectangle ``(x, y, w, h)`` in pixels.
            gid: GID to install.
            layer_id: Target layer ID.

        Returns:
            int: The number of tiles that actually changed.
        """
        x, y, w, h = rect
        ts = self.tile_size
        gx0 = int(x // ts)
        gy0 = int(y // ts)
        gx1 = int((x + w - 1) // ts) if w > 0 else gx0 - 1
        gy1 = int((y + h - 1) // ts) if h > 0 else gy0 - 1

        changed = 0
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                if self.set_tile(gx * ts, gy * ts, gid, layer_id):
                    changed += 1
        return changed

    def remove_tile(
        self, world_x: float, world_y: float, layer_id: LayerID = "1"
    ) -> bool:
        """Removes the tile at world coordinates (alias of set_tile(.., 0, ..)).

        Args:
            world_x: World X position.
            world_y: World Y position.
            layer_id: Target layer ID.

        Returns:
            bool: ``True`` if it was previously non-``0`` and got removed.
        """
        return self.set_tile(world_x, world_y, 0, layer_id)

    def _invalidate_chunk(
        self, key: ChunkKey, chunk: ChunkRT, layer_id: LayerID
    ) -> None:
        """Chunk invalidation hook (currently a no-op; reserved for editor wiring)."""
        return None

    def _rebake_chunk_physics(self, key: ChunkKey, chunk: ChunkRT) -> None:
        """Re-bakes physics for one chunk and respawns it into Physics."""
        from .physics_baker import bake_chunk_from_arrays, build_gid_physics_map_runtime

        if self.config is None:
            return
        cfg = self.config
        gid_physics = build_gid_physics_map_runtime(cfg.tilesets)
        if not gid_physics:
            return

        old_ids = self._spawned_physics.pop(key, None)
        if old_ids:
            self._despawn_chunk_physics(old_ids)

        new_baked = bake_chunk_from_arrays(
            chunk, cfg.settings.chunk_size, cfg.settings.tile_size[0], gid_physics
        )
        chunk.baked_physics = new_baked

        store = self._chunk_tile
        if store is not None and store.is_loaded(key):
            self._spawn_chunk_physics(key, chunk)

    # ------------------------------------------------------------------
    # Physics bake / spawn
    # ------------------------------------------------------------------

    def _ensure_baked_physics(self) -> None:
        """Ensures every chunk has baked_physics; performs a fallback bake if needed."""
        if self.config is None:
            return
        if self.config is None:
            return

        cfg = self.config
        from .physics_baker import build_gid_physics_map_runtime

        gid_physics = build_gid_physics_map_runtime(cfg.tilesets)
        if not gid_physics:
            return

        needs_bake = any(not chunk.baked_physics for chunk in cfg.chunks.values())
        if not needs_bake:
            return

        warnings.warn(
            "Map missing baked_physics — runtime fallback bake is deprecated. "
            "Editor MapDocument.save should pre-bake physics.",
            DeprecationWarning,
            stacklevel=2,
        )

        if not self._background_bake_enabled:
            self._bake_physics_sync()
            return

        logger.warning(
            "Map belum punya baked_physics — baking di background thread. "
            "Editor sebaiknya pre-bake physics saat simpan."
        )
        self._start_background_bake()

    def _bake_physics_sync(self) -> None:
        """Bakes physics for the whole map synchronously on the main thread."""
        if self.config is None:
            return
        cfg = self.config
        for chunk in cfg.chunks.values():
            self._decode_chunk_layers(chunk)
        baked_all = bake_all_chunks_runtime(cfg)
        for key, baked_layers in baked_all.items():
            chunk = cfg.chunks.get(key)
            if chunk is not None:
                chunk.baked_physics = baked_layers

    def _start_background_bake(self) -> None:
        """Spawns a daemon thread to bake map physics in the background."""
        import threading

        if self._physics_baking:
            return
        self._physics_baking = True

        def _worker() -> None:
            """Runs the synchronous bake and clears the in-progress flag."""
            try:
                self._bake_physics_sync()
            except Exception:
                logger.exception("Background physics bake gagal.")
            finally:
                self._physics_baking = False

        threading.Thread(
            target=_worker, daemon=True, name="tilemap-physics-bake"
        ).start()

    def _spawn_chunk_physics(self, key: ChunkKey, chunk: ChunkRT) -> None:
        """Spawns a chunk's static bodies into Physics (once per key)."""
        if key in self._spawned_physics:
            return

        bodies: list[BakedStaticBody] = []
        for baked_chunk in chunk.baked_physics.values():
            bodies.extend(baked_chunk.get("bodies", []))
        if not bodies:
            return

        if type(self)._spawn_static_body is not TileMapNode._spawn_static_body:
            spawned: list[object] = []
            for body in bodies:
                handle = self._spawn_static_body(body)
                if handle is not None:
                    spawned.append(handle)
            if spawned:
                self._spawned_physics[key] = spawned
            return

        bridge = self.get_bridge()
        if bridge is None:
            logger.debug("Tidak ada Physics — spawn fisika chunk %s di-skip.", key)
            return
        ids = bridge.spawn_bodies(bodies)
        if ids:
            self._spawned_physics[key] = ids

    def _despawn_chunk_physics(self, ids: list[object]) -> None:
        """Removes static bodies by the id list returned at spawn time."""
        bridge = self.get_bridge()
        if bridge is None:
            return
        int_ids = [i for i in ids if isinstance(i, int)]
        if int_ids:
            bridge.despawn_bodies(int_ids)

    def get_bridge(self) -> TileMapPhysicsBridge | None:
        """Gets (or creates + caches) the :class:`TileMapPhysicsBridge` instance."""
        if self._bridge is not None:
            return self._bridge

        physics = self.one_or_none("@Physics")
        if physics is None:
            return None

        bridge = TileMapPhysicsBridge(
            physics=physics,
            tile_size=self.tile_size,
            chunk_size=self.chunk_size,
        )
        bridge.install_one_way_handler()
        self._bridge = bridge
        return bridge

    def _spawn_static_body(self, body: BakedStaticBody) -> object | None:
        """Default hook for when a subclass overrides ``_spawn_static_body``.

        Default: log and return ``None`` (meaning "use the bridge").
        """
        logger.debug(
            "Spawn static body: pos=%s shape=%s layer=%d mask=%d",
            body["world_pos"],
            body["shape"].get("kind"),
            body["physics_layer"],
            body["physics_mask"],
        )
        return None

    # ------------------------------------------------------------------
    # Render bake / submit
    # ------------------------------------------------------------------

    def render_submit(self, renderer: Renderer, context=None) -> None:
        """Submits draws for every visible chunk to the renderer.

        Args:
            renderer: Backend renderer to submit to.
            context: Extra context (optional, currently unused).
        """
        if self.config is None:
            return

        visible_keys = self._visible_chunk_keys()
        store = self._chunk_tile
        store.update(visible_keys)

        for key in store.loaded:
            chunk = self.config.chunks.get(key)
            if chunk is None:
                continue
            if chunk.baked_physics and key not in self._spawned_physics:
                self._spawn_chunk_physics(key, chunk)

        for key in visible_keys:
            if not store.is_loaded(key):
                continue
            chunk = self.config.chunks.get(key)
            if chunk is None:
                continue
            self._submit_chunk(renderer, key, chunk)

    def _layer_meta(self, layer_id: LayerID) -> LayerMeta:
        """Gets a layer's metadata (dict) or ``{}`` when absent."""
        if self.config is None:
            return {}
        meta = self.config.layers.get(layer_id)
        return meta if isinstance(meta, dict) else {}

    def _effective_render_mode(self, layer_id: LayerID) -> str:
        """Determines the final render mode (``"baked"`` / ``"tiles"``) for a layer.

        Accounts for ``y_sort_enabled`` (overrides baked -> tiles) and the
        ``auto`` rule (``"1"`` = baked, other layers = tiles).

        Args:
            layer_id: Layer ID.

        Returns:
            str: ``"baked"`` or ``"tiles"``.
        """
        meta = self._layer_meta(layer_id)
        y_sort = bool(meta.get("y_sort_enabled", False)) and layer_id != "1"
        if y_sort:
            mode = meta.get("render_mode", "auto")
            if mode == "baked":
                logger.debug(
                    "Layer %s: render_mode=baked diabaikan karena y_sort_enabled",
                    layer_id,
                )
            return "tiles"

        mode = meta.get("render_mode", "auto")
        if mode == "baked":
            return "baked"
        if mode == "tiles":
            return "tiles"
        return "baked" if layer_id == "1" else "tiles"

    def _bake_chunk_layer(
        self, key: ChunkKey, chunk: ChunkRT, layer_id: LayerID
    ) -> None:
        """Bakes one chunk layer into a render texture (cached)."""
        bake_key = (key, layer_id)
        if bake_key in self._baked_render:
            return
        gid_array = chunk.gid_arrays.get(layer_id)
        if gid_array is None:
            return
        if not any(gid != 0 for gid in gid_array):
            return
        # A layer whose contents are all oversized tiles produces nothing
        # in the RT; don't allocate a wasted RT for it.
        if not self._has_bakeable_tile(gid_array):
            return

        px = self.chunk_size * self.tile_size
        canvas = self._canvas()
        rt = canvas.load_render_texture(px, px)
        canvas.begin_texture_mode(rt)
        canvas.clear_transparent()
        self._draw_layer_to_texture(gid_array)
        canvas.end_texture_mode()
        # Point filter: pixel tiles stay sharp; trilinear + pan caused shimmer.
        canvas.set_texture_filter(rt, "point")
        self._baked_render[bake_key] = rt

    def _has_bakeable_tile(self, gid_array: list[GID]) -> bool:
        """True if at least one cell-sized tile is suitable for baking into the RT."""
        for gid in gid_array:
            if gid == 0:
                continue
            entry = self._gid_map.get(gid)
            if entry is not None and not entry.is_oversized(self.tile_size):
                return True
        return False

    def _bake_chunk_render(self, key: ChunkKey, chunk: ChunkRT) -> None:
        """Bakes every ``baked`` layer for one chunk."""
        layer_ids = set(chunk.raw_layers) | set(chunk.gid_arrays)
        if self.config is not None:
            layer_ids |= set(self.config.layers)
        for layer_id in layer_ids:
            if self._effective_render_mode(layer_id) == "baked":
                self._bake_chunk_layer(key, chunk, layer_id)

    def _bake_all_chunks(self) -> None:
        """Decodes + bakes every chunk in the map (called from ``on_ready``)."""
        if self.config is None:
            return
        for key, chunk in self.config.chunks.items():
            self._decode_chunk_layers(chunk)
            self._bake_chunk_render(key, chunk)

    def _decode_all_chunks(self) -> None:
        """Decodes every chunk in the map (lazy decode cache)."""
        if self.config is None:
            return
        for chunk in self.config.chunks.values():
            self._decode_chunk_layers(chunk)

    def _draw_layer_to_texture(self, gid_array: list[GID]) -> None:
        """Renders a GID array into the active render texture
        (used by ``_bake_chunk_layer``).

        Oversized tiles are **skipped**: a chunk RT is exactly one chunk in
        size, so spilling image parts would be clipped at the chunk
        boundary. Those tiles are submitted separately by
        :meth:`_submit_oversized_tiles`.
        """
        canvas = self._canvas()
        ts = self.tile_size
        cs = self.chunk_size

        for i, gid in enumerate(gid_array):
            if gid == 0 or gid not in self._gid_map:
                continue
            entry = self._gid_map[gid]
            if entry.is_oversized(self.tile_size):
                continue
            col = i % cs
            row = i // cs
            src = entry.source_rect
            canvas.draw_texture_region(
                entry.texture,
                src,
                tile_dest_rect(col, row, ts, src[2], src[3]),
            )

    def _load_chunk(self, key: ChunkKey, chunk: ChunkRT) -> None:
        """Hook invoked by :class:`ChunkTile` when loading a chunk.

        Only decodes + spawns physics; all baked RTs were baked once in
        ``on_ready`` and stay resident until ``destroy``.
        """
        self._decode_chunk_layers(chunk)
        self._spawn_chunk_physics(key, chunk)

    def _unload_chunk(self, key: ChunkKey) -> None:
        """Hook invoked by :class:`ChunkTile` when unloading a chunk.

        Baked RTs are not unloaded with it (resident until ``destroy``).
        """
        ids = self._spawned_physics.pop(key, None)
        if ids:
            self._despawn_chunk_physics(ids)

    def _visible_chunk_keys(self) -> set[ChunkKey]:
        """Computes the set of chunk keys visible in the viewport (with margin)."""
        all_keys: set[ChunkKey] = set(self.config.chunks.keys())  # type: ignore[union-attr]

        camera = self.one_or_none("@Camera2D", scope="global")
        if camera is None:
            return all_keys

        left, top, right, bottom = camera.get_view_rect()
        px = self.chunk_size * self.tile_size
        if px <= 0:
            return all_keys
        margin = int(self.margin_chunks)

        # Oversized tiles anchor bottom-left: their image spills upward and
        # to the right of the cell. The owning chunk can sit outside the
        # viewport while its image is still visible, so the scan range is
        # widened by the largest overhang (rounded up in chunk units).
        over_x, over_y = self._max_overhang
        extra_cx = int(-(-over_x // px)) if over_x > 0 else 0
        extra_cy = int(-(-over_y // px)) if over_y > 0 else 0

        start_cx = int(left // px) - margin - extra_cx
        end_cx = int(right // px) + margin
        start_cy = int(top // px) - margin
        end_cy = int(bottom // px) + margin + extra_cy

        visible: set[ChunkKey] = set()
        for cx in range(start_cx, end_cx + 1):
            for cy in range(start_cy, end_cy + 1):
                visible.add(f"{cx},{cy}")
        return visible

    def _submit_chunk(
        self,
        renderer: Renderer,
        key: ChunkKey,
        chunk: ChunkRT,
    ) -> None:
        """Submits draws for every layer of a chunk (baked + tiles)."""
        cx = chunk.chunk_x
        cy = chunk.chunk_y
        px = self.chunk_size * self.tile_size
        world_x = cx * px
        world_y = cy * px

        layer_ids = set(chunk.raw_layers) | set(chunk.gid_arrays)
        if self.config is not None:
            layer_ids |= set(self.config.layers)

        def _sort_key(lid: str) -> tuple[int, str]:
            """Sorts numeric layer IDs naturally; non-numeric ones sort last."""
            try:
                return (0, f"{int(lid):08d}")
            except ValueError:
                return (1, lid)

        for layer_id in sorted(layer_ids, key=_sort_key):
            if self._effective_render_mode(layer_id) == "baked":
                self._submit_baked_layer(renderer, key, layer_id, world_x, world_y, px)
                # Oversized tiles are deliberately left out of the RT (they
                # would be clipped at the chunk boundary), so they are drawn
                # per-tile here.
                self._submit_oversized_tiles(
                    renderer, layer_id, chunk, world_x, world_y
                )
            else:
                self._submit_prop_layer(renderer, layer_id, chunk, world_x, world_y)

    def _submit_baked_layer(
        self,
        renderer: Renderer,
        key: ChunkKey,
        layer_id: LayerID,
        world_x: int,
        world_y: int,
        px: int,
    ) -> None:
        """Submits one baked layer to the renderer (using the cached RT)."""
        bake_key = (key, layer_id)
        if bake_key not in self._baked_render:
            return

        tex = self._baked_render[bake_key].texture
        source = (0.0, 0.0, float(tex.width), float(-tex.height))
        dest = (float(world_x), float(world_y), float(px), float(px))

        meta = self._layer_meta(layer_id)
        z_offset = int(meta.get("z_offset", 0))
        if layer_id == "1":
            z = _LAYER_BAKED_BASE
        else:
            try:
                layer_num = int(layer_id)
            except ValueError:
                layer_num = 0
            z = layer_num * 100 + z_offset

        renderer.render_sprite(
            z=z,
            layer=_LAYER_WORLD,
            texture=tex,
            source=source,
            dest=dest,
            origin=(0.0, 0.0),
            rotation=0.0,
            tint=(255, 255, 255, 255),
        )

    def _submit_oversized_tiles(
        self,
        renderer: Renderer,
        layer_id: LayerID,
        chunk: ChunkRT,
        world_x: int,
        world_y: int,
    ) -> None:
        """Submits the oversized tiles belonging to a ``baked`` layer.

        Baked layers are drawn as one RT quad per chunk, but that RT is
        exactly one chunk in size and cannot hold images spilling past its
        edges. Such tiles are skipped during baking and drawn here at
        their original size, in world space.

        ``z`` is placed above this layer's baked quad so the ordering
        stays sensible against the base tiles below it.
        """
        gid_array = self._decode_chunk_layer(chunk, layer_id)
        if gid_array is None:
            return

        meta = self._layer_meta(layer_id)
        z_offset = int(meta.get("z_offset", 0))
        if layer_id == "1":
            base_z = _LAYER_BAKED_BASE
        else:
            try:
                layer_num = int(layer_id)
            except ValueError:
                layer_num = 0
            base_z = layer_num * 100 + z_offset

        ts = self.tile_size
        cs = self.chunk_size
        for i, gid in enumerate(gid_array):
            if gid == 0:
                continue
            entry = self._gid_map.get(gid)
            if entry is None or not entry.is_oversized(self.tile_size):
                continue
            col = i % cs
            row = i // cs
            src = entry.source_rect
            dx, dy, dw, dh = tile_dest_rect(col, row, ts, src[2], src[3])
            renderer.render_sprite(
                z=base_z + 1,
                layer=_LAYER_WORLD,
                texture=entry.texture,
                source=src,
                dest=(float(world_x + dx), float(world_y + dy), float(dw), float(dh)),
                origin=(0.0, 0.0),
                rotation=0.0,
                tint=(255, 255, 255, 255),
                y_sort=False,
                y_sort_origin=0.0,
            )

    def _submit_prop_layer(
        self,
        renderer: Renderer,
        layer_id: LayerID,
        chunk: ChunkRT,
        world_x: int,
        world_y: int,
    ) -> None:
        """Submits one per-tile layer to the renderer (mode ``"tiles"``)."""
        gid_array = self._decode_chunk_layer(chunk, layer_id)
        if gid_array is None:
            return

        try:
            layer_num = int(layer_id)
        except ValueError:
            layer_num = 0
        ts = self.tile_size
        cs = self.chunk_size
        meta = self._layer_meta(layer_id)
        z_offset = int(meta.get("z_offset", 0))
        y_sort = bool(meta.get("y_sort_enabled", False)) and layer_id != "1"

        for i, gid in enumerate(gid_array):
            if gid == 0 or gid not in self._gid_map:
                continue

            entry = self._gid_map[gid]
            col = i % cs
            row = i // cs
            src = entry.source_rect
            # Original image size, anchored at the cell's bottom-left corner:
            # excess height grows upward and excess width rightward, so the
            # object's footing always sits at the base of the chosen cell.
            dx, dy, dw, dh = tile_dest_rect(col, row, ts, src[2], src[3])
            dest = (float(world_x + dx), float(world_y + dy), float(dw), float(dh))
            z = layer_num * 100 + z_offset
            # Y-sort uses the **cell** position, not the image's top edge.
            # Tall bottom-left-anchored images have a ``dy`` far above their
            # cell; using ``dy`` would sort them as if they were far behind.
            # The cell-based value is independent of image height, keeping
            # the ordering against old content unchanged.
            sort_y = float(world_y + row * ts)
            if y_sort:
                z += sort_y

            renderer.render_sprite(
                z=z,
                layer=_LAYER_WORLD,
                texture=entry.texture,
                source=src,
                dest=dest,
                origin=(0.0, 0.0),
                rotation=0.0,
                tint=(255, 255, 255, 255),
                y_sort=y_sort,
                y_sort_origin=sort_y if y_sort else 0.0,
            )
