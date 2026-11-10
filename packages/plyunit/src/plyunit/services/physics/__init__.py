from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

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


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Physics": "plyunit.backends.physics",
        "PhysicsArea": "plyunit.backends.physics",
        "PhysicsBody": "plyunit.backends.physics",
        "PhysicsDebugDraw": "plyunit.backends.physics",
    },
    global_dict=globals(),
    all_exports=__all__,
)
