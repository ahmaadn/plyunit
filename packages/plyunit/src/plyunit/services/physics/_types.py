"""Base types and shape definitions for the plyunit physics engine.

Contains AABB, BodyType, CollisionFilter, CollisionInfo, the physics
collision shapes, and the backend-agnostic service data types (StaticBody,
PhysicsStepProfile, PhysicsBodyCreateInfo). This module is pure (does not
depend on any physics backend) so it can be used by core/engine modules
without violating purity.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NewType

_static_id_counter = itertools.count(1)

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
    "PhysicsBodyCreateInfo",
    "PhysicsHandle",
    "PhysicsShape",
    "PhysicsStepProfile",
    "PolygonShape",
    "SegmentShape",
    "StaticBody",
)


class BodyType(Enum):
    """Physics body types supported by the engine.

    Attributes:
        DYNAMIC: Affected by forces and collisions (player, enemy, projectile).
        KINEMATIC: Moves via script but is not affected by forces
            (moving platform, conveyor).
        STATIC: Immovable, never moves (walls, floors).
    """

    DYNAMIC = "dynamic"
    KINEMATIC = "kinematic"
    STATIC = "static"


PhysicsHandle = NewType("PhysicsHandle", int)
"""Opaque handle to a physics body or area managed by the physics backend."""


WORLD_STATIC = 1 << 0
"""Layer bitmask for static world bodies (ground, walls)."""

DYNAMIC_ACTOR = 1 << 1
"""Layer bitmask for dynamic actors (player, enemy)."""

DYNAMIC_SENSOR_TARGET = 1 << 2
"""Layer bitmask for dynamic sensor targets."""

SENSOR = 1 << 3
"""Layer bitmask for sensors (trigger zones, non-solid)."""

PROJECTILE = 1 << 4
"""Layer bitmask for projectiles (bullets, spells)."""


@dataclass(slots=True)
class AABB:
    """Axis-Aligned Bounding Box for spatial queries.

    Attributes:
        min_x: Left edge.
        min_y: Top edge.
        max_x: Right edge.
        max_y: Bottom edge.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        """Width of the box."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Height of the box."""
        return self.max_y - self.min_y

    @property
    def center(self) -> tuple[float, float]:
        """Center point of the box as ``(x, y)``."""
        return (
            (self.min_x + self.max_x) * 0.5,
            (self.min_y + self.max_y) * 0.5,
        )

    def contains_point(self, x: float, y: float) -> bool:
        """Checks whether the point ``(x, y)`` lies inside the box (edges inclusive).

        Args:
            x: X coordinate of the point.
            y: Y coordinate of the point.

        Returns:
            True if the point is inside or on the boundary of the box.
        """
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y

    def intersects(self, other: AABB) -> bool:
        """Checks whether this box overlaps ``other``.

        Args:
            other: The box to test against.

        Returns:
            True if the two boxes overlap (touching edges count as overlap).
        """
        return not (
            other.max_x < self.min_x
            or other.min_x > self.max_x
            or other.max_y < self.min_y
            or other.min_y > self.max_y
        )

    def merge(self, other: AABB) -> AABB:
        """Merges two AABBs into the smallest AABB that encloses both.

        Args:
            other: The box to merge with.

        Returns:
            A new AABB covering both boxes.
        """
        return AABB(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )

    def expand(self, margin: float) -> AABB:
        """Expands the AABB by ``margin`` in every direction.

        Args:
            margin: Amount to push each edge outward by.

        Returns:
            A new, larger AABB.
        """
        return AABB(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )


@dataclass(slots=True)
class CollisionFilter:
    """Collision filter using bitmasks — identical to Godot.

    A collision occurs when:
        ``(A.layer & B.mask) != 0 OR (B.layer & A.mask) != 0``

    Attributes:
        layer: 32-bit bitmask — "I am in these layers".
            Default ``1`` (first bit set).
        mask: 32-bit bitmask — "I want to detect these layers".
            Default ``0xFFFFFFFF`` (all layers enabled).
        group: Collision group — objects in the same group
            never collide with each other. Default ``0`` (no group).
    """

    layer: int = 1
    mask: int = 0xFFFFFFFF
    group: int = 0

    def set_layer_bit(self, bit: int, enabled: bool = True) -> None:
        """Sets a specific bit in the layer (0-31).

        Args:
            bit: Bit index to modify.
            enabled: True to set the bit, False to clear it.

        Raises:
            ValueError: If ``bit`` is outside the range 0-31.
        """
        if not 0 <= bit <= 31:
            raise ValueError("bit must be 0-31")
        if enabled:
            self.layer |= 1 << bit
        else:
            self.layer &= ~(1 << bit)

    def get_layer_bit(self, bit: int) -> bool:
        """Returns whether a specific bit is set in the layer (0-31).

        Args:
            bit: Bit index to check.

        Returns:
            True if the bit is set.

        Raises:
            ValueError: If ``bit`` is outside the range 0-31.
        """
        if not 0 <= bit <= 31:
            raise ValueError("bit must be 0-31")
        return bool(self.layer & (1 << bit))

    def set_mask_bit(self, bit: int, enabled: bool = True) -> None:
        """Sets a specific bit in the mask (0-31).

        Args:
            bit: Bit index to modify.
            enabled: True to set the bit, False to clear it.

        Raises:
            ValueError: If ``bit`` is outside the range 0-31.
        """
        if not 0 <= bit <= 31:
            raise ValueError("bit must be 0-31")
        if enabled:
            self.mask |= 1 << bit
        else:
            self.mask &= ~(1 << bit)

    def get_mask_bit(self, bit: int) -> bool:
        """Returns whether a specific bit is set in the mask (0-31).

        Args:
            bit: Bit index to check.

        Returns:
            True if the bit is set.

        Raises:
            ValueError: If ``bit`` is outside the range 0-31.
        """
        if not 0 <= bit <= 31:
            raise ValueError("bit must be 0-31")
        return bool(self.mask & (1 << bit))

    def can_collide_with(self, other: CollisionFilter) -> bool:
        """Checks whether two filters can collide with each other.

        Args:
            other: The other object's filter.

        Returns:
            True if either filter's layer intersects the other's mask.
        """
        return bool((self.layer & other.mask) or (other.layer & self.mask))

    @classmethod
    def world_static(cls) -> CollisionFilter:
        """Creates a filter for static world geometry.

        Returns:
            A filter on the ``WORLD_STATIC`` layer that detects all layers.
        """
        return cls(layer=WORLD_STATIC, mask=0xFFFFFFFF)

    @classmethod
    def dynamic_actor(cls, *, collide_with_dynamic: bool = False) -> CollisionFilter:
        """Creates a filter for a dynamic actor (player, enemy, etc.).

        Args:
            collide_with_dynamic: If True, the mask also includes the
                ``DYNAMIC_ACTOR`` and ``DYNAMIC_SENSOR_TARGET`` layers.

        Returns:
            A filter on the ``DYNAMIC_ACTOR`` and ``DYNAMIC_SENSOR_TARGET`` layers.
        """
        mask = WORLD_STATIC | SENSOR
        if collide_with_dynamic:
            mask |= DYNAMIC_ACTOR | DYNAMIC_SENSOR_TARGET
        return cls(layer=DYNAMIC_ACTOR | DYNAMIC_SENSOR_TARGET, mask=mask)

    @classmethod
    def sensor(
        cls, mask: int = DYNAMIC_SENSOR_TARGET | DYNAMIC_ACTOR
    ) -> CollisionFilter:
        """Creates a filter for a sensor (trigger zone).

        Args:
            mask: Layers the sensor detects. Defaults to dynamic sensor
                targets and dynamic actors.

        Returns:
            A filter on the ``SENSOR`` layer.
        """
        return cls(layer=SENSOR, mask=mask)


@dataclass
class CollisionInfo:
    """Information about a collision that occurred.

    Attributes:
        other: The other object involved in the collision.
        normal: Collision normal vector (from self toward other).
        points: List of contact points.
        total_impulse: Total impulse applied.
    """

    other: Any = None
    normal: tuple[float, float] = (0.0, 0.0)
    points: list[tuple[float, float]] = field(default_factory=list)
    total_impulse: float = 0.0


@dataclass(kw_only=True)
class PhysicsShape:
    """Base class for physics collision shapes.

    Attributes:
        offset: Position offset of the shape relative to the body center.
        filter: Collision filter (layer/mask) specific to this shape.
            If None, the parent body's filter is used.
        is_sensor: If True, the shape only detects overlaps without a
            physical collision response (trigger zone).
        friction: Surface friction coefficient (0.0 = slippery, 1.0 = rough).
        elasticity: Bounciness coefficient (0.0 = no bounce, 1.0 = perfect bounce).
    """

    offset: tuple[float, float] = (0.0, 0.0)
    filter: CollisionFilter | None = None
    is_sensor: bool = False
    friction: float = 0.5
    elasticity: float = 0.0


@dataclass(kw_only=True)
class CircleShape(PhysicsShape):
    """Circle collision shape.

    Attributes:
        radius: Circle radius.
    """

    radius: float = 16.0


@dataclass(kw_only=True)
class BoxShape(PhysicsShape):
    """Rectangle collision shape.

    Attributes:
        width: Rectangle width.
        height: Rectangle height.
        radius: Corner radius for a rounded rectangle (0 = sharp corners).
    """

    width: float = 32.0
    height: float = 32.0
    radius: float = 0.0


@dataclass(kw_only=True)
class SegmentShape(PhysicsShape):
    """Segment (line) collision shape — from point A to point B, body-relative.

    Attributes:
        a: Start point relative to the body center.
        b: End point relative to the body center.
        radius: Segment thickness (capsule radius).
    """

    a: tuple[float, float] = (0.0, 0.0)
    b: tuple[float, float] = (32.0, 0.0)
    radius: float = 1.0


@dataclass(kw_only=True)
class PolygonShape(PhysicsShape):
    """Convex polygon collision shape.

    Vertices must form a convex polygon wound in counter-clockwise order.
    pymunk automatically computes the convex hull if the polygon is not convex.

    Attributes:
        vertices: List of polygon points relative to the body center.
            At least 3 vertices.
    """

    vertices: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class StaticBody:
    """Static body representation (tile, wall, tree) — NOT a NodeUnit.

    Pure data: native backend objects are tracked by the backend itself
    (keyed by ``id``), never stored on this class.

    Usage example::

        static = StaticBody(
            position=(100, 200),
            shapes=[BoxShape(width=32, height=32)],
        )
        physics.add_static(static)

    Attributes:
        position: World position (x, y).
        shapes: The list of collision shapes that make up this body.
        filter: The default collision filter for all shapes.
        user_data: Custom data that can be attached by the user.
        id: Unique auto-generated ID.
    """

    position: tuple[float, float] = (0.0, 0.0)
    shapes: list[PhysicsShape] = field(default_factory=list)
    filter: CollisionFilter = field(default_factory=CollisionFilter)
    user_data: Any = None
    id: int = field(default_factory=lambda: next(_static_id_counter))


@dataclass(slots=True)
class PhysicsStepProfile:
    """Profiling statistics for a single physics ``step``."""

    pre_sync_ms: float = 0.0
    backend_step_ms: float = 0.0
    post_sync_ms: float = 0.0
    collision_dispatch_ms: float = 0.0
    active_body_count: int = 0
    sleeping_body_count: int = 0
    shape_count: int = 0
    arbiter_count: int = 0

    def as_dict(self) -> dict[str, float]:
        """Convert the profile to a dict (for logging or telemetry)."""
        return {
            "pre_sync_ms": self.pre_sync_ms,
            "backend_step_ms": self.backend_step_ms,
            "post_sync_ms": self.post_sync_ms,
            "collision_dispatch_ms": self.collision_dispatch_ms,
            "active_body_count": float(self.active_body_count),
            "sleeping_body_count": float(self.sleeping_body_count),
            "shape_count": float(self.shape_count),
            "arbiter_count": float(self.arbiter_count),
        }


@dataclass(slots=True)
class PhysicsBodyCreateInfo:
    """Constructor parameters for batch body creation."""

    position: tuple[float, float] = (0.0, 0.0)
    rotation: float = 0.0
    body_type: BodyType = BodyType.DYNAMIC
    shapes: list[PhysicsShape] = field(default_factory=list)
    mass: float = 1.0
    filter: CollisionFilter | None = None
    fixed_rotation: bool = False
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    angular_damping: float = 0.0
    user_data: Any = None
