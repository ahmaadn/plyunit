"""Tilemap module — data structures, autotiling, mesher, physics baking, and the
tilemap node."""

from .autotile import AutotileProcessor
from .encoding import (
    decode_array,
    decode_base64_zlib,
    decode_csv,
    encode_array,
    encode_base64_zlib,
    encode_csv,
)
from .map_data import (
    DEFAULT_RENDER_MODE,
    GID,
    MAP_TYPE_ORTHOGONAL,
    BakedPhysicsChunk,
    BakedStaticBody,
    ChunkData,
    ChunkKey,
    LayerID,
    MapConfigData,
    ObjectData,
    PhysicsBoxShape,
    PhysicsCircleShape,
    PhysicsPolygonShape,
    PhysicsShape,
    RenderMode,
    TilePhysicsData,
    TilesetEntry,
)
from .physics_bridge import TileMapPhysicsBridge
from .tilemap import TileMapNode

__all__ = [
    "DEFAULT_RENDER_MODE",
    "GID",
    "MAP_TYPE_ORTHOGONAL",
    "AutotileProcessor",
    "BakedPhysicsChunk",
    "BakedStaticBody",
    "ChunkData",
    "ChunkKey",
    "LayerID",
    "MapConfigData",
    "ObjectData",
    "PhysicsBoxShape",
    "PhysicsCircleShape",
    "PhysicsPolygonShape",
    "PhysicsShape",
    "RenderMode",
    "TileMapNode",
    "TileMapPhysicsBridge",
    "TilePhysicsData",
    "TilesetEntry",
    "decode_array",
    "decode_base64_zlib",
    "decode_csv",
    "encode_array",
    "encode_base64_zlib",
    "encode_csv",
]
