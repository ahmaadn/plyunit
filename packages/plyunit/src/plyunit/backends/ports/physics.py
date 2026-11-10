"""``IPhysics`` — port (Protocol) for the physics service.

Concrete implementations satisfy this Protocol structurally. Components such as
``PhysicsBody``, ``PhysicsArea`` and ``PhysicsDebugDraw`` depend on this port
only, never on a concrete backend.

Backend-specific extras (raw collision callbacks, native spaces, spatial hash
tuning...) are intentionally NOT part of the port.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from plyunit.backends.ports._unit import IServiceUnit
from plyunit.services.physics._types import BodyType

if TYPE_CHECKING:
    from plyunit.services.physics._types import (
        AABB,
        CollisionFilter,
        PhysicsBodyCreateInfo,
        PhysicsHandle,
        PhysicsShape,
        PhysicsStepProfile,
        StaticBody,
    )

__all__ = ("AreaStateView", "BodyStateView", "IPhysics")


class BodyStateView(Protocol):
    """Read-only view of a registered dynamic/kinematic body.

    Backends return their own record type; consumers (debug draw, tools)
    depend only on this structural contract.
    """

    @property
    def handle(self) -> PhysicsHandle: ...

    @property
    def body_type(self) -> BodyType: ...

    @property
    def shape_defs(self) -> list[PhysicsShape]: ...

    @property
    def is_sleeping(self) -> bool: ...

    @property
    def shape_bounds(self) -> Iterable[AABB]:
        """World-space bounds of each shape (for culling / debug draw)."""
        ...

    def state(self) -> tuple[float, float, float]:
        """Return ``(x, y, angle_degrees)``."""
        ...

    def interpolated(self, alpha: float) -> tuple[float, float, float]:
        """Return the render-interpolated ``(x, y, angle_degrees)``."""
        ...


class AreaStateView(Protocol):
    """Read-only view of a registered sensor area."""

    @property
    def handle(self) -> PhysicsHandle: ...

    @property
    def shape_defs(self) -> list[PhysicsShape]: ...

    @property
    def shape_bounds(self) -> Iterable[AABB]: ...

    def state(self) -> tuple[float, float, float]: ...

    def interpolated(self, alpha: float) -> tuple[float, float, float]: ...


@runtime_checkable
class IPhysics[BodyComponent, AreaComponent](IServiceUnit, Protocol):
    """Contract of a physics simulation service."""

    profile_enabled: bool
    last_step_profile: PhysicsStepProfile

    def step(self, dt: float) -> None:
        """Advance the simulation by one fixed step of ``dt`` seconds."""
        ...

    @property
    def gravity(self) -> tuple[float, float]:
        """The current world gravity ``(gx, gy)``."""
        ...

    def set_gravity(self, gx: float, gy: float) -> None: ...

    def set_sleeping(self, enabled: bool, threshold: float = 0.5) -> None: ...

    def set_iterations(self, iterations: int) -> None: ...

    def set_damping(self, damping: float) -> None: ...

    def configure_space(
        self,
        *,
        iterations: int | None = None,
        damping: float | None = None,
        collision_slop: float | None = None,
        collision_bias: float | None = None,
        enable_spatial_hash: bool | None = None,
        spatial_hash_dim: float = 100.0,
        spatial_hash_count: int = 1000,
    ) -> None:
        """Selectively configure the simulation space.

        Options a backend does not support are ignored.
        """
        ...

    def register_body(self, body: BodyComponent) -> None: ...

    def unregister_body(self, body: BodyComponent) -> None: ...

    def register_area(self, area: AreaComponent) -> None: ...

    def unregister_area(self, area: AreaComponent) -> None: ...

    def sync_body_shapes(self, body: BodyComponent) -> None:
        """Re-sync a registered body's shapes after its shape list changed."""
        ...

    def sync_area_shapes(self, area: AreaComponent) -> None:
        """Re-sync a registered area's shapes after its shape list changed."""
        ...

    def create_body(
        self,
        *,
        position: tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        body_type: BodyType = BodyType.DYNAMIC,
        shapes: list[PhysicsShape] | None = None,
        mass: float = 1.0,
        filter: CollisionFilter | None = None,
        fixed_rotation: bool = False,
        gravity_scale: float = 1.0,
        linear_damping: float = 0.0,
        angular_damping: float = 0.0,
        user_data: object = None,
    ) -> PhysicsHandle: ...

    def create_body_batch(
        self, infos: list[PhysicsBodyCreateInfo]
    ) -> list[PhysicsHandle]: ...

    def destroy_body(self, handle: PhysicsHandle) -> None: ...

    def destroy_body_batch(self, handles: list[PhysicsHandle]) -> None: ...

    def destroy_area(self, handle: PhysicsHandle) -> None: ...

    def get_body_state(
        self, handle: PhysicsHandle
    ) -> tuple[float, float, float] | None: ...

    def set_body_state(
        self,
        handle: PhysicsHandle,
        *,
        position: tuple[float, float] | None = None,
        rotation: float | None = None,
        velocity: tuple[float, float] | None = None,
    ) -> None: ...

    def get_position(self, handle: PhysicsHandle) -> tuple[float, float] | None: ...

    def get_rotation(self, handle: PhysicsHandle) -> float | None: ...

    def iter_body_states(self) -> Iterator[BodyStateView]: ...

    def iter_dynamic_states(self) -> Iterator[BodyStateView]: ...

    def iter_area_states(self) -> Iterator[AreaStateView]: ...

    def add_static(self, static: StaticBody) -> None: ...

    def add_static_batch(self, statics: list[StaticBody]) -> None: ...

    def remove_static(self, static_id: int) -> None: ...

    def clear_statics(self) -> None: ...

    def get_static_shape_bounds(self, static: StaticBody) -> Iterable[AABB]:
        """World-space bounds of each shape of a registered static body."""
        ...

    def install_one_way_handler(self) -> None:
        """Enable one-way platform behaviour (``user_data["is_one_way"]``)."""
        ...

    def point_query(
        self,
        x: float,
        y: float,
        max_distance: float = 0.0,
        filter: CollisionFilter | None = None,
    ) -> Sequence[object]: ...

    def ray_cast(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        radius: float = 0.0,
        filter: CollisionFilter | None = None,
    ) -> Sequence[tuple[object, float, tuple[float, float]]]:
        """Return ``(object, alpha, normal)`` hits sorted by distance."""
        ...

    def area_query(
        self, aabb: AABB, filter: CollisionFilter | None = None
    ) -> Sequence[object]: ...

    def query_aabb_fast(
        self, aabb: AABB
    ) -> Sequence[StaticBody | BodyStateView | AreaStateView]: ...

    @property
    def body_count(self) -> int: ...

    @property
    def area_count(self) -> int: ...

    @property
    def static_count(self) -> int: ...

    def get_bodies(self) -> list[BodyComponent]: ...

    def get_areas(self) -> list[AreaComponent]: ...

    def get_statics(self) -> list[StaticBody]: ...

    def iter_contact_points(self) -> Iterable[tuple[float, float]]:
        """Yield current world-space contact points (deduplicated)."""
        ...
