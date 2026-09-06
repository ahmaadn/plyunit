"""PhysicsArea — sensor/trigger zone component.

A component that detects overlaps without a physical collision response.
Useful for trigger zones, damage zones, pickup areas, etc.

Usage example::

    node.add_component(PhysicsArea(name="DamageZone"))
    area.add_shape(CircleShape(radius=64, is_sensor=True))
    area.on_body_entered.connect(lambda info: print("entered!"))
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pymunk

from plyunit.core.components.component import Component
from plyunit.core.components.physics import CollisionFilter, PhysicsShape
from plyunit.events.signal import Signal

if TYPE_CHECKING:
    from .physics_body import PhysicsBody
    from .service import Physics


class PhysicsArea(Component):
    """Sensor zone for overlap detection.

    Produces no physical collision response (does not push bodies).
    It only detects when other bodies/areas enter or leave this area.

    Automatically registers with Physics when it enters the scene tree.

    Args:
        name: Optional unit name.
    """

    def __init__(
        self,
        name: str | None = None,
    ) -> None:
        """Initialize an empty sensor area with default filters and signals."""
        super().__init__(name=name)

        # Collision shapes — all of them are set as sensors
        self.shapes: list[PhysicsShape] = []

        # Collision filter
        self.filter = CollisionFilter()

        # Monitoring flags
        self.monitoring: bool = True
        """Whether this area detects overlaps (emits signals)?"""

        self.monitorable: bool = True
        """Whether this area can be detected by other areas/bodies?"""

        # --- Signals ---
        self.on_body_entered = Signal("on_body_entered")
        """Emitted when a PhysicsBody enters the area. Args: (PhysicsBody,)"""

        self.on_body_exited = Signal("on_body_exited")
        """Emitted when a PhysicsBody exits the area. Args: (PhysicsBody,)"""

        self.on_area_entered = Signal("on_area_entered")
        """Emitted when another PhysicsArea enters the area. Args: (PhysicsArea,)"""

        self.on_area_exited = Signal("on_area_exited")
        """Emitted when another PhysicsArea exits the area. Args: (PhysicsArea,)"""

        # Tracking of current overlaps
        self._overlapping_bodies: set[PhysicsBody] = set()
        self._overlapping_areas: set[PhysicsArea] = set()

        # Internal pymunk references
        self._pm_body: pymunk.Body | None = None
        self._pm_shapes: list[pymunk.Shape] = []
        self._physics_service: Physics | None = None
        self._physics_handle = None
        self._registered = False

    @classmethod
    def sensor(cls, name: str | None = None) -> PhysicsArea:
        """Create a sensor area (alias for the default constructor)."""
        return cls(name=name)

    @property
    def name(self) -> str:
        """Return the component name."""
        return self._name

    @property
    def transform(self):
        """Return the owning unit's transform.

        Raises:
            RuntimeError: If the area is not attached to a NodeUnit.
        """
        if self.unit is None:
            raise RuntimeError("PhysicsArea must be attached to a NodeUnit")
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
            RuntimeError: If the area is not attached to a NodeUnit.
        """
        if self.unit is None:
            raise RuntimeError("PhysicsArea must be attached to a NodeUnit")
        return self.unit.world_transform_lerp(alpha)

    # ------------------------------------------------------------------
    # Shape Management
    # ------------------------------------------------------------------

    def add_shape(self, shape: PhysicsShape) -> PhysicsShape:
        """Add a collision shape to the area.

        The shape is automatically set as a sensor.

        Args:
            shape: Shape definition.

        Returns:
            The same shape (fluent).
        """
        shape.is_sensor = True  # Force sensor mode
        self.shapes.append(shape)
        if self._registered and self._physics_service is not None:
            self._physics_service._sync_area_shapes(self)
        return shape

    def remove_shape(self, shape: PhysicsShape) -> None:
        """Remove a collision shape from the area."""
        if shape in self.shapes:
            self.shapes.remove(shape)
            if self._registered and self._physics_service is not None:
                self._physics_service._sync_area_shapes(self)

    def clear_shapes(self) -> None:
        """Remove all shapes."""
        self.shapes.clear()
        if self._registered and self._physics_service is not None:
            self._physics_service._sync_area_shapes(self)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_overlapping_bodies(self) -> list[PhysicsBody]:
        """Return the list of PhysicsBody currently overlapping this area."""
        return list(self._overlapping_bodies)

    def get_overlapping_areas(self) -> list[PhysicsArea]:
        """Return the list of other PhysicsArea currently overlapping this area."""
        return list(self._overlapping_areas)

    def has_overlapping_bodies(self) -> bool:
        """Check whether any PhysicsBody is overlapping."""
        return len(self._overlapping_bodies) > 0

    def has_overlapping_areas(self) -> bool:
        """Check whether any other PhysicsArea is overlapping."""
        return len(self._overlapping_areas) > 0

    # ------------------------------------------------------------------
    # Internal — called by Physics
    # ------------------------------------------------------------------

    def _on_body_enter(self, body: PhysicsBody) -> None:
        """Internal: a PhysicsBody entered the area."""
        if not self.monitoring:
            return
        if body not in self._overlapping_bodies:
            self._overlapping_bodies.add(body)
            self.on_body_entered.emit(body)

    def _on_body_exit(self, body: PhysicsBody) -> None:
        """Internal: a PhysicsBody exited the area."""
        if body in self._overlapping_bodies:
            self._overlapping_bodies.discard(body)
            self.on_body_exited.emit(body)

    def _on_area_enter(self, area: PhysicsArea) -> None:
        """Internal: another PhysicsArea entered the area."""
        if not self.monitoring:
            return
        if area is not self and area not in self._overlapping_areas:
            self._overlapping_areas.add(area)
            self.on_area_entered.emit(area)

    def _on_area_exit(self, area: PhysicsArea) -> None:
        """Internal: another PhysicsArea exited the area."""
        if area in self._overlapping_areas:
            self._overlapping_areas.discard(area)
            self.on_area_exited.emit(area)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Recalculate the world transform and register with the Physics service."""
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
                svc.register_area(self)

    def on_destroy(self) -> None:
        """Unregister from the Physics service and clear overlap tracking."""
        if self._physics_service is not None:
            self._physics_service.unregister_area(self)
            self._physics_service = None
        self._overlapping_bodies.clear()
        self._overlapping_areas.clear()

    def destroy(self) -> None:
        """Destroy the component through its unit, or directly when unattached."""
        if self.unit is not None:
            self.unit.destroy_component(self)
        else:
            self.on_destroy()
