"""Physics Baker — computes collision shapes and greedily merges static bodies.

The only greedy merge algorithm lives in :mod:`mesher`. This module merely
wraps the mesher results into :class:`BakedStaticBody` while respecting the
tile's original geometry (full box → merge; polygon/circle/non-full box →
per-tile).

All computation may only be invoked from:
- The map editor when saving the file.
- TileMapNode.on_load() the first time a map is loaded (background fallback).

The runtime must NOT call this module synchronously.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .map_data import (
    GID,
    BakedPhysicsChunk,
    BakedStaticBody,
    ChunkData,
    ChunkKey,
    ChunkRT,
    LayerID,
    MapConfig,
    PhysicsBoxShape,
    PhysicsShape,
    TilePhysicsData,
    TilesetEntry,
    TilesetRuntime,
)
from .mesher import generate_merged_rectangles_grouped

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _physics_key(p: TilePhysicsData) -> tuple[object, ...]:
    """Builds a grouping key for tiles with identical physics parameters.

    The key covers layer, mask, ``is_one_way``, friction/restitution
    (rounded to 4 decimals), and ``shape_kind`` so that tiles with
    identical physics properties can be merged into one static body.

    Args:
        p: Per-GID physics data.

    Returns:
        tuple[object, ...]: Hashable tuple serving as the merge group identity.
    """
    shape = p.get("shape")
    shape_kind = shape.get("kind", "none") if shape else "none"
    return (
        p.get("layer", 0),
        p.get("mask", 0),
        p.get("is_one_way", False),
        round(p.get("friction", 0.5), 4),
        round(p.get("restitution", 0.0), 4),
        shape_kind,
    )


def _is_full_tile_box(shape: PhysicsShape | None, tile_size: int) -> bool:
    """Checks whether the shape is a box covering one full tile.

    A box without explicit ``offset``/``size`` is treated as full-tile
    (default ``offset=(0,0)``, ``size=tile_size``).

    Args:
        shape: Physics shape; ``None`` is considered not full-tile.
        tile_size: Size of one tile edge in pixels.

    Returns:
        bool: ``True`` if the shape is a full-tile box.
    """
    if shape is None:
        return False
    if shape.get("kind", "box") != "box":
        return False
    ox, oy = shape.get("offset", (0.0, 0.0))
    sw, sh = shape.get("size", (float(tile_size), float(tile_size)))
    return (ox, oy) == (0.0, 0.0) and (sw, sh) == (
        float(tile_size),
        float(tile_size),
    )


def _make_merged_body(
    world_x: float,
    world_y: float,
    rect_w: float,
    rect_h: float,
    physics: TilePhysicsData,
) -> BakedStaticBody:
    """Builds one :class:`BakedStaticBody` from a merged-rectangle result.

    Args:
        world_x: World X position of the rectangle's top-left corner.
        world_y: World Y position of the rectangle's top-left corner.
        rect_w: Merged rectangle width (pixels).
        rect_h: Merged rectangle height (pixels).
        physics: Physics properties inherited by the body.

    Returns:
        BakedStaticBody: The baked static body.
    """
    shape: PhysicsBoxShape = {
        "kind": "box",
        "offset": (0.0, 0.0),
        "size": (rect_w, rect_h),
    }
    return {
        "shape": shape,
        "world_pos": (world_x, world_y),
        "physics_layer": physics.get("layer", 1),
        "physics_mask": physics.get("mask", 0xFFFF),
        "is_one_way": physics.get("is_one_way", False),
        "friction": physics.get("friction", 0.5),
        "restitution": physics.get("restitution", 0.0),
    }


def _make_per_tile_body(
    tile_world_x: float,
    tile_world_y: float,
    physics: TilePhysicsData,
) -> BakedStaticBody:
    """Builds one per-tile :class:`BakedStaticBody` with its original shape.

    The shape is kept as-is (not run through the merge). If ``physics``
    has no shape, falls back to an empty box.

    Args:
        tile_world_x: World X position of the tile's top-left corner.
        tile_world_y: World Y position of the tile's top-left corner.
        physics: The tile's physics properties.

    Returns:
        BakedStaticBody: The per-tile static body.
    """
    shape = physics.get("shape")
    if shape is None:
        # No explicit shape → fall back to an empty box.
        shape = {"kind": "box", "offset": (0.0, 0.0), "size": (0.0, 0.0)}
    return {
        "shape": shape,
        "world_pos": (tile_world_x, tile_world_y),
        "physics_layer": physics.get("layer", 1),
        "physics_mask": physics.get("mask", 0xFFFF),
        "is_one_way": physics.get("is_one_way", False),
        "friction": physics.get("friction", 0.5),
        "restitution": physics.get("restitution", 0.0),
    }


def _bake_layer(
    gid_array: list[GID],
    chunk_size: int,
    tile_size: int,
    chunk_world_x: float,
    chunk_world_y: float,
    gid_physics: dict[GID, TilePhysicsData],
) -> list[BakedStaticBody]:
    """Bakes physics for one layer within one chunk.

    Tiles with full-tile boxes (``offset (0,0)``, ``size == tile_size``)
    are greedily merged with identically-keyed neighbors. Tiles with
    other shapes (polygon/circle/non-full box) are emitted per-tile as-is.

    Args:
        gid_array: GID list of one layer (length ``chunk_size * chunk_size``).
        chunk_size: Number of tiles per chunk side.
        tile_size: Size of one tile edge in pixels.
        chunk_world_x: World X position of the chunk's top-left corner.
        chunk_world_y: World Y position of the chunk's top-left corner.
        gid_physics: Mapping of GID to :class:`TilePhysicsData`.

    Returns:
        list[BakedStaticBody]: The baked static bodies for the layer.
    """
    cs = chunk_size
    bodies: list[BakedStaticBody] = []

    # Key grid for mergeable (full-tile box) tiles; None for per-tile.
    key_grid: list[list[object | None]] = [[None] * cs for _ in range(cs)]
    per_tile_tiles: list[tuple[int, int, TilePhysicsData]] = []

    for row in range(cs):
        for col in range(cs):
            idx = row * cs + col
            if idx >= len(gid_array):
                continue
            gid = gid_array[idx]
            if gid == 0 or gid not in gid_physics:
                continue
            physics = gid_physics[gid]
            shape = physics.get("shape")
            if shape is None or _is_full_tile_box(shape, tile_size):
                key_grid[row][col] = _physics_key(physics)
            else:
                per_tile_tiles.append((col, row, physics))

    # Merge full-tile boxes via the mesher (the only greedy algorithm).
    merged = generate_merged_rectangles_grouped(key_grid, float(tile_size))
    for wx, wy, rw, rh, _key in merged:
        # Take the representative physics from this rect's first cell.
        col0 = int(wx // tile_size)
        row0 = int(wy // tile_size)
        idx0 = row0 * cs + col0
        gid0 = gid_array[idx0] if idx0 < len(gid_array) else 0
        physics = gid_physics.get(gid0, {})
        bodies.append(
            _make_merged_body(
                chunk_world_x + wx,
                chunk_world_y + wy,
                rw,
                rh,
                physics,
            )
        )

    # Per-tile bodies for non-full shapes.
    for col, row, physics in per_tile_tiles:
        tile_wx = chunk_world_x + col * tile_size
        tile_wy = chunk_world_y + row * tile_size
        bodies.append(_make_per_tile_body(tile_wx, tile_wy, physics))

    return bodies


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_gid_physics_map(
    tilesets: dict[str, TilesetEntry],
) -> dict[GID, TilePhysicsData]:
    """Builds a ``GID -> TilePhysicsData`` mapping from dict tileset definitions.

    Args:
        tilesets: Mapping of ``asset_id`` to :class:`TilesetEntry` (raw dict).

    Returns:
        dict[GID, TilePhysicsData]: GID to physics mapping; only entries
        with valid ``physics`` are included.
    """
    result: dict[GID, TilePhysicsData] = {}
    for entry in tilesets.values():
        gid = entry.get("gid")
        physics = entry.get("physics")
        if gid is not None and physics:
            result[gid] = physics
    return result


def build_gid_physics_map_runtime(
    tilesets: dict[GID, TilesetRuntime],
) -> dict[GID, TilePhysicsData]:
    """Builds a ``GID -> TilePhysicsData`` mapping from runtime tilesets.

    Args:
        tilesets: Mapping of ``GID`` to :class:`TilesetRuntime` (dataclass).

    Returns:
        dict[GID, TilePhysicsData]: GID to physics mapping; entries without
        ``physics`` are skipped.
    """
    result: dict[GID, TilePhysicsData] = {}
    for entry in tilesets.values():
        if entry.physics:
            result[entry.gid] = entry.physics
    return result


def bake_chunk_physics(
    chunk_data: ChunkData,
    chunk_size: int,
    tile_size: int,
    gid_physics: dict[GID, TilePhysicsData],
    decode_fn: dict[str, object],
    default_encoding: str = "csv",
) -> dict[LayerID, BakedPhysicsChunk]:
    """Bakes all physics for one chunk from raw :class:`ChunkData`.

    Args:
        chunk_data: Raw chunk data parsed from JSON.
        chunk_size: Number of tiles per chunk side.
        tile_size: Size of one tile edge in pixels.
        gid_physics: Mapping of GID to physics data.
        decode_fn: Decoder registry (name -> function).
        default_encoding: Default encoding when the chunk has no override.

    Returns:
        dict[LayerID, BakedPhysicsChunk]: Baking per layer; layers without
        physics-bearing solid tiles are skipped.
    """
    from .encoding import decode_array  # local import to avoid circular imports

    cx = chunk_data.get("chunk_x", 0)
    cy = chunk_data.get("chunk_y", 0)
    world_x = float(cx * chunk_size * tile_size)
    world_y = float(cy * chunk_size * tile_size)

    encoding = chunk_data.get("encoding", default_encoding)
    decoder = decode_fn.get(encoding, decode_array)  # type: ignore[call-arg]

    baked: dict[LayerID, BakedPhysicsChunk] = {}

    for layer_id, raw_data in chunk_data.get("layers", {}).items():
        gid_array = decoder(raw_data)  # type: ignore[operator]

        has_physics = any(gid != 0 and gid in gid_physics for gid in gid_array)
        if not has_physics:
            continue

        bodies = _bake_layer(
            gid_array=gid_array,
            chunk_size=chunk_size,
            tile_size=tile_size,
            chunk_world_x=world_x,
            chunk_world_y=world_y,
            gid_physics=gid_physics,
        )

        if bodies:
            baked[layer_id] = {"bodies": bodies}
            logger.debug(
                "Chunk (%d,%d) layer %s: %d tiles → %d bodies",
                cx,
                cy,
                layer_id,
                chunk_size * chunk_size,
                len(bodies),
            )

    return baked


def bake_all_chunks(
    map_config: dict,
    decode_fn: dict[str, object],
) -> dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]]:
    """Bakes physics for the whole map at once from a raw dict.

    Args:
        map_config: Raw ``MapConfigData`` dict from ``json.load``.
        decode_fn: Decoder registry (name -> function).

    Returns:
        dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]]: Baking per chunk,
        per layer. Chunks without any collision are skipped.
    """
    settings = map_config.get("settings", {})
    tile_size: int = settings.get("tile_size", [16, 16])[0]
    chunk_size: int = settings.get("chunk_size", 16)
    default_encoding: str = settings.get("encoding", "csv")

    gid_physics = build_gid_physics_map(map_config.get("tilesets", {}))

    if not gid_physics:
        logger.info("Tidak ada tile dengan data fisika, skip baking.")
        return {}

    result: dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]] = {}

    for chunk_key, chunk_data in map_config.get("chunks", {}).items():
        baked = bake_chunk_physics(
            chunk_data=chunk_data,
            chunk_size=chunk_size,
            tile_size=tile_size,
            gid_physics=gid_physics,
            decode_fn=decode_fn,
            default_encoding=default_encoding,
        )
        if baked:
            result[chunk_key] = baked

    logger.info("Physics baking selesai: %d chunk dengan collision data.", len(result))
    return result


def bake_chunk_from_arrays(
    chunk: ChunkRT,
    chunk_size: int,
    tile_size: int,
    gid_physics: dict[GID, TilePhysicsData],
) -> dict[LayerID, BakedPhysicsChunk]:
    """Bakes physics for one :class:`ChunkRT` from its ``gid_arrays`` cache.

    Performs no re-decoding — the caller is expected to have filled
    ``chunk.gid_arrays`` beforehand.

    Args:
        chunk: Target runtime chunk.
        chunk_size: Number of tiles per chunk side.
        tile_size: Size of one tile edge in pixels.
        gid_physics: Mapping of GID to physics data.

    Returns:
        dict[LayerID, BakedPhysicsChunk]: Baking per layer; layers without
        physics-bearing solid tiles are skipped.
    """
    cx = chunk.chunk_x
    cy = chunk.chunk_y
    world_x = float(cx * chunk_size * tile_size)
    world_y = float(cy * chunk_size * tile_size)

    baked: dict[LayerID, BakedPhysicsChunk] = {}
    for layer_id, gid_array in chunk.gid_arrays.items():
        has_physics = any(gid != 0 and gid in gid_physics for gid in gid_array)
        if not has_physics:
            continue
        bodies = _bake_layer(
            gid_array=gid_array,
            chunk_size=chunk_size,
            tile_size=tile_size,
            chunk_world_x=world_x,
            chunk_world_y=world_y,
            gid_physics=gid_physics,
        )
        if bodies:
            baked[layer_id] = {"bodies": bodies}
    return baked


def bake_all_chunks_runtime(
    config: MapConfig,
) -> dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]]:
    """Bakes physics for the whole map from a runtime :class:`MapConfig`.

    Uses the ``config.chunks[].gid_arrays`` already decoded by
    :meth:`TileMapNode._decode_chunk_layers`.

    Args:
        config: The parsed runtime map configuration.

    Returns:
        dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]]: Baking per chunk,
        per layer. Chunks without any collision are skipped.
    """
    tile_size = config.settings.tile_size[0]
    chunk_size = config.settings.chunk_size
    gid_physics = build_gid_physics_map_runtime(config.tilesets)
    if not gid_physics:
        logger.info("Tidak ada tile dengan data fisika, skip baking.")
        return {}

    result: dict[ChunkKey, dict[LayerID, BakedPhysicsChunk]] = {}
    for chunk_key, chunk in config.chunks.items():
        baked = bake_chunk_from_arrays(chunk, chunk_size, tile_size, gid_physics)
        if baked:
            result[chunk_key] = baked
    logger.info("Physics baking selesai: %d chunk dengan collision data.", len(result))
    return result
