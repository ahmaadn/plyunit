from typing import TYPE_CHECKING

from ._types import (
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
    PhysicsBodyCreateInfo,
    PhysicsHandle,
    PhysicsShape,
    PhysicsStepProfile,
    PolygonShape,
    SegmentShape,
    StaticBody,
)

if TYPE_CHECKING:
    from plyunit.backends.physics import (
        Physics,
        PhysicsArea,
        PhysicsBody,
        PhysicsDebugDraw,
    )

__all__ = (
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
    "Physics",
    "PhysicsArea",
    "PhysicsBody",
    "PhysicsBodyCreateInfo",
    "PhysicsDebugDraw",
    "PhysicsHandle",
    "PhysicsShape",
    "PhysicsStepProfile",
    "PolygonShape",
    "SegmentShape",
    "StaticBody",
)


def __getattr__(name: str):
    if name not in {"Physics", "PhysicsArea", "PhysicsBody", "PhysicsDebugDraw"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends import physics

    value = getattr(physics, name)
    globals()[name] = value
    return value
