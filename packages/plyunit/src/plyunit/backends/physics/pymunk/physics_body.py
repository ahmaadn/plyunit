"""PhysicsBody — dynamic/kinematic physics body component.

This component represents an entity with a real collision response in the
physics world. Position is synced two-way between the owning ``NodeUnit``
transform and the pymunk body on every physics step.

Usage example::

    node.add_component(PhysicsBody(body_type=BodyType.DYNAMIC, mass=1.0))
    body.add_shape(CircleShape(radius=16))
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymunk

from plyunit.core.components.component import Component
from plyunit.core.components.physics import (
    BodyType,
    CollisionFilter,
    PhysicsShape,
)
from plyunit.events.signal import Signal

if TYPE_CHECKING:
    from .service import Physics


class PhysicsBody(Component):
    """Physics body with collision response.

    This body automatically registers with Physics when it enters the
    scene tree and unregisters when it leaves.

    Args:
        body_type: Body type (DYNAMIC, KINEMATIC).
            For STATIC, use ``StaticBody`` (not a NodeUnit).
        mass: Body mass (only relevant for DYNAMIC). Default ``1.0``.
        name: Optional component name.
    """

    def __init__(
        self,
        body_type: BodyType = BodyType.DYNAMIC,
        mass: float = 1.0,
        name: str | None = None,
    ) -> None:
        """Initialize a body with its type, mass, default filter, and signals."""
        super().__init__(name=name)

        self.body_type = body_type
        self.mass = max(mass, 0.01)

        # Collision shapes
        self.shapes: list[PhysicsShape] = []

        # Collision filter (layer/mask) — default: layer 1, mask all
        self.filter = CollisionFilter()

        # Physics properties
        self.gravity_scale: float = 1.0
        self.linear_damping: float = 0.0
        self.angular_damping: float = 0.0
        self.fixed_rotation: bool = False

        # --- Signals ---
        self.on_collision_enter = Signal("on_collision_enter")
        """Emitted when a collision begins. Args: (CollisionInfo,)"""

        self.on_collision_exit = Signal("on_collision_exit")
        """Emitted when a collision ends. Args: (other_body,)"""

        # Internal pymunk references — managed by Physics
        self._pm_body: pymunk.Body | None = None
        self._pm_shapes: list[pymunk.Shape] = []
        self._physics_service: Physics | None = None
        self._physics_handle = None

        # Flag: whether it is already registered with the physics service
        self._registered = False

    @classmethod
    def dynamic(cls, mass: float = 1.0, name: str | None = None) -> PhysicsBody:
        """Create a DYNAMIC body with the given mass."""
        return cls(body_type=BodyType.DYNAMIC, mass=mass, name=name)

    @classmethod
    def kinematic(cls, name: str | None = None) -> PhysicsBody:
        """Create a KINEMATIC body."""
        return cls(body_type=BodyType.KINEMATIC, mass=1.0, name=name)

    @property
    def name(self) -> str:
        """Return the component name."""
        return self._name

    @property
    def transform(self):
        """Return the owning unit's transform.

        Raises:
            RuntimeError: If the body is not attached to a NodeUnit.
        """
        if self.unit is None:
            raise RuntimeError("PhysicsBody must be attached to a NodeUnit")
        return self.unit.transform

    @property
    def parent(self):
        """Return the owning unit's parent, or ``None`` when unattached."""
        return None if self.unit is None else self.unit.parent

    def world_transform_lerp(self, alpha: float | None = None):
        """Return the owning unit's world transform, optionally interpolated.

        Args:
            alpha: Interpolation alpha; ``None`` uses the unit's default.

        Raises:
            RuntimeError: If the body is not attached to a NodeUnit.
        """
        if self.unit is None:
            raise RuntimeError("PhysicsBody must be attached to a NodeUnit")
        return self.unit.world_transform_lerp(alpha)

    # ------------------------------------------------------------------
    # Shape Management
    # ------------------------------------------------------------------

    def add_shape(self, shape: PhysicsShape) -> PhysicsShape:
        """Add a collision shape to the body.

        If the body is already registered with Physics, the shape is
        synced to pymunk immediately.

        Args:
            shape: The shape definition to add.

        Returns:
            The same shape (fluent).
        """
        self.shapes.append(shape)
        if self._registered and self._physics_service is not None:
            self._physics_service._sync_body_shapes(self)
        return shape

    def remove_shape(self, shape: PhysicsShape) -> None:
        """Remove a collision shape from the body."""
        if shape in self.shapes:
            self.shapes.remove(shape)
            if self._registered and self._physics_service is not None:
                self._physics_service._sync_body_shapes(self)

    def clear_shapes(self) -> None:
        """Remove all shapes."""
        self.shapes.clear()
        if self._registered and self._physics_service is not None:
            self._physics_service._sync_body_shapes(self)

    # ------------------------------------------------------------------
    # Force & Impulse API
    # ------------------------------------------------------------------

    def apply_force(self, fx: float, fy: float) -> None:
        """Apply a continuous force to the body's center.

        The force is applied on every physics step. For a one-off push,
        use ``apply_impulse()``.
        """
        if self._pm_body is not None:
            self._pm_body.apply_force_at_local_point((fx, fy), (0, 0))

    def apply_force_at_point(self, fx: float, fy: float, px: float, py: float) -> None:
        """Apply a force at a specific world point."""
        if self._pm_body is not None:
            self._pm_body.apply_force_at_world_point((fx, fy), (px, py))

    def apply_impulse(self, ix: float, iy: float) -> None:
        """Apply an impulse (instant push) to the body's center."""
        if self._pm_body is not None:
            self._pm_body.apply_impulse_at_local_point((ix, iy), (0, 0))

    def apply_impulse_at_point(
        self, ix: float, iy: float, px: float, py: float
    ) -> None:
        """Apply an impulse at a specific world point."""
        if self._pm_body is not None:
            self._pm_body.apply_impulse_at_world_point((ix, iy), (px, py))

    # ------------------------------------------------------------------
    # Velocity & State
    # ------------------------------------------------------------------

    @property
    def velocity(self) -> tuple[float, float]:
        """The current linear velocity."""
        if self._pm_body is not None:
            v = self._pm_body.velocity
            return (v.x, v.y)
        return (0.0, 0.0)

    @velocity.setter
    def velocity(self, value: tuple[float, float]) -> None:
        if self._pm_body is not None:
            self._pm_body.velocity = value

    @property
    def angular_velocity(self) -> float:
        """The current angular velocity (degrees/second)."""
        if self._pm_body is not None:
            return math.degrees(self._pm_body.angular_velocity)
        return 0.0

    @angular_velocity.setter
    def angular_velocity(self, value: float) -> None:
        if self._pm_body is not None:
            self._pm_body.angular_velocity = math.radians(value)

    @property
    def is_sleeping(self) -> bool:
        """Check whether the body is currently sleeping."""
        if self._pm_body is not None:
            return self._pm_body.is_sleeping
        return False

    def wake(self) -> None:
        """Wake the body from sleep."""
        if self._pm_body is not None and self._pm_body.is_sleeping:
            self._pm_body.activate()

    def sleep(self) -> None:
        """Force the body to sleep."""
        if self._pm_body is not None and not self._pm_body.is_sleeping:
            self._pm_body.sleep()

    # ------------------------------------------------------------------
    # Lifecycle — auto register/unregister with Physics
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Automatically register with Physics when the owning node starts updating."""
        if self.unit is None:
            return

        if self.transform.dirty:
            parent_world = self.parent.transform.world if self.parent else None
            self.transform.recalc_world(parent_world)
            self.transform.reset_interpolation()

        svc = self.unit.one_or_none("@Physics", scope="global")
        if svc is None:
            svc = self.unit.one_or_none("Physics", scope="global")
        if svc is not None:
            from .service import Physics

            if isinstance(svc, Physics):
                self._physics_service = svc
                svc.register_body(self)

    def on_destroy(self) -> None:
        """Clean up pymunk references when the component is destroyed."""
        if self._physics_service is not None:
            self._physics_service.unregister_body(self)
            self._physics_service = None

    def destroy(self) -> None:
        """Destroy this component through its owning node when possible."""
        if self.unit is not None:
            self.unit.destroy_component(self)
        else:
            self.on_destroy()
