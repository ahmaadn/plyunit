"""The ``Component`` base class and the component registry.

Exports ``Component``, ``ComponentNotFoundError``, ``UnitNotSetError``,
``ComponentRegistry``, ``components``, ``builtin``, plus the basic physics
types (``AABB``, ``BodyType``, ``BoxShape``, ``CircleShape``, ``CollisionFilter``,
``CollisionInfo``, ``PhysicsHandle``, ``PhysicsShape``, ``PolygonShape``,
``SegmentShape``, and the filter constants).
"""

from .component import Component, ComponentNotFoundError, UnitNotSetError
from .component_registry import ComponentRegistry, components
from .physics import (
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

__all__ = [
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
    "Component",
    "ComponentNotFoundError",
    "ComponentRegistry",
    "PhysicsHandle",
    "PhysicsShape",
    "PolygonShape",
    "SegmentShape",
    "UnitNotSetError",
    "components",
]
