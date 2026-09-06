"""Data types for the plyunit map system.

All computation (bitmasks, physics shape baking, collision hulls) may
only happen at the editor level or during on_load. The runtime only
reads pre-baked data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

# ---------------------------------------------------------------------------
# Basic type aliases
# ---------------------------------------------------------------------------

type GID = int
"""Global Tile ID. The value ``0`` represents an empty tile."""

type LayerID = str
"""Layer ID as a string (e.g. ``"1"``, ``"2"``)."""

type ChunkKey = str
"""Chunk key formatted as ``"cx,cy"``, e.g.: ``"0,0"``, ``"-1,2"``."""

type Rect = tuple[float, float, float, float]
"""A rectangle ``(x, y, w, h)``."""

type Vec2 = tuple[float, float]
"""A 2D vector ``(x, y)``."""


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------

PhysicsShapeKind = Literal["box", "polygon", "circle", "none"]
"""Literal of supported collision shape kinds."""


class PhysicsBoxShape(TypedDict):
    """Box (AABB) collision shape.

    Attributes:
        kind: Discriminator, always ``"box"``.
        offset: Offset of the shape's top-left corner relative to the tile (pixels).
        size: Shape size ``(width, height)`` in pixels.
    """

    kind: Literal["box"]
    offset: Vec2
    size: Vec2


class PhysicsPolygonShape(TypedDict):
    """Convex polygon collision shape.

    Attributes:
        kind: Discriminator, always ``"polygon"``.
        vertices: List of polygon vertices (``Vec2``) relative to the tile's
            top-left corner.
    """

    kind: Literal["polygon"]
    vertices: list[Vec2]


class PhysicsCircleShape(TypedDict):
    """Circle collision shape.

    Attributes:
        kind: Discriminator, always ``"circle"``.
        offset: Circle center relative to the tile's top-left corner.
        radius: Circle radius in pixels.
    """

    kind: Literal["circle"]
    offset: Vec2
    radius: float


type PhysicsShape = PhysicsBoxShape | PhysicsPolygonShape | PhysicsCircleShape
"""Union of all physics shape kinds used by the runtime."""


class TilePhysicsData(TypedDict, total=False):
    """Pre-baked physics data for a single tile type (per GID).

    Baked once in the editor/on_load. The runtime just uses it.

    Attributes:
        layer: Physics layer bitmask (e.g. 0b0001 = ground, 0b0010 = platform).
        mask: Physics collision mask — which layers interact with this tile.
        shape: The pre-computed collision shape.
        is_one_way: True = a platform that can be passed through from below.
        friction: Tile surface friction coefficient (0.0-1.0).
        restitution: Bounciness coefficient (0.0-1.0).
    """

    layer: int
    mask: int
    shape: PhysicsShape
    is_one_way: bool
    friction: float
    restitution: float


# ---------------------------------------------------------------------------
# Baked Collision Chunks
# ---------------------------------------------------------------------------


class BakedStaticBody(TypedDict):
    """A single static body merged from several adjacent tiles.

    Baked in the editor using greedy rect merge / convex hull merge.
    The runtime only needs to create one RigidBody per entry.

    Attributes:
        shape: Collision shape (usually a merged box).
        world_pos: World position of the shape's top-left corner (absolute,
            not chunk-relative).
        physics_layer: Layer bitmask.
        physics_mask: Mask bitmask.
        is_one_way: Platform flag.
        friction: Friction coefficient.
        restitution: Bounciness coefficient.
    """

    shape: PhysicsShape
    world_pos: Vec2
    physics_layer: int
    physics_mask: int
    is_one_way: bool
    friction: float
    restitution: float


class BakedPhysicsChunk(TypedDict):
    """A collection of merged static bodies for a single chunk.

    One chunk can yield far fewer bodies than its tile count, because
    identical adjacent tiles are merged.
    """

    bodies: list[BakedStaticBody]


# ---------------------------------------------------------------------------
# Tileset
# ---------------------------------------------------------------------------


class TilesetEntry(TypedDict, total=False):
    """A single tileset entry — maps a GID to an asset and physics data.

    Attributes:
        gid: Global tile ID (must be unique within the map).
        asset_id: Texture asset ID from the Assets service.
        physics: Optional physics data. If absent, the tile has no collider.
    """

    gid: int
    asset_id: str
    physics: TilePhysicsData


# ---------------------------------------------------------------------------
# Layer metadata
# ---------------------------------------------------------------------------


RenderMode = Literal["auto", "baked", "tiles"]
"""Literal of layer render modes: ``"auto"`` (default), ``"baked"`` (RT per
chunk), ``"tiles"`` (per-tile)."""

DEFAULT_RENDER_MODE: RenderMode = "auto"
"""Default :data:`RenderMode` value when a layer does not specify an explicit mode."""


class LayerMeta(TypedDict, total=False):
    """Metadata for a layer.

    Attributes:
        name: Descriptive layer name.
        visible: Whether the layer is drawn.
        opacity: Layer opacity (0.0-1.0).
        z_offset: Extra z-index offset for this layer.
        physics_enabled: Whether this layer participates in physics.
        y_sort_enabled: Per-tile Y-sort (default False). Forces the tiles
            path (cannot be fully baked).
        render_mode: ``"auto"`` | ``"baked"`` | ``"tiles"`` (default auto).
            auto: layer ``"1"`` → baked, other layers → tiles.
            baked: RT per chunk per layer (clamped to tiles if y_sort).
            tiles: always per-tile.
    """

    name: str
    visible: bool
    opacity: float
    z_offset: int
    physics_enabled: bool
    y_sort_enabled: bool
    render_mode: RenderMode


# ---------------------------------------------------------------------------
# Chunk data
# ---------------------------------------------------------------------------


class ChunkData(TypedDict, total=False):
    """Data for a single map chunk.

    Attributes:
        chunk_x: Chunk position in the chunk grid (not pixels).
        chunk_y: Chunk position in the chunk grid.
        layers: Mapping layer_id -> encoded tile array.
        baked_physics: Pre-baked static bodies per layer. Key = layer_id.
        encoding: Encoding override for this chunk.
    """

    chunk_x: int
    chunk_y: int
    layers: dict[LayerID, str | list[int]]
    baked_physics: dict[LayerID, BakedPhysicsChunk]
    encoding: str


# ---------------------------------------------------------------------------
# Object data
# ---------------------------------------------------------------------------


class ObjectData(TypedDict, total=False):
    """Custom object instantiation data within a map.

    Attributes:
        type: Entity type to spawn (e.g. "enemy_goblin", "chest").
        world_x: World X position (pixels).
        world_y: World Y position (pixels).
        properties: Free-form custom attributes for game logic needs.
    """

    type: str
    world_x: float
    world_y: float
    properties: dict[str, object]


# ---------------------------------------------------------------------------
# Map settings
# ---------------------------------------------------------------------------


class MapSettings(TypedDict, total=False):
    """Fundamental map configuration.

    Attributes:
        tile_size: Tile size in pixels [w, h].
        chunk_size: Number of tiles per chunk side (chunks are square).
        encoding: Default tile array encoding format ("csv", "array", "base64_zlib").
        background_color: Background color [R, G, B, A].
    """

    tile_size: list[int]
    chunk_size: int
    encoding: str
    background_color: list[int]


# ---------------------------------------------------------------------------
# Root map config
# ---------------------------------------------------------------------------


MAP_TYPE_ORTHOGONAL: str = "orthogonal"
"""The only supported ``map_type``. The isometric format is not yet implemented."""


class MapConfigData(TypedDict, total=False):
    """Full structure of a JSON map file.

    Attributes:
        version: File format version.
        map_type: Map kind — only ``"orthogonal"`` (default).
        settings: Fundamental configuration.
        tilesets: Mapping of string GID -> TilesetEntry.
        layers: Metadata per layer (``y_sort_enabled``, ``render_mode``, …).
        objects: List of map-level custom objects (spawn points, triggers, etc.).
        chunks: Data per chunk, key = "cx,cy".
    """

    version: str
    map_type: str
    settings: MapSettings
    tilesets: dict[str, TilesetEntry]
    layers: dict[LayerID, LayerMeta]
    objects: list[ObjectData]
    chunks: dict[ChunkKey, ChunkData]


# ---------------------------------------------------------------------------
# Runtime dataclasses (strongly-typed, parsed once in load_map)
# ---------------------------------------------------------------------------


@dataclass
class MapSettingsRT:
    """Fundamental map configuration (runtime, typed)."""

    tile_size: tuple[int, int] = (16, 16)
    chunk_size: int = 16
    encoding: str = "csv"
    background_color: tuple[int, int, int, int] = (0, 0, 0, 255)


@dataclass
class TilesetRuntime:
    """A single tileset entry at runtime — key = GID."""

    gid: GID
    asset_id: str | None = None
    physics: TilePhysicsData | None = None


@dataclass
class ChunkRT:
    """Runtime data for a single chunk.

    ``gid_arrays`` stores decoded (cached) tile arrays so ``get_gid_at``
    is O(1). Filled lazily when first needed (render bake / physics bake
    / query). ``raw_layers`` stores the raw data for re-serialization /
    write-back mutation.
    """

    chunk_x: int = 0
    chunk_y: int = 0
    gid_arrays: dict[LayerID, list[GID]] = field(default_factory=dict)
    baked_physics: dict[LayerID, BakedPhysicsChunk] = field(default_factory=dict)
    encoding: str | None = None
    raw_layers: dict[LayerID, str | list[int]] = field(default_factory=dict)
    decoded: bool = False


@dataclass
class MapConfig:
    """A map parsed into strongly-typed objects.

    Produced once in ``TileMapNode.load_map``. The ``chunks`` field holds
    :class:`ChunkRT` with cached ``gid_arrays``; ``objects`` holds the
    map-level custom objects forwarded to the ``on_objects`` hook.
    """

    version: str = "1"
    map_type: str = "orthogonal"
    settings: MapSettingsRT = field(default_factory=MapSettingsRT)
    tilesets: dict[GID, TilesetRuntime] = field(default_factory=dict)
    layers: dict[LayerID, LayerMeta] = field(default_factory=dict)
    objects: list[ObjectData] = field(default_factory=list)
    chunks: dict[ChunkKey, ChunkRT] = field(default_factory=dict)
    raw: dict = field(default_factory=dict, repr=False, compare=False)
