"""Physics engine for Plyunit.

Uses pymunk (Chipmunk2D) as the backend, with the following features:
- Collision mask & layer system (32-bit bitmask, Godot-style).
- Spatial hash (pymunk built-in) for broad-phase dynamic entities.
- Quad tree (custom) for static world geometry.
- Sleeping (pymunk built-in) for idle bodies.
- Debug draw component (plug & play).
"""

from __future__ import annotations

try:
    import pymunk  # noqa: F401
except ImportError as exc:  # pragma: no cover - depends on env
    raise ImportError(
        "plyunit physics requires pymunk: uv sync --package plyunit --extra physics"
    ) from exc

from plyunit.core.components.physics import (
    AABB,
    DYNAMIC_ACTOR,
    DYNAMIC_SENSOR_TARGET,
    PROJECTILE,
    SENSOR,
    WORLD_STATIC,
    BodyType,
    BoxShape,
    CircleShape,
    CollisionFilter,
    CollisionInfo,
    PhysicsHandle,
    PhysicsShape,
    PolygonShape,
    SegmentShape,
)

from .debug_draw import PhysicsDebugDraw
from .physics_area import PhysicsArea
from .physics_body import PhysicsBody
from .pymunk_adapter import PhysicsBackend
from .service import Physics
from .static_body import StaticBody

__all__ = [
    # Types
    "AABB",
    "DYNAMIC_ACTOR",
    "DYNAMIC_SENSOR_TARGET",
    "PROJECTILE",
    "SENSOR",
    "WORLD_STATIC",
    "BodyType",
    "BoxShape",
    "CircleShape",
    "CollisionFilter",
    "CollisionInfo",
    # Service & Backend
    "Physics",
    "PhysicsArea",
    "PhysicsBackend",
    # Entities (Components)
    "PhysicsBody",
    # Debug
    "PhysicsDebugDraw",
    "PhysicsHandle",
    # Shapes
    "PhysicsShape",
    "PolygonShape",
    "SegmentShape",
    # Static World
    "StaticBody",
]
