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


def build_physics_service(cfg) -> Physics:
    """Build a ``Physics`` service from a ``PhysicsConfig`` (factory composition root).

    Separates backend parameterization from ``Physics``: the pymunk backend
    is built here and then injected into ``Physics`` via DI.
    """
    backend = PhysicsBackend(
        gravity=cfg.gravity,
        spatial_hash_dim=cfg.spatial_hash_dim,
        spatial_hash_count=cfg.spatial_hash_count,
        sleep_time_threshold=cfg.sleep_time_threshold,
        idle_speed_threshold=cfg.idle_speed_threshold,
        iterations=cfg.iterations,
        damping=cfg.damping,
        enable_spatial_hash=cfg.enable_spatial_hash,
    )
    return Physics(backend, world_bounds=cfg.world_bounds)


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
    # Factory
    "build_physics_service",
]
