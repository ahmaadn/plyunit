"""``Physics`` service — global orchestrator for the physics simulation.

Manages:
- ``PhysicsBackend`` (pymunk ``Space`` wrapper)
- Registration/unregistration of ``PhysicsBody`` and ``PhysicsArea``
- ``QuadTree`` for static world geometry
- Position synchronization (pymunk ↔ ``NodeUnit`` transform)
- Collision event dispatch (``Signal``)
- Query API (point, ray, area)

Example:
    >>> physics = Physics(gravity=(0, 900))
    >>> # Static world
    >>> physics.add_static(StaticBody(
    ...     position=(400, 500),
    ...     shapes=[BoxShape(width=800, height=32)],
    ... ))
    >>> # In the scene update:
    >>> physics.step(dt)
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pymunk

from plyunit.core.components.physics import (
    AABB,
    BodyType,
    CollisionFilter,
    CollisionInfo,
    PhysicsHandle,
    PhysicsShape,
)
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils.data_structures.quad_tree import QuadTree

from .physics_area import PhysicsArea
from .physics_body import PhysicsBody
from .pymunk_adapter import PhysicsBackend
from .static_body import StaticBody

if TYPE_CHECKING:
    from plyunit.core.app import App

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PhysicsBodyRecord:
    """Internal record for a registered ``PhysicsBody``."""

    handle: PhysicsHandle
    pm_body: pymunk.Body
    pm_shapes: list[pymunk.Shape]
    shape_defs: list[PhysicsShape]
    owner: PhysicsBody | None
    body_type: BodyType
    mass: float
    filter: CollisionFilter
    user_data: Any = None
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    prev_x: float = 0.0
    prev_y: float = 0.0
    prev_angle: float = 0.0
    fixed_rotation: bool = False
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    angular_damping: float = 0.0

    def state(self) -> tuple[float, float, float]:
        """Return the current state `(x, y, angle)`."""
        return (self.x, self.y, self.angle)

    def interpolated(self, alpha: float) -> tuple[float, float, float]:
        """Return the interpolated state ``(x, y, angle)`` at ``alpha`` in [0, 1]."""
        return (
            self.prev_x + (self.x - self.prev_x) * alpha,
            self.prev_y + (self.y - self.prev_y) * alpha,
            self.prev_angle + (self.angle - self.prev_angle) * alpha,
        )


@dataclass(slots=True)
class PhysicsAreaRecord:
    """Internal record for a registered ``PhysicsArea`` (sensor)."""

    handle: PhysicsHandle
    pm_body: pymunk.Body
    pm_shapes: list[pymunk.Shape]
    shape_defs: list[PhysicsShape]
    owner: PhysicsArea | None
    filter: CollisionFilter
    user_data: Any = None
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    prev_x: float = 0.0
    prev_y: float = 0.0
    prev_angle: float = 0.0


@dataclass(slots=True)
class PhysicsStaticRecord:
    """Internal record for a ``StaticBody`` in the world."""

    static: StaticBody
    aabb: AABB


@dataclass(slots=True)
class PhysicsStepProfile:
    """Profiling statistics for a single physics ``step``."""

    pre_sync_ms: float = 0.0
    pymunk_step_ms: float = 0.0
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
            "pymunk_step_ms": self.pymunk_step_ms,
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


class Physics(ServiceUnit):
    """Global service that manages the entire physics simulation.

    Must be instantiated before PhysicsBody/PhysicsArea enter the scene
    tree. Call ``step(dt)`` on every fixed update (automatic once the
    service is created while ``App`` is active, or via ``init``, thanks
    to ``on_attach``).

    Args:
        backend: A ``PhysicsBackend`` instance (pymunk Space wrapper)
            injected via DI. When ``None``, a default backend is built
            from the following kwargs (legacy path; prefer
            :func:`build_physics_service`).
        gravity: World gravity (gx, gy). Default ``(0, 0)``.
        world_bounds: World bounds for the QuadTree (min_x, min_y, max_x, max_y).
        spatial_hash_dim: pymunk spatial hash cell dimension.
        sleep_time_threshold: Idle time before a body sleeps (0 = disabled).
    """

    @staticmethod
    def create_static_body(**kwargs: Any) -> StaticBody:
        """Create a static body without importing it from the tilemap engine.

        Args:
            **kwargs: Arguments forwarded to ``StaticBody(...)``.

        Returns:
            StaticBody: A new ``StaticBody`` instance.
        """
        return StaticBody(**kwargs)

    def __init__(
        self,
        backend: PhysicsBackend | None = None,
        *,
        world_bounds: tuple[float, float, float, float] = (
            -10000,
            -10000,
            10000,
            10000,
        ),
        gravity: tuple[float, float] = (0.0, 0.0),
        spatial_hash_dim: float = 100.0,
        spatial_hash_count: int = 1000,
        sleep_time_threshold: float = 0.5,
        idle_speed_threshold: float = 10.0,
        iterations: int = 10,
        damping: float = 1.0,
        collision_slop: float | None = None,
        collision_bias: float | None = None,
        enable_spatial_hash: bool = True,
    ) -> None:
        """Initialize the service, its backend, registries, and collision handlers."""
        super().__init__(name="Physics", tags={"service", "physics"})

        # pymunk backend — DI required via the factory; legacy kwargs as fallback.
        self.backend = (
            backend
            if backend is not None
            else PhysicsBackend(
                gravity=gravity,
                spatial_hash_dim=spatial_hash_dim,
                spatial_hash_count=spatial_hash_count,
                sleep_time_threshold=sleep_time_threshold,
                idle_speed_threshold=idle_speed_threshold,
                iterations=iterations,
                damping=damping,
                collision_slop=collision_slop,
                collision_bias=collision_bias,
                enable_spatial_hash=enable_spatial_hash,
            )
        )

        # QuadTree for static world geometry
        self.world_tree: QuadTree[StaticBody] = QuadTree(
            world_bounds[0],
            world_bounds[1],
            world_bounds[2],
            world_bounds[3],
            max_items=8,
            max_depth=10,
        )

        # Entity registration
        self._bodies: dict[int, PhysicsBody] = {}
        self._areas: dict[int, PhysicsArea] = {}
        self._statics: dict[int, StaticBody] = {}
        self._body_records: list[PhysicsBodyRecord] = []
        self._body_handle_to_index: dict[PhysicsHandle, int] = {}
        self._area_records: list[PhysicsAreaRecord] = []
        self._area_handle_to_index: dict[PhysicsHandle, int] = {}
        self._static_records: dict[int, PhysicsStaticRecord] = {}
        self._next_handle = 1

        # Collision tracking — to detect enter/exit (counter per shape pair)
        self._active_collisions: dict[tuple[int, int], int] = {}
        self._active_overlaps: dict[tuple[int, int], int] = {}
        # Additional pre-solve hooks (e.g. one-way platforms) — may set
        # ``arbiter.process_collision = False`` to disable the response.
        self._pre_solve_handlers: list[
            Callable[[pymunk.Arbiter, pymunk.Space, Any], None]
        ] = []
        self.profile_enabled = False
        self.last_step_profile = PhysicsStepProfile()
        self._collision_dispatch_ms = 0.0

        # Set up collision handlers
        self._setup_collision_handlers()

    # ------------------------------------------------------------------
    # Collision Handler Setup
    # ------------------------------------------------------------------

    def _setup_collision_handlers(self) -> None:
        """Register the pymunk collision handlers that dispatch events to
        the service."""
        self.backend.set_default_collision_handler(
            begin=self._on_collision_begin,
            pre_solve=self._on_pre_solve,
            separate=self._on_collision_separate,
        )

    def add_pre_solve_handler(
        self,
        handler: Callable[[pymunk.Arbiter, pymunk.Space, Any], None],
    ) -> None:
        """Register an additional pre-solve callback.

        Used by integrations (e.g.
        :class:`~plyunit.tilemap.TileMapPhysicsBridge` for one-way
        platforms) to selectively disable the collision response via
        ``arbiter.process_collision = False``.
        """
        self._pre_solve_handlers.append(handler)

    def _on_pre_solve(
        self,
        arbiter: pymunk.Arbiter,
        space: pymunk.Space,
        data: Any,
    ) -> None:
        """Dispatch additional pre-solve hooks (e.g. one-way platforms)."""
        if not self._pre_solve_handlers:
            return
        start = time.perf_counter() if self.profile_enabled else 0.0
        try:
            for handler in self._pre_solve_handlers:
                handler(arbiter, space, data)
        finally:
            if self.profile_enabled:
                self._collision_dispatch_ms += (time.perf_counter() - start) * 1000.0

    def _on_collision_begin(
        self,
        arbiter: pymunk.Arbiter,
        space: pymunk.Space,
        data: Any,
    ) -> None:
        """pymunk handler fired when a collision begins (begin callback)."""
        shape_a, shape_b = arbiter.shapes
        body_a_data = getattr(shape_a.body, "data", None)
        body_b_data = getattr(shape_b.body, "data", None)

        if body_a_data is None or body_b_data is None:
            return

        is_a_sensor = shape_a.sensor
        is_b_sensor = shape_b.sensor

        start = time.perf_counter() if self.profile_enabled else 0.0
        try:
            # Sensor overlap (area detection)
            if is_a_sensor or is_b_sensor:
                self._handle_overlap_begin(body_a_data, body_b_data)
                arbiter.process_collision = False  # Sensor: no collision response
                return

            # Physical collision
            self._handle_collision_begin(body_a_data, body_b_data, arbiter)
        finally:
            if self.profile_enabled:
                self._collision_dispatch_ms += (time.perf_counter() - start) * 1000.0

    def _on_collision_separate(
        self,
        arbiter: pymunk.Arbiter,
        space: pymunk.Space,
        data: Any,
    ) -> None:
        """pymunk handler fired when a collision ends (separate callback)."""
        shape_a, shape_b = arbiter.shapes
        body_a_data = getattr(shape_a.body, "data", None)
        body_b_data = getattr(shape_b.body, "data", None)

        if body_a_data is None or body_b_data is None:
            return

        is_a_sensor = shape_a.sensor
        is_b_sensor = shape_b.sensor

        start = time.perf_counter() if self.profile_enabled else 0.0
        try:
            if is_a_sensor or is_b_sensor:
                self._handle_overlap_end(body_a_data, body_b_data)
            else:
                self._handle_collision_end(body_a_data, body_b_data)
        finally:
            if self.profile_enabled:
                self._collision_dispatch_ms += (time.perf_counter() - start) * 1000.0

    @staticmethod
    def _event_target(data: Any) -> Any:
        """Resolve a record to its owner component for event dispatch."""
        return (
            data.owner
            if isinstance(data, (PhysicsBodyRecord, PhysicsAreaRecord))
            else data
        )

    @staticmethod
    def _event_key_part(data: Any) -> int:
        """Return a stable hashable key part (handle or id) for a record or object."""
        if isinstance(data, (PhysicsBodyRecord, PhysicsAreaRecord)):
            return int(data.handle)
        return id(data)

    def _handle_collision_begin(
        self,
        a: PhysicsBody | StaticBody,
        b: PhysicsBody | StaticBody,
        arbiter: pymunk.Arbiter,
    ) -> None:
        """Dispatch a collision-enter event to the owners' ``on_collision_enter``."""
        key = tuple(sorted((self._event_key_part(a), self._event_key_part(b))))
        a = self._event_target(a)
        b = self._event_target(b)

        self._active_collisions[key] = self._active_collisions.get(key, 0) + 1
        if self._active_collisions[key] > 1:
            return

        a_listens = isinstance(a, PhysicsBody) and len(a.on_collision_enter) > 0
        b_listens = isinstance(b, PhysicsBody) and len(b.on_collision_enter) > 0
        if not a_listens and not b_listens:
            return

        contact_points = []
        normal = (0.0, 0.0)
        total_impulse = 0.0
        cs = arbiter.contact_point_set
        if cs.points:
            normal = (cs.normal.x, cs.normal.y)
            for cp in cs.points:
                contact_points.append((cp.point_a.x, cp.point_a.y))
            total_impulse = arbiter.total_impulse.length

        if a_listens:
            info_a = CollisionInfo(
                other=b,
                normal=normal,
                points=contact_points,
                total_impulse=total_impulse,
            )
            a.on_collision_enter.emit(info_a)

        if b_listens:
            inv_normal = (-normal[0], -normal[1])
            info_b = CollisionInfo(
                other=a,
                normal=inv_normal,
                points=contact_points,
                total_impulse=total_impulse,
            )
            b.on_collision_enter.emit(info_b)

    def _handle_collision_end(
        self, a: PhysicsBody | StaticBody, b: PhysicsBody | StaticBody
    ) -> None:
        """Dispatch a collision-exit event to the owning ``PhysicsBody``."""
        key = tuple(sorted((self._event_key_part(a), self._event_key_part(b))))
        a = self._event_target(a)
        b = self._event_target(b)

        if key not in self._active_collisions:
            return

        self._active_collisions[key] -= 1
        if self._active_collisions[key] > 0:
            return

        del self._active_collisions[key]

        if isinstance(a, PhysicsBody):
            a.on_collision_exit.emit(b)
        if isinstance(b, PhysicsBody):
            b.on_collision_exit.emit(a)

    def _handle_overlap_begin(
        self,
        a: PhysicsBody | PhysicsArea | StaticBody,
        b: PhysicsBody | PhysicsArea | StaticBody,
    ) -> None:
        """Dispatch a (sensor) overlap-enter event to the ``PhysicsArea``."""
        key = tuple(sorted((self._event_key_part(a), self._event_key_part(b))))
        a = self._event_target(a)
        b = self._event_target(b)

        self._active_overlaps[key] = self._active_overlaps.get(key, 0) + 1
        if self._active_overlaps[key] > 1:
            return

        # Area ↔ Body
        if isinstance(a, PhysicsArea) and isinstance(b, PhysicsBody):
            a._on_body_enter(b)
        elif isinstance(a, PhysicsBody) and isinstance(b, PhysicsArea):
            b._on_body_enter(a)
        # Area ↔ Area
        elif isinstance(a, PhysicsArea) and isinstance(b, PhysicsArea):
            a._on_area_enter(b)
            b._on_area_enter(a)

    def _handle_overlap_end(
        self,
        a: PhysicsBody | PhysicsArea | StaticBody,
        b: PhysicsBody | PhysicsArea | StaticBody,
    ) -> None:
        """Dispatch a (sensor) overlap-exit event to the ``PhysicsArea``."""
        key = tuple(sorted((self._event_key_part(a), self._event_key_part(b))))
        a = self._event_target(a)
        b = self._event_target(b)

        if key not in self._active_overlaps:
            return

        self._active_overlaps[key] -= 1
        if self._active_overlaps[key] > 0:
            return

        del self._active_overlaps[key]

        if isinstance(a, PhysicsArea) and isinstance(b, PhysicsBody):
            a._on_body_exit(b)
        elif isinstance(a, PhysicsBody) and isinstance(b, PhysicsArea):
            b._on_body_exit(a)
        elif isinstance(a, PhysicsArea) and isinstance(b, PhysicsArea):
            a._on_area_exit(b)
            b._on_area_exit(a)

    # ------------------------------------------------------------------
    # Entity Registration
    # ------------------------------------------------------------------

    def _new_handle(self) -> PhysicsHandle:
        """Create a new ``PhysicsHandle`` with an incrementing ID."""
        handle = PhysicsHandle(self._next_handle)
        self._next_handle += 1
        return handle

    def _body_record_for_owner(self, owner: PhysicsBody) -> PhysicsBodyRecord | None:
        """Find the ``PhysicsBodyRecord`` for ``owner`` (or ``None``)."""
        handle = getattr(owner, "_physics_handle", None)
        if handle is None:
            return None
        index = self._body_handle_to_index.get(handle)
        return None if index is None else self._body_records[index]

    def _area_record_for_owner(self, owner: PhysicsArea) -> PhysicsAreaRecord | None:
        """Find the ``PhysicsAreaRecord`` for ``owner`` (or ``None``)."""
        handle = getattr(owner, "_physics_handle", None)
        if handle is None:
            return None
        index = self._area_handle_to_index.get(handle)
        return None if index is None else self._area_records[index]

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
        user_data: Any = None,
    ) -> PhysicsHandle:
        """Create an ownerless body and return its stable handle."""
        record = self._create_body_record(
            position=position,
            rotation=rotation,
            body_type=body_type,
            shapes=shapes or [],
            mass=mass,
            filter=filter,
            fixed_rotation=fixed_rotation,
            gravity_scale=gravity_scale,
            linear_damping=linear_damping,
            angular_damping=angular_damping,
            owner=None,
            user_data=user_data,
        )
        return record.handle

    def create_body_batch(
        self, infos: list[PhysicsBodyCreateInfo]
    ) -> list[PhysicsHandle]:
        """Create many ownerless bodies in a single call.

        Args:
            infos: The list of ``PhysicsBodyCreateInfo``.

        Returns:
            list[PhysicsHandle]: The handle for each created body.
        """
        return [
            self.create_body(
                position=info.position,
                rotation=info.rotation,
                body_type=info.body_type,
                shapes=info.shapes,
                mass=info.mass,
                filter=info.filter,
                fixed_rotation=info.fixed_rotation,
                gravity_scale=info.gravity_scale,
                linear_damping=info.linear_damping,
                angular_damping=info.angular_damping,
                user_data=info.user_data,
            )
            for info in infos
        ]

    def _create_body_record(
        self,
        *,
        position: tuple[float, float],
        rotation: float,
        body_type: BodyType,
        shapes: list[PhysicsShape],
        mass: float,
        filter: CollisionFilter | None,
        fixed_rotation: bool,
        gravity_scale: float,
        linear_damping: float,
        angular_damping: float,
        owner: PhysicsBody | None,
        user_data: Any,
    ) -> PhysicsBodyRecord:
        """Create a pymunk body, its shapes, and its registered record."""
        if body_type == BodyType.DYNAMIC:
            moment = PhysicsBackend.calculate_moment_for_shapes(max(mass, 0.01), shapes)
            pm_body = self.backend.create_dynamic_body(
                mass=max(mass, 0.01),
                moment=moment,
                position=position,
                angle=math.radians(rotation),
            )
        elif body_type == BodyType.KINEMATIC:
            pm_body = self.backend.create_kinematic_body(
                position=position,
                angle=math.radians(rotation),
            )
        else:
            raise ValueError("create_body only supports DYNAMIC and KINEMATIC bodies")

        if fixed_rotation:
            pm_body.moment = float("inf")

        body_filter = filter if filter is not None else CollisionFilter.dynamic_actor()
        handle = self._new_handle()
        record = PhysicsBodyRecord(
            handle=handle,
            pm_body=pm_body,
            pm_shapes=[],
            shape_defs=shapes,
            owner=owner,
            body_type=body_type,
            mass=max(mass, 0.01),
            filter=body_filter,
            user_data=user_data,
            x=float(position[0]),
            y=float(position[1]),
            angle=float(rotation),
            prev_x=float(position[0]),
            prev_y=float(position[1]),
            prev_angle=float(rotation),
            fixed_rotation=fixed_rotation,
            gravity_scale=gravity_scale,
            linear_damping=linear_damping,
            angular_damping=angular_damping,
        )
        pm_body.data = record
        for shape_def in shapes:
            record.pm_shapes.append(
                self.backend.add_shape_to_body(pm_body, shape_def, body_filter)
            )
        self._body_handle_to_index[handle] = len(self._body_records)
        self._body_records.append(record)
        return record

    def destroy_body(self, handle: PhysicsHandle) -> None:
        """Remove a body and clean up its collision tracking.

        Args:
            handle: The handle of the body to remove.
        """
        index = self._body_handle_to_index.pop(handle, None)
        if index is None:
            return
        record = self._body_records[index]
        self.backend.remove_body(record.pm_body)
        if record.owner is not None:
            record.owner._pm_body = None
            record.owner._pm_shapes.clear()
            record.owner._registered = False
            record.owner._physics_handle = None
            self._bodies.pop(id(record.owner), None)
        last = self._body_records.pop()
        if index < len(self._body_records):
            self._body_records[index] = last
            self._body_handle_to_index[last.handle] = index
        self._active_collisions = {
            k: v for k, v in self._active_collisions.items() if int(handle) not in k
        }
        self._active_overlaps = {
            k: v for k, v in self._active_overlaps.items() if int(handle) not in k
        }

    def destroy_body_batch(self, handles: list[PhysicsHandle]) -> None:
        """Remove many bodies from the service.

        Args:
            handles: The list of body handles to remove.
        """
        for handle in handles:
            self.destroy_body(handle)

    def get_body_state(
        self, handle: PhysicsHandle
    ) -> tuple[float, float, float] | None:
        """Return the body's state ``(x, y, angle)``, or ``None`` when absent.

        Args:
            handle: The body handle.

        Returns:
            The tuple ``(x, y, angle)`` or ``None``.
        """
        index = self._body_handle_to_index.get(handle)
        if index is None:
            return None
        return self._body_records[index].state()

    def set_body_state(
        self,
        handle: PhysicsHandle,
        *,
        position: tuple[float, float] | None = None,
        rotation: float | None = None,
        velocity: tuple[float, float] | None = None,
    ) -> None:
        """Partially set the body's state (position/rotation/velocity are optional).

        Args:
            handle: The body handle.
            position: The new position ``(x, y)`` (optional).
            rotation: The new angle in degrees (optional).
            velocity: The new linear velocity ``(vx, vy)`` (optional).
        """
        index = self._body_handle_to_index.get(handle)
        if index is None:
            return
        record = self._body_records[index]
        if position is not None:
            record.pm_body.position = position
            record.prev_x = record.x = float(position[0])
            record.prev_y = record.y = float(position[1])
        if rotation is not None:
            record.pm_body.angle = math.radians(rotation)
            record.prev_angle = record.angle = float(rotation)
        if velocity is not None:
            record.pm_body.velocity = velocity

    def get_position(self, handle: PhysicsHandle) -> tuple[float, float] | None:
        """Return the body's position ``(x, y)``, or ``None`` when absent.

        Args:
            handle: The body handle.

        Returns:
            The tuple ``(x, y)`` or ``None``.
        """
        state = self.get_body_state(handle)
        return None if state is None else (state[0], state[1])

    def get_rotation(self, handle: PhysicsHandle) -> float | None:
        """Return the body's angle (degrees), or ``None`` when absent.

        Args:
            handle: The body handle.

        Returns:
            The angle in degrees, or ``None``.
        """
        state = self.get_body_state(handle)
        return None if state is None else state[2]

    def iter_body_states(self):
        """Iterate over all ``PhysicsBodyRecord`` (dynamic + kinematic)."""
        return iter(self._body_records)

    def iter_dynamic_states(self):
        """Iterate over only the dynamic ``PhysicsBodyRecord``."""
        return (r for r in self._body_records if r.body_type == BodyType.DYNAMIC)

    @staticmethod
    def _query_target(data: Any) -> Any:
        """Resolve a record to its owner (or the record itself when ownerless)."""
        if isinstance(data, (PhysicsBodyRecord, PhysicsAreaRecord)):
            return data.owner if data.owner is not None else data
        return data

    def _create_area_record(
        self,
        *,
        position: tuple[float, float],
        rotation: float,
        shapes: list[PhysicsShape],
        filter: CollisionFilter | None,
        owner: PhysicsArea | None,
        user_data: Any,
    ) -> PhysicsAreaRecord:
        """Create a kinematic sensor body, its shapes, and its registered record."""
        pm_body = self.backend.create_kinematic_body(
            position=position,
            angle=math.radians(rotation),
        )
        area_filter = filter if filter is not None else CollisionFilter.sensor()
        handle = self._new_handle()
        record = PhysicsAreaRecord(
            handle=handle,
            pm_body=pm_body,
            pm_shapes=[],
            shape_defs=shapes,
            owner=owner,
            filter=area_filter,
            user_data=user_data,
            x=float(position[0]),
            y=float(position[1]),
            angle=float(rotation),
            prev_x=float(position[0]),
            prev_y=float(position[1]),
            prev_angle=float(rotation),
        )
        pm_body.data = record
        for shape_def in shapes:
            shape_def.is_sensor = True
            record.pm_shapes.append(
                self.backend.add_shape_to_body(pm_body, shape_def, area_filter)
            )
        self._area_handle_to_index[handle] = len(self._area_records)
        self._area_records.append(record)
        return record

    def destroy_area(self, handle: PhysicsHandle) -> None:
        """Remove a sensor area and clean up its overlap tracking.

        Args:
            handle: The handle of the area to remove.
        """
        index = self._area_handle_to_index.pop(handle, None)
        if index is None:
            return
        record = self._area_records[index]
        self.backend.remove_body(record.pm_body)
        if record.owner is not None:
            record.owner._pm_body = None
            record.owner._pm_shapes.clear()
            record.owner._registered = False
            record.owner._physics_handle = None
            self._areas.pop(id(record.owner), None)
        last = self._area_records.pop()
        if index < len(self._area_records):
            self._area_records[index] = last
            self._area_handle_to_index[last.handle] = index
        self._active_overlaps = {
            k: v for k, v in self._active_overlaps.items() if int(handle) not in k
        }

    def register_body(self, body: PhysicsBody) -> None:
        """Register a ``PhysicsBody`` with the physics simulation.

        Called automatically by ``PhysicsBody.on_enter_tree()``.

        Args:
            body: The ``PhysicsBody`` to register.
        """
        if body._registered:
            return

        world_pos = body.transform.world.position
        record = self._create_body_record(
            position=world_pos,
            rotation=body.transform.world.rotation,
            body_type=body.body_type,
            shapes=body.shapes,
            mass=body.mass,
            filter=body.filter,
            fixed_rotation=body.fixed_rotation,
            gravity_scale=body.gravity_scale,
            linear_damping=body.linear_damping,
            angular_damping=body.angular_damping,
            owner=body,
            user_data=body,
        )

        body._pm_body = record.pm_body
        body._pm_shapes = record.pm_shapes
        body._physics_handle = record.handle
        body._registered = True
        body_id = id(body)
        self._bodies[body_id] = body
        logger.debug("Registered PhysicsBody '%s' (id=%d)", body.name, body_id)

    def unregister_body(self, body: PhysicsBody) -> None:
        """Unregister a ``PhysicsBody`` from the simulation.

        Called automatically by ``PhysicsBody.on_exit_tree()`` or ``destroy()``.

        Args:
            body: The ``PhysicsBody`` to detach.
        """
        if not body._registered:
            return

        handle = getattr(body, "_physics_handle", None)
        if handle is not None:
            self.destroy_body(handle)
        else:
            body._pm_body = None
            body._pm_shapes.clear()
            body._registered = False
            self._bodies.pop(id(body), None)

        # Cleanup collision tracking
        body_id = id(body)
        to_remove = [k for k in self._active_collisions if body_id in k]
        for k in to_remove:
            self._active_collisions.pop(k, None)

        logger.debug("Unregistered PhysicsBody '%s' (id=%d)", body.name, body_id)

    def register_area(self, area: PhysicsArea) -> None:
        """Register a ``PhysicsArea`` with the physics simulation.

        Args:
            area: The ``PhysicsArea`` (sensor) to register.
        """
        if area._registered:
            return

        world_pos = area.transform.world.position
        record = self._create_area_record(
            position=world_pos,
            rotation=area.transform.world.rotation,
            shapes=area.shapes,
            filter=area.filter,
            owner=area,
            user_data=area,
        )
        area._pm_body = record.pm_body
        area._pm_shapes = record.pm_shapes
        area._physics_handle = record.handle
        area._registered = True
        area_id = id(area)
        self._areas[area_id] = area
        logger.debug("Registered PhysicsArea '%s' (id=%d)", area.name, area_id)

    def unregister_area(self, area: PhysicsArea) -> None:
        """Unregister a ``PhysicsArea`` from the simulation.

        Args:
            area: The ``PhysicsArea`` to detach.
        """
        if not area._registered:
            return

        handle = getattr(area, "_physics_handle", None)
        if handle is not None:
            self.destroy_area(handle)
        else:
            area._pm_body = None
            area._pm_shapes.clear()
            area._registered = False
            self._areas.pop(id(area), None)

        # Cleanup overlap tracking
        area_id = id(area)
        to_remove = [k for k in self._active_overlaps if area_id in k]
        for k in to_remove:
            self._active_overlaps.pop(k, None)

        logger.debug("Unregistered PhysicsArea '%s' (id=%d)", area.name, area_id)

    def _sync_body_shapes(self, body: PhysicsBody) -> None:
        """Re-sync a ``PhysicsBody``'s shapes to pymunk after its shape list changed.

        Args:
            body: The ``PhysicsBody`` whose shapes will be re-synced.
        """
        if body._pm_body is None:
            return

        # Remove old shapes
        for old_shape in body._pm_shapes:
            self.backend.remove_shape(old_shape)
        body._pm_shapes.clear()
        record = self._body_record_for_owner(body)
        if record is not None:
            record.pm_shapes.clear()
            record.shape_defs = body.shapes

        # Recalculate moment for dynamic bodies
        if body.body_type == BodyType.DYNAMIC:
            moment = PhysicsBackend.calculate_moment_for_shapes(body.mass, body.shapes)
            body._pm_body.moment = moment

        # Create new shapes
        for shape_def in body.shapes:
            pm_shape = self.backend.add_shape_to_body(
                body._pm_body, shape_def, body.filter
            )
            body._pm_shapes.append(pm_shape)
            if record is not None:
                record.pm_shapes.append(pm_shape)

    def _sync_area_shapes(self, area: PhysicsArea) -> None:
        """Re-sync a ``PhysicsArea``'s shapes to pymunk after its shape list changed.

        Args:
            area: The ``PhysicsArea`` whose shapes will be re-synced.
        """
        if area._pm_body is None:
            return

        for old_shape in area._pm_shapes:
            self.backend.remove_shape(old_shape)
        area._pm_shapes.clear()
        record = self._area_record_for_owner(area)
        if record is not None:
            record.pm_shapes.clear()
            record.shape_defs = area.shapes

        for shape_def in area.shapes:
            shape_def.is_sensor = True
            pm_shape = self.backend.add_shape_to_body(
                area._pm_body, shape_def, area.filter
            )
            area._pm_shapes.append(pm_shape)
            if record is not None:
                record.pm_shapes.append(pm_shape)

    # ------------------------------------------------------------------
    # App Integration
    # ------------------------------------------------------------------

    def on_attach(self, app: App) -> None:
        """Hook invoked by the registry once the service has been created.

        Subscribes to ``app.on_fixed_update`` (after the scene update +
        transform sync) so that ``step(dt)`` runs once per fixed tick.
        **Do not** also call ``step`` from ``update()`` (it would double-step).

        Args:
            app: The App this service is attached to.
        """
        app.on_fixed_update.connect(self._on_fixed_update)

    def _on_fixed_update(self, dt: float) -> None:
        """Fixed tick hook: delegates to ``step(dt)``."""
        self.step(dt)

    # ------------------------------------------------------------------
    # Static World Management
    # ------------------------------------------------------------------

    def add_static(self, static: StaticBody) -> None:
        """Add a ``StaticBody`` to the world.

        The static body is inserted into the ``QuadTree`` AND into
        ``pymunk.Space``.

        Args:
            static: The static body to add.
        """
        static_id = static.id
        if static_id in self._statics:
            return

        # Create the pymunk static body
        pm_body = self.backend.create_static_body(
            position=static.position,
        )
        pm_body.data = static
        static._pm_body = pm_body

        pm_shapes = []
        for shape_def in static.shapes:
            pm_shape = self.backend.add_shape_to_body(pm_body, shape_def, static.filter)
            pm_shapes.append(pm_shape)
        static._pm_shapes = pm_shapes

        # Insert into the QuadTree
        aabb = self._compute_static_aabb(static)
        self.world_tree.insert(static, aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y)

        self._statics[static_id] = static
        self._static_records[static_id] = PhysicsStaticRecord(static=static, aabb=aabb)
        logger.debug("Added static body id=%d at %s", static_id, static.position)

    def add_static_batch(self, statics: list[StaticBody]) -> None:
        """Add many static bodies at once.

        Args:
            statics: The list of static bodies.
        """
        for s in statics:
            self.add_static(s)

    def remove_static(self, static_id: int) -> None:
        """Remove a static body by ID.

        Args:
            static_id: The ID of the static body to remove.
        """
        static = self._statics.pop(static_id, None)
        if static is None:
            return

        if static._pm_body is not None:
            self.backend.remove_body(static._pm_body)
        static._pm_body = None
        static._pm_shapes.clear()

        self.world_tree.remove(static)
        self._static_records.pop(static_id, None)

    def clear_statics(self) -> None:
        """Remove all static bodies from the world."""
        for static in list(self._statics.values()):
            if static._pm_body is not None:
                self.backend.remove_body(static._pm_body)
            static._pm_body = None
            static._pm_shapes.clear()
        self._statics.clear()
        self._static_records.clear()
        self.world_tree.clear()

    def _compute_static_aabb(self, static: StaticBody) -> AABB:
        """Compute a static body's AABB from its position + shapes.

        Args:
            static: The source static body.

        Returns:
            AABB: The world-space bounding box. Falls back to 1x1 when
            there are no shapes.
        """
        from plyunit.core.components.physics import (
            BoxShape,
            CircleShape,
            PolygonShape,
            SegmentShape,
        )

        px, py = static.position
        min_x = px
        min_y = py
        max_x = px
        max_y = py

        for shape in static.shapes:
            ox, oy = shape.offset
            if isinstance(shape, CircleShape):
                r = shape.radius
                min_x = min(min_x, px + ox - r)
                min_y = min(min_y, py + oy - r)
                max_x = max(max_x, px + ox + r)
                max_y = max(max_y, py + oy + r)
            elif isinstance(shape, BoxShape):
                hw, hh = shape.width / 2, shape.height / 2
                min_x = min(min_x, px + ox - hw)
                min_y = min(min_y, py + oy - hh)
                max_x = max(max_x, px + ox + hw)
                max_y = max(max_y, py + oy + hh)
            elif isinstance(shape, SegmentShape):
                ax, ay = shape.a
                bx, by = shape.b
                r = shape.radius
                min_x = min(min_x, px + ox + ax - r, px + ox + bx - r)
                min_y = min(min_y, py + oy + ay - r, py + oy + by - r)
                max_x = max(max_x, px + ox + ax + r, px + ox + bx + r)
                max_y = max(max_y, py + oy + ay + r, py + oy + by + r)
            elif isinstance(shape, PolygonShape):
                for vx, vy in shape.vertices:
                    min_x = min(min_x, px + ox + vx)
                    min_y = min(min_y, py + oy + vy)
                    max_x = max(max_x, px + ox + vx)
                    max_y = max(max_y, py + oy + vy)

        # Fallback: when there are no shapes, use a minimal 1x1 AABB
        if min_x == max_x and min_y == max_y:
            return AABB(px - 0.5, py - 0.5, px + 0.5, py + 0.5)

        return AABB(min_x, min_y, max_x, max_y)

    # ------------------------------------------------------------------
    # Simulation Step
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance the physics simulation by one step.

        Workflow:
        1. Sync positions from NodeUnit transform → pymunk (kinematic bodies + areas)
        2. Step the pymunk space
        3. Sync positions from pymunk → NodeUnit transform (dynamic bodies)

        Normally invoked by the service through ``App.on_fixed_update``. Call it
        manually only when the service is not attached to an App.

        Args:
            dt: Fixed delta time (seconds).
        """
        if dt <= 0:
            return

        self._collision_dispatch_ms = 0.0
        pre_start = time.perf_counter() if self.profile_enabled else 0.0
        self._pre_step_sync(dt)
        pre_ms = (
            (time.perf_counter() - pre_start) * 1000.0 if self.profile_enabled else 0.0
        )

        step_start = time.perf_counter() if self.profile_enabled else 0.0
        self.backend.step(dt)
        pymunk_ms = (
            (time.perf_counter() - step_start) * 1000.0 if self.profile_enabled else 0.0
        )

        post_start = time.perf_counter() if self.profile_enabled else 0.0
        self._post_step_sync()
        post_ms = (
            (time.perf_counter() - post_start) * 1000.0 if self.profile_enabled else 0.0
        )

        if self.profile_enabled:
            self.last_step_profile = PhysicsStepProfile(
                pre_sync_ms=pre_ms,
                pymunk_step_ms=pymunk_ms,
                post_sync_ms=post_ms,
                collision_dispatch_ms=self._collision_dispatch_ms,
                active_body_count=len(self._body_records),
                sleeping_body_count=sum(
                    1 for r in self._body_records if r.pm_body.is_sleeping
                ),
                shape_count=sum(len(r.pm_shapes) for r in self._body_records)
                + sum(len(r.pm_shapes) for r in self._area_records)
                + sum(len(s._pm_shapes) for s in self._statics.values()),
                arbiter_count=len(self._active_collisions) + len(self._active_overlaps),
            )

    def _pre_step_sync(self, dt: float) -> None:
        """Sync ``NodeUnit`` transforms → pymunk bodies (kinematic + areas)."""
        for record in self._body_records:
            body = record.owner
            pm_body = record.pm_body

            if record.body_type == BodyType.KINEMATIC and body is not None:
                # Kinematic: calculate velocity from transform change
                target_pos = body.transform.world.position
                current_pos = pm_body.position

                dx = target_pos[0] - current_pos[0]
                dy = target_pos[1] - current_pos[1]

                if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                    pm_body.velocity = (dx / dt, dy / dt)
                elif pm_body.velocity != (0.0, 0.0):
                    pm_body.velocity = (0.0, 0.0)

                target_rot = math.radians(body.transform.world.rotation)
                current_rot = pm_body.angle
                diff = (target_rot - current_rot + math.pi) % (2 * math.pi) - math.pi
                if abs(diff) > 1e-4:
                    pm_body.angular_velocity = diff / dt
                elif pm_body.angular_velocity != 0.0:
                    pm_body.angular_velocity = 0.0

            elif record.body_type == BodyType.DYNAMIC:
                # Apply gravity scale
                if record.gravity_scale != 1.0:
                    gx, gy = self.backend.gravity
                    scale_diff = record.gravity_scale - 1.0
                    pm_body.apply_force_at_local_point(
                        (gx * scale_diff * record.mass, gy * scale_diff * record.mass),
                        (0, 0),
                    )

                # Apply damping
                if record.linear_damping > 0:
                    v = pm_body.velocity
                    damp = max(0, 1.0 - record.linear_damping * dt)
                    pm_body.velocity = (v.x * damp, v.y * damp)

                if record.angular_damping > 0:
                    av = pm_body.angular_velocity
                    damp = max(0, 1.0 - record.angular_damping * dt)
                    pm_body.angular_velocity = av * damp

        # Sync area positions
        for record in self._area_records:
            area = record.owner
            if area is None:
                continue
            target_pos = area.transform.world.position
            current_pos = record.pm_body.position

            dx = target_pos[0] - current_pos[0]
            dy = target_pos[1] - current_pos[1]
            if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                record.pm_body.velocity = (dx / dt, dy / dt)
            elif record.pm_body.velocity != (0.0, 0.0):
                record.pm_body.velocity = (0.0, 0.0)

            target_rot = math.radians(area.transform.world.rotation)
            current_rot = record.pm_body.angle
            diff = (target_rot - current_rot + math.pi) % (2 * math.pi) - math.pi
            if abs(diff) > 1e-4:
                record.pm_body.angular_velocity = diff / dt
            elif record.pm_body.angular_velocity != 0.0:
                record.pm_body.angular_velocity = 0.0

    def _post_step_sync(self) -> None:
        """Sync pymunk bodies → ``NodeUnit`` transforms (dynamic bodies)."""
        moved_owners: list = []
        for record in self._body_records:
            pm_pos = record.pm_body.position
            pm_rot = math.degrees(record.pm_body.angle)
            record.prev_x = record.x
            record.prev_y = record.y
            record.prev_angle = record.angle
            record.x = pm_pos.x
            record.y = pm_pos.y
            record.angle = pm_rot

            body = record.owner
            if record.body_type == BodyType.DYNAMIC and body is not None:
                parent = body.parent
                pw = parent.transform.world if parent is not None else None

                local_x, local_y, local_rot = self._world_to_local_state(
                    pm_pos.x,
                    pm_pos.y,
                    pm_rot,
                    pw,
                )
                body.transform.apply_physics_state(
                    (local_x, local_y),
                    local_rot,
                    (record.x, record.y),
                    record.angle,
                    (record.prev_x, record.prev_y),
                    record.prev_angle,
                    previous_world_scale=body.transform.world.scale,
                )
                moved_owners.append(body)

        # incremental SpatialIndex — physics movers bypass transform dirty
        # (apply_physics_state clears _dirty), so a dirty-only spatial flush
        # would miss them. Mark them dirty here so spatial queries reflect the
        # new post-step positions before the next render / query.
        if moved_owners:
            spatial = self.one_or_none("@SpatialIndex", scope="global")
            if spatial is not None:
                spatial.mark_dirty_many(moved_owners)
                spatial.flush_dirty()

        for record in self._area_records:
            pm_pos = record.pm_body.position
            record.prev_x = record.x
            record.prev_y = record.y
            record.prev_angle = record.angle
            record.x = pm_pos.x
            record.y = pm_pos.y
            record.angle = math.degrees(record.pm_body.angle)

    @staticmethod
    def _world_to_local_state(
        x: float,
        y: float,
        rotation: float,
        parent_world,
    ) -> tuple[float, float, float]:
        """Convert a world-space state to the parent's local space."""
        if parent_world is None:
            return (x, y, rotation)

        dx = x - parent_world.position[0]
        dy = y - parent_world.position[1]
        parent_rad = math.radians(-parent_world.rotation)
        cos_r = math.cos(parent_rad)
        sin_r = math.sin(parent_rad)
        scale_x = parent_world.scale[0] if parent_world.scale[0] != 0.0 else 1e-6
        scale_y = parent_world.scale[1] if parent_world.scale[1] != 0.0 else 1e-6

        return (
            (dx * cos_r - dy * sin_r) / scale_x,
            (dx * sin_r + dy * cos_r) / scale_y,
            rotation - parent_world.rotation,
        )

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def point_query(
        self,
        x: float,
        y: float,
        max_distance: float = 0.0,
        filter: CollisionFilter | None = None,
    ) -> list[PhysicsBody | PhysicsArea | StaticBody]:
        """Query all physics objects near a point.

        Args:
            x, y: The query point.
            max_distance: The maximum distance.
            filter: Optional collision filter.

        Returns:
            The list of physics objects found.
        """
        pm_filter = pymunk.ShapeFilter()
        if filter is not None:
            pm_filter = pymunk.ShapeFilter(
                group=filter.group, categories=filter.layer, mask=filter.mask
            )

        results = self.backend.point_query((x, y), max_distance, pm_filter)
        objects: list[PhysicsBody | PhysicsArea | StaticBody] = []
        seen: set[int] = set()

        for info in results:
            if info.shape is not None and info.shape.body is not None:
                data = getattr(info.shape.body, "data", None)
                if data is not None:
                    data = self._query_target(data)
                    did = id(data)
                    if did not in seen:
                        seen.add(did)
                        objects.append(data)
        return objects

    def ray_cast(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        radius: float = 0.0,
        filter: CollisionFilter | None = None,
    ) -> list[
        tuple[PhysicsBody | PhysicsArea | StaticBody, float, tuple[float, float]]
    ]:
        """Cast a ray from start to end.

        Args:
            start: The start point (x, y).
            end: The end point (x, y).
            radius: The ray thickness.
            filter: Optional collision filter.

        Returns:
            A list of (object, alpha, normal) tuples sorted by distance.
            ``alpha`` = 0.0 at start, 1.0 at end.
        """
        pm_filter = pymunk.ShapeFilter()
        if filter is not None:
            pm_filter = pymunk.ShapeFilter(
                group=filter.group, categories=filter.layer, mask=filter.mask
            )

        results = self.backend.segment_query(start, end, radius, pm_filter)
        hits = []
        seen: set[int] = set()

        for info in results:
            if info.shape is not None and info.shape.body is not None:
                data = getattr(info.shape.body, "data", None)
                if data is not None:
                    data = self._query_target(data)
                    did = id(data)
                    if did not in seen:
                        seen.add(did)
                        normal = (info.normal.x, info.normal.y)
                        hits.append((data, info.alpha, normal))

        # Sort by alpha (distance)
        hits.sort(key=lambda h: h[1])
        return hits

    def area_query(
        self,
        aabb: AABB,
        filter: CollisionFilter | None = None,
    ) -> list[PhysicsBody | PhysicsArea | StaticBody]:
        """Query all objects inside an AABB.

        Args:
            aabb: The query area.
            filter: Optional collision filter.

        Returns:
            The list of physics objects found.
        """
        pm_filter = pymunk.ShapeFilter()
        if filter is not None:
            pm_filter = pymunk.ShapeFilter(
                group=filter.group, categories=filter.layer, mask=filter.mask
            )

        results = self.backend.bb_query(
            (aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y), pm_filter
        )
        objects: list[PhysicsBody | PhysicsArea | StaticBody] = []
        seen: set[int] = set()

        for shape in results:
            if shape.body is not None:
                data = getattr(shape.body, "data", None)
                if data is not None:
                    data = self._query_target(data)
                    did = id(data)
                    if did not in seen:
                        seen.add(did)
                        objects.append(data)
        return objects

    # ------------------------------------------------------------------
    # Configuration API
    # ------------------------------------------------------------------

    def set_gravity(self, gx: float, gy: float) -> None:
        """Set the world gravity ``(gx, gy)``.

        Args:
            gx: The gravity X component.
            gy: The gravity Y component.
        """
        self.backend.gravity = (gx, gy)

    @property
    def gravity(self) -> tuple[float, float]:
        """The current world gravity ``(gx, gy)``."""
        return self.backend.gravity

    def set_sleeping(self, enabled: bool, threshold: float = 0.5) -> None:
        """Enable/disable body sleeping.

        Args:
            enabled: ``True`` to enable sleeping.
            threshold: The idle time threshold before a body sleeps.
        """
        self.backend.set_sleeping(enabled, threshold)

    def set_iterations(self, iterations: int) -> None:
        """Set the pymunk solver's iteration count.

        Args:
            iterations: The number of iterations (higher = more accurate).
        """
        self.backend.iterations = iterations

    def set_damping(self, damping: float) -> None:
        """Set the pymunk global damping.

        Args:
            damping: The damping factor.
        """
        self.backend.damping = damping

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
        """Configure pymunk ``Space`` parameters all at once.

        Args:
            iterations: The solver iteration count (optional).
            damping: Global damping (optional).
            collision_slop: Collision tolerance slop (optional).
            collision_bias: Collision bias (optional).
            enable_spatial_hash: Enable the spatial hash (optional).
            spatial_hash_dim: The spatial hash cell dimension.
            spatial_hash_count: The spatial hash capacity.
        """
        self.backend.configure_space(
            iterations=iterations,
            damping=damping,
            collision_slop=collision_slop,
            collision_bias=collision_bias,
            enable_spatial_hash=enable_spatial_hash,
            spatial_hash_dim=spatial_hash_dim,
            spatial_hash_count=spatial_hash_count,
        )

    def query_aabb_fast(
        self, aabb: AABB
    ) -> list[StaticBody | PhysicsBodyRecord | PhysicsAreaRecord]:
        """Fast AABB query via the ``QuadTree`` + pymunk bounding box check.

        Args:
            aabb: The query area.

        Returns:
            list: The statics/body records/area records overlapping the AABB.
        """
        results: list[StaticBody | PhysicsBodyRecord | PhysicsAreaRecord] = []
        for record in self._static_records.values():
            if record.aabb.intersects(aabb):
                results.append(record.static)
        query_bb = (aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y)
        for record in self._body_records:
            if self._shapes_intersect_bb(record.pm_shapes, query_bb):
                results.append(record)
        for record in self._area_records:
            if self._shapes_intersect_bb(record.pm_shapes, query_bb):
                results.append(record)
        return results

    @staticmethod
    def _shapes_intersect_bb(
        pm_shapes: list[pymunk.Shape], bb: tuple[float, float, float, float]
    ) -> bool:
        """Return whether any of the shapes' bounding boxes intersect ``bb``."""
        left, top, right, bottom = bb
        for pm_shape in pm_shapes:
            shape_bb = getattr(pm_shape, "bb", None)
            if shape_bb is None:
                continue
            shape_left = float(min(shape_bb.left, shape_bb.right))
            shape_right = float(max(shape_bb.left, shape_bb.right))
            shape_top = float(min(shape_bb.top, shape_bb.bottom))
            shape_bottom = float(max(shape_bb.top, shape_bb.bottom))
            if (
                shape_right >= left
                and shape_left <= right
                and shape_bottom >= top
                and shape_top <= bottom
            ):
                return True
        return False

    @property
    def body_count(self) -> int:
        """The number of registered dynamic/kinematic bodies."""
        return len(self._body_records)

    @property
    def area_count(self) -> int:
        """The number of registered sensor areas."""
        return len(self._areas)

    @property
    def static_count(self) -> int:
        """The number of static bodies in the world."""
        return len(self._statics)

    def get_bodies(self) -> list[PhysicsBody]:
        """Return all registered PhysicsBody instances."""
        return list(self._bodies.values())

    def get_areas(self) -> list[PhysicsArea]:
        """Return all registered PhysicsArea instances."""
        return list(self._areas.values())

    def get_statics(self) -> list[StaticBody]:
        """Return all registered StaticBody instances."""
        return list(self._statics.values())
