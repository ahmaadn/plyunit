"""``Physics`` service — pymunk implementation of the ``IPhysics`` port."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pymunk

from plyunit.core.units.service_unit import ServiceUnit
from plyunit.services.physics._types import (
    AABB,
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
from plyunit.utils.data_structures.quad_tree import QuadTree

from .physics_area import PhysicsArea
from .physics_body import PhysicsBody

if TYPE_CHECKING:
    from plyunit.core.app import App

logger = logging.getLogger(__name__)

type CollisionCallback = Callable[[pymunk.Arbiter, pymunk.Space, Any], None]


def iter_shape_aabbs(pm_shapes: list[pymunk.Shape]) -> Iterator[AABB]:
    """Convert the cached bounding boxes of pymunk shapes to ``AABB`` objects."""
    for pm_shape in pm_shapes:
        bb = pm_shape.bb
        yield AABB(
            float(min(bb.left, bb.right)),
            float(min(bb.top, bb.bottom)),
            float(max(bb.left, bb.right)),
            float(max(bb.top, bb.bottom)),
        )


@dataclass(slots=True)
class PymunkBodyRecord:
    """Internal record for a registered dynamic/kinematic body."""

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

    @property
    def is_sleeping(self) -> bool:
        """Whether the underlying pymunk body is sleeping."""
        return bool(self.pm_body.is_sleeping)

    @property
    def shape_bounds(self) -> Iterator[AABB]:
        """World-space bounds of each shape."""
        return iter_shape_aabbs(self.pm_shapes)

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
class PymunkAreaRecord:
    """Internal record for a registered sensor area."""

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

    @property
    def shape_bounds(self) -> Iterator[AABB]:
        """World-space bounds of each shape."""
        return iter_shape_aabbs(self.pm_shapes)

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
class PymunkStaticRecord:
    """Internal record for a ``StaticBody`` registered in the pymunk space."""

    static: StaticBody
    aabb: AABB
    pm_body: pymunk.Body
    pm_shapes: list[pymunk.Shape]


class Physics(ServiceUnit):
    """Global service that manages the entire physics simulation (pymunk).

    Implements :class:`plyunit.backends.ports.physics.IPhysics`.

    Must be instantiated before PhysicsBody/PhysicsArea enter the scene
    tree. ``step(dt)`` runs on every fixed update (connected in ``on_attach``).

    Args:
        world_bounds: World bounds for the QuadTree (min_x, min_y, max_x, max_y).
        gravity: World gravity (gx, gy). Default ``(0, 0)``.
        spatial_hash_dim: pymunk spatial hash cell dimension (pixels).
        spatial_hash_count: Number of spatial hash buckets.
        sleep_time_threshold: Idle time before a body sleeps (0 = disabled).
        idle_speed_threshold: Speed below which a body is considered idle.
        iterations: Solver iteration count.
        damping: Global velocity damping (1.0 = none).
        collision_slop: Allowed overlap between shapes.
        collision_bias: Fraction of penetration fixed per step.
        enable_spatial_hash: Use the spatial hash instead of the default BB tree.
    """

    @staticmethod
    def create_static_body(**kwargs: Any) -> StaticBody:
        """Create a ``StaticBody`` (convenience factory).

        Args:
            **kwargs: Arguments forwarded to ``StaticBody(...)``.
        """
        return StaticBody(**kwargs)

    def __init__(
        self,
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
        """Initialize the service, the pymunk space, registries and handlers."""
        super().__init__(name="Physics", tags={"service", "physics"})

        # --- pymunk space ---------------------------------------------
        self._space = pymunk.Space()
        self._space.gravity = gravity
        self._space.iterations = max(1, int(iterations))
        self._space.damping = max(0.0, float(damping))
        if collision_slop is not None:
            self._space.collision_slop = max(0.0, float(collision_slop))
        if collision_bias is not None:
            self._space.collision_bias = float(collision_bias)

        self.spatial_hash_enabled = bool(enable_spatial_hash)
        if self.spatial_hash_enabled:
            self._space.use_spatial_hash(spatial_hash_dim, spatial_hash_count)

        if sleep_time_threshold > 0:
            self._space.sleep_time_threshold = sleep_time_threshold
            self._space.idle_speed_threshold = idle_speed_threshold

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
        self._body_records: list[PymunkBodyRecord] = []
        self._body_handle_to_index: dict[PhysicsHandle, int] = {}
        self._area_records: list[PymunkAreaRecord] = []
        self._area_handle_to_index: dict[PhysicsHandle, int] = {}
        self._static_records: dict[int, PymunkStaticRecord] = {}
        self._next_handle = 1
        self._pending_reindexes: set[pymunk.Body] = set()

        # Collision tracking — to detect enter/exit (counter per shape pair)
        self._active_collisions: dict[tuple[int, int], int] = {}
        self._active_overlaps: dict[tuple[int, int], int] = {}
        # Additional pre-solve hooks (e.g. one-way platforms) — may set
        # ``arbiter.process_collision = False`` to disable the response.
        self._pre_solve_handlers: list[CollisionCallback] = []
        self.profile_enabled = False
        self.last_step_profile = PhysicsStepProfile()
        self._collision_dispatch_ms = 0.0

        self._setup_collision_handlers()

    def _add_pm_dynamic_body(
        self,
        mass: float,
        moment: float,
        position: tuple[float, float],
        angle: float,
    ) -> pymunk.Body:
        """Create a dynamic pymunk body and add it to the space."""
        body = pymunk.Body(mass, moment, body_type=pymunk.Body.DYNAMIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def _add_pm_kinematic_body(
        self, position: tuple[float, float], angle: float = 0.0
    ) -> pymunk.Body:
        """Create a kinematic pymunk body and add it to the space."""
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def _add_pm_static_body(
        self, position: tuple[float, float], angle: float = 0.0
    ) -> pymunk.Body:
        """Create a static pymunk body and add it to the space."""
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def _add_pm_shape(
        self,
        body: pymunk.Body,
        shape_def: PhysicsShape,
        body_filter: CollisionFilter | None = None,
    ) -> pymunk.Shape:
        """Convert a ``PhysicsShape`` to a pymunk shape, attach and add it."""
        pm_shape = self._convert_shape(body, shape_def)
        pm_shape.sensor = shape_def.is_sensor
        pm_shape.friction = shape_def.friction
        pm_shape.elasticity = shape_def.elasticity

        filt = shape_def.filter if shape_def.filter is not None else body_filter
        if filt is None:
            filt = CollisionFilter()
        pm_shape.filter = pymunk.ShapeFilter(
            group=filt.group,
            categories=filt.layer,
            mask=filt.mask,
        )

        self._space.add(pm_shape)
        return pm_shape

    @staticmethod
    def _convert_shape(body: pymunk.Body, shape_def: PhysicsShape) -> pymunk.Shape:
        """Convert a plyunit shape definition to a native pymunk shape."""
        ox, oy = shape_def.offset

        if isinstance(shape_def, CircleShape):
            return pymunk.Circle(body, shape_def.radius, offset=(ox, oy))

        if isinstance(shape_def, BoxShape):
            hw, hh = shape_def.width / 2, shape_def.height / 2
            vertices = [
                (ox - hw, oy - hh),
                (ox + hw, oy - hh),
                (ox + hw, oy + hh),
                (ox - hw, oy + hh),
            ]
            if shape_def.radius > 0:
                return pymunk.Poly(body, vertices, radius=shape_def.radius)
            return pymunk.Poly(body, vertices)

        if isinstance(shape_def, SegmentShape):
            a = (shape_def.a[0] + ox, shape_def.a[1] + oy)
            b = (shape_def.b[0] + ox, shape_def.b[1] + oy)
            return pymunk.Segment(body, a, b, shape_def.radius)

        if isinstance(shape_def, PolygonShape):
            if len(shape_def.vertices) < 3:
                raise ValueError("PolygonShape needs at least 3 vertices")
            verts = [(v[0] + ox, v[1] + oy) for v in shape_def.vertices]
            return pymunk.Poly(body, verts)

        raise TypeError(f"Unknown shape type: {type(shape_def)}")

    def _remove_pm_body(self, body: pymunk.Body) -> None:
        """Remove a pymunk body and all of its shapes from the space."""
        self._pending_reindexes.discard(body)
        for shape in list(body.shapes):
            self._space._add_later.discard(shape)
            if shape.space is self._space:
                self._space.remove(shape)
        self._space._add_later.discard(body)
        if body.space is self._space:
            self._space.remove(body)
        self._flush_pending_reindexes()

    def _reindex_pm_body(self, body: pymunk.Body) -> None:
        if self._space._locked:
            self._pending_reindexes.add(body)
        elif body.space is self._space:
            self._space.reindex_shapes_for_body(body)

    def _flush_pending_reindexes(self) -> None:
        if self._space._locked:
            return
        while self._pending_reindexes:
            body = self._pending_reindexes.pop()
            if body.space is self._space:
                self._space.reindex_shapes_for_body(body)

    @staticmethod
    def _moment_for_shapes(mass: float, shapes: list[PhysicsShape]) -> float:
        """Compute the total moment of inertia for a set of shapes."""
        if not shapes:
            return pymunk.moment_for_circle(mass, 0, 10)

        total_moment = 0.0
        mass_per_shape = mass / len(shapes)

        for shape_def in shapes:
            ox, oy = shape_def.offset
            if isinstance(shape_def, CircleShape):
                total_moment += pymunk.moment_for_circle(
                    mass_per_shape, 0, shape_def.radius, offset=(ox, oy)
                )
            elif isinstance(shape_def, BoxShape):
                total_moment += pymunk.moment_for_box(
                    mass_per_shape, (shape_def.width, shape_def.height)
                )
            elif isinstance(shape_def, PolygonShape):
                if len(shape_def.vertices) >= 3:
                    verts = [(v[0] + ox, v[1] + oy) for v in shape_def.vertices]
                    total_moment += pymunk.moment_for_poly(mass_per_shape, verts)
                else:
                    total_moment += pymunk.moment_for_circle(mass_per_shape, 0, 10)
            elif isinstance(shape_def, SegmentShape):
                # Thin rod approximation: (1/12) * m * L^2
                a, b = shape_def.a, shape_def.b
                length = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
                total_moment += (1.0 / 12.0) * mass_per_shape * length * length
            else:
                total_moment += pymunk.moment_for_circle(mass_per_shape, 0, 10)

        return max(total_moment, 1.0)

    def _setup_collision_handlers(self) -> None:
        """Register the pymunk collision handlers that dispatch events."""
        self._space.on_collision(
            collision_type_a=None,
            collision_type_b=None,
            begin=self._on_collision_begin,
            pre_solve=self._on_pre_solve,
            separate=self._on_collision_separate,
        )

    def add_pre_solve_handler(self, handler: CollisionCallback) -> None:
        """Register an additional pymunk pre-solve callback.

        pymunk-specific extension (NOT part of ``IPhysics``): the handler may
        set ``arbiter.process_collision = False`` to disable the response.
        """
        self._pre_solve_handlers.append(handler)

    def install_one_way_handler(self) -> None:
        """Install the collision filter for one-way platform metadata.

        All tilemap bridges share this service-owned callback, so unloading or
        recreating a tilemap does not accumulate bound bridge methods.
        """
        handler = self._one_way_pre_solve
        if handler not in self._pre_solve_handlers:
            self.add_pre_solve_handler(handler)

    @staticmethod
    def _one_way_pre_solve(
        arbiter: pymunk.Arbiter, space: pymunk.Space, data: Any
    ) -> None:
        """Allow contact only above a one-way platform in a Y-down world."""
        shape_a, shape_b = arbiter.shapes
        a_data = getattr(shape_a.body, "data", None)
        b_data = getattr(shape_b.body, "data", None)
        if isinstance(a_data, StaticBody):
            static, direction = a_data, 1.0
        elif isinstance(b_data, StaticBody):
            static, direction = b_data, -1.0
        else:
            return
        metadata = static.user_data
        if isinstance(metadata, dict) and metadata.get("is_one_way"):
            _, normal_y = arbiter.normal
            if normal_y * direction > -0.5:
                arbiter.process_collision = False

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
        """pymunk handler fired when a collision begins."""
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
                self._handle_overlap_begin(body_a_data, body_b_data)
                arbiter.process_collision = False  # Sensor: no collision response
                return

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
        """pymunk handler fired when a collision ends."""
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
            if isinstance(data, (PymunkBodyRecord, PymunkAreaRecord))
            else data
        )

    @staticmethod
    def _event_key_part(data: Any) -> int:
        """Return a stable hashable key part (handle or id) for a record or object."""
        if isinstance(data, (PymunkBodyRecord, PymunkAreaRecord)):
            return int(data.handle)
        return id(data)

    def _handle_collision_begin(
        self,
        a: PhysicsBody | StaticBody,
        b: PhysicsBody | StaticBody,
        arbiter: pymunk.Arbiter,
    ) -> None:
        """Dispatch a collision-enter event to the owners' ``on_collision_enter``."""
        lo, hi = sorted((self._event_key_part(a), self._event_key_part(b)))
        key = (lo, hi)
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
            a.on_collision_enter.emit(
                CollisionInfo(
                    other=b,
                    normal=normal,
                    points=contact_points,
                    total_impulse=total_impulse,
                )
            )

        if b_listens:
            b.on_collision_enter.emit(
                CollisionInfo(
                    other=a,
                    normal=(-normal[0], -normal[1]),
                    points=contact_points,
                    total_impulse=total_impulse,
                )
            )

    def _handle_collision_end(
        self, a: PhysicsBody | StaticBody, b: PhysicsBody | StaticBody
    ) -> None:
        """Dispatch a collision-exit event to the owning ``PhysicsBody``."""
        lo, hi = sorted((self._event_key_part(a), self._event_key_part(b)))
        key = (lo, hi)
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
        lo, hi = sorted((self._event_key_part(a), self._event_key_part(b)))
        key = (lo, hi)
        a = self._event_target(a)
        b = self._event_target(b)

        self._active_overlaps[key] = self._active_overlaps.get(key, 0) + 1
        if self._active_overlaps[key] > 1:
            return

        if isinstance(a, PhysicsArea) and isinstance(b, PhysicsBody):
            a._on_body_enter(b)
        elif isinstance(a, PhysicsBody) and isinstance(b, PhysicsArea):
            b._on_body_enter(a)
        elif isinstance(a, PhysicsArea) and isinstance(b, PhysicsArea):
            a._on_area_enter(b)
            b._on_area_enter(a)

    def _handle_overlap_end(
        self,
        a: PhysicsBody | PhysicsArea | StaticBody,
        b: PhysicsBody | PhysicsArea | StaticBody,
    ) -> None:
        """Dispatch a (sensor) overlap-exit event to the ``PhysicsArea``."""
        lo, hi = sorted((self._event_key_part(a), self._event_key_part(b)))
        key = (lo, hi)
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

    def _new_handle(self) -> PhysicsHandle:
        """Create a new ``PhysicsHandle`` with an incrementing ID."""
        handle = PhysicsHandle(self._next_handle)
        self._next_handle += 1
        return handle

    def _body_record_for_owner(self, owner: PhysicsBody) -> PymunkBodyRecord | None:
        """Find the body record for ``owner`` (or ``None``)."""
        handle = getattr(owner, "_physics_handle", None)
        if handle is None:
            return None
        index = self._body_handle_to_index.get(handle)
        return None if index is None else self._body_records[index]

    def _area_record_for_owner(self, owner: PhysicsArea) -> PymunkAreaRecord | None:
        """Find the area record for ``owner`` (or ``None``)."""
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
        """Create many ownerless bodies in a single call."""
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
    ) -> PymunkBodyRecord:
        """Create a pymunk body, its shapes, and its registered record."""
        if body_type == BodyType.DYNAMIC:
            moment = self._moment_for_shapes(max(mass, 0.01), shapes)
            pm_body = self._add_pm_dynamic_body(
                mass=max(mass, 0.01),
                moment=moment,
                position=position,
                angle=math.radians(rotation),
            )
        elif body_type == BodyType.KINEMATIC:
            pm_body = self._add_pm_kinematic_body(
                position=position,
                angle=math.radians(rotation),
            )
        else:
            raise ValueError("create_body only supports DYNAMIC and KINEMATIC bodies")

        if fixed_rotation:
            pm_body.moment = float("inf")

        body_filter = filter if filter is not None else CollisionFilter.dynamic_actor()
        handle = self._new_handle()
        record = PymunkBodyRecord(
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
        try:
            for shape_def in shapes:
                record.pm_shapes.append(
                    self._add_pm_shape(pm_body, shape_def, body_filter)
                )
        except Exception:
            self._remove_pm_body(pm_body)
            raise
        self._body_handle_to_index[handle] = len(self._body_records)
        self._body_records.append(record)
        return record

    def destroy_body(self, handle: PhysicsHandle) -> None:
        """Remove a body and clean up its collision tracking."""
        index = self._body_handle_to_index.pop(handle, None)
        if index is None:
            return
        record = self._body_records[index]
        last = self._body_records.pop()
        if index < len(self._body_records):
            self._body_records[index] = last
            self._body_handle_to_index[last.handle] = index
        self._remove_pm_body(record.pm_body)
        if record.owner is not None:
            record.owner._pm_body = None
            record.owner._pm_shapes.clear()
            record.owner._registered = False
            record.owner._physics_handle = None
            self._bodies.pop(id(record.owner), None)
        self._active_collisions = {
            k: v for k, v in self._active_collisions.items() if int(handle) not in k
        }
        self._active_overlaps = {
            k: v for k, v in self._active_overlaps.items() if int(handle) not in k
        }

    def destroy_body_batch(self, handles: list[PhysicsHandle]) -> None:
        """Remove many bodies from the service."""
        for handle in handles:
            self.destroy_body(handle)

    def get_body_state(
        self, handle: PhysicsHandle
    ) -> tuple[float, float, float] | None:
        """Return the body's state ``(x, y, angle)``, or ``None`` when absent."""
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
        """Partially set the body's state (position/rotation/velocity are optional)."""
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
        if position is not None or rotation is not None:
            self._reindex_pm_body(record.pm_body)

    def get_position(self, handle: PhysicsHandle) -> tuple[float, float] | None:
        """Return the body's position ``(x, y)``, or ``None`` when absent."""
        state = self.get_body_state(handle)
        return None if state is None else (state[0], state[1])

    def get_rotation(self, handle: PhysicsHandle) -> float | None:
        """Return the body's angle (degrees), or ``None`` when absent."""
        state = self.get_body_state(handle)
        return None if state is None else state[2]

    def iter_body_states(self) -> Iterator[PymunkBodyRecord]:
        """Iterate over all body records (dynamic + kinematic)."""
        return iter(self._body_records)

    def iter_dynamic_states(self) -> Iterator[PymunkBodyRecord]:
        """Iterate over only the dynamic body records."""
        return (r for r in self._body_records if r.body_type == BodyType.DYNAMIC)

    def iter_area_states(self) -> Iterator[PymunkAreaRecord]:
        """Iterate over all sensor area records."""
        return iter(self._area_records)

    @staticmethod
    def _query_target(data: Any) -> Any:
        """Resolve a record to its owner (or the record itself when ownerless)."""
        if isinstance(data, (PymunkBodyRecord, PymunkAreaRecord)):
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
    ) -> PymunkAreaRecord:
        """Create a kinematic sensor body, its shapes, and its registered record."""
        pm_body = self._add_pm_kinematic_body(
            position=position,
            angle=math.radians(rotation),
        )
        area_filter = filter if filter is not None else CollisionFilter.sensor()
        handle = self._new_handle()
        record = PymunkAreaRecord(
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
        try:
            for shape_def in shapes:
                shape_def.is_sensor = True
                record.pm_shapes.append(
                    self._add_pm_shape(pm_body, shape_def, area_filter)
                )
        except Exception:
            self._remove_pm_body(pm_body)
            raise
        self._area_handle_to_index[handle] = len(self._area_records)
        self._area_records.append(record)
        return record

    def destroy_area(self, handle: PhysicsHandle) -> None:
        """Remove a sensor area and clean up its overlap tracking."""
        index = self._area_handle_to_index.pop(handle, None)
        if index is None:
            return
        record = self._area_records[index]
        last = self._area_records.pop()
        if index < len(self._area_records):
            self._area_records[index] = last
            self._area_handle_to_index[last.handle] = index
        self._remove_pm_body(record.pm_body)
        if record.owner is not None:
            record.owner._pm_body = None
            record.owner._pm_shapes.clear()
            record.owner._registered = False
            record.owner._physics_handle = None
            self._areas.pop(id(record.owner), None)
        self._active_overlaps = {
            k: v for k, v in self._active_overlaps.items() if int(handle) not in k
        }

    def register_body(self, body: PhysicsBody) -> None:
        """Register a ``PhysicsBody`` with the physics simulation."""
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
        """Unregister a ``PhysicsBody`` from the simulation."""
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

        body_id = id(body)
        to_remove = [k for k in self._active_collisions if body_id in k]
        for k in to_remove:
            self._active_collisions.pop(k, None)

        logger.debug("Unregistered PhysicsBody '%s' (id=%d)", body.name, body_id)

    def register_area(self, area: PhysicsArea) -> None:
        """Register a ``PhysicsArea`` with the physics simulation."""
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
        """Unregister a ``PhysicsArea`` from the simulation."""
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

        area_id = id(area)
        to_remove = [k for k in self._active_overlaps if area_id in k]
        for k in to_remove:
            self._active_overlaps.pop(k, None)

        logger.debug("Unregistered PhysicsArea '%s' (id=%d)", area.name, area_id)

    def sync_body_shapes(self, body: PhysicsBody) -> None:
        """Re-sync a ``PhysicsBody``'s shapes to pymunk after its shape list changed."""
        if body._pm_body is None:
            return

        record = self._body_record_for_owner(body)
        for old_shape in body._pm_shapes:
            self._space.remove(old_shape)
        body._pm_shapes.clear()
        if record is not None:
            record.shape_defs = body.shapes
            record.fixed_rotation = body.fixed_rotation

        if body.body_type == BodyType.DYNAMIC:
            body._pm_body.moment = (
                float("inf")
                if body.fixed_rotation
                else self._moment_for_shapes(body.mass, body.shapes)
            )

        for shape_def in body.shapes:
            pm_shape = self._add_pm_shape(body._pm_body, shape_def, body.filter)
            body._pm_shapes.append(pm_shape)

    def sync_area_shapes(self, area: PhysicsArea) -> None:
        """Re-sync a ``PhysicsArea``'s shapes to pymunk after its shape list changed."""
        if area._pm_body is None:
            return

        record = self._area_record_for_owner(area)
        for old_shape in area._pm_shapes:
            self._space.remove(old_shape)
        area._pm_shapes.clear()
        if record is not None:
            record.shape_defs = area.shapes

        for shape_def in area.shapes:
            shape_def.is_sensor = True
            pm_shape = self._add_pm_shape(area._pm_body, shape_def, area.filter)
            area._pm_shapes.append(pm_shape)

    def on_attach(self, app: App) -> None:
        """Subscribe ``step(dt)`` to ``app.on_fixed_update``.

        **Do not** also call ``step`` from ``update()`` (it would double-step).
        """
        app.on_fixed_update.connect(self._on_fixed_update)

    def on_detach(self, app: App) -> None:
        app.on_fixed_update.disconnect(self._on_fixed_update)

    def _on_fixed_update(self, dt: float) -> None:
        """Fixed tick hook: delegates to ``step(dt)``."""
        self.step(dt)

    def add_static(self, static: StaticBody) -> None:
        """Add a ``StaticBody`` to the QuadTree AND the pymunk space."""
        static_id = static.id
        if static_id in self._statics:
            return

        pm_body = self._add_pm_static_body(position=static.position)
        pm_body.data = static

        try:
            pm_shapes = [
                self._add_pm_shape(pm_body, shape_def, static.filter)
                for shape_def in static.shapes
            ]
            aabb = self._compute_static_aabb(static)
        except Exception:
            self._remove_pm_body(pm_body)
            raise
        self.world_tree.insert(static, aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y)

        self._statics[static_id] = static
        self._static_records[static_id] = PymunkStaticRecord(
            static=static, aabb=aabb, pm_body=pm_body, pm_shapes=pm_shapes
        )
        logger.debug("Added static body id=%d at %s", static_id, static.position)

    def add_static_batch(self, statics: list[StaticBody]) -> None:
        """Add many static bodies at once."""
        for s in statics:
            self.add_static(s)

    def remove_static(self, static_id: int) -> None:
        """Remove a static body by ID."""
        static = self._statics.pop(static_id, None)
        record = self._static_records.pop(static_id, None)
        if static is None:
            return

        if record is not None:
            self._remove_pm_body(record.pm_body)
        self.world_tree.remove(static)

    def clear_statics(self) -> None:
        """Remove all static bodies from the world."""
        for record in list(self._static_records.values()):
            self._remove_pm_body(record.pm_body)
        self._statics.clear()
        self._static_records.clear()
        self.world_tree.clear()

    def get_static_shape_bounds(self, static: StaticBody) -> Iterator[AABB]:
        """World-space bounds of each shape of a registered static body."""
        record = self._static_records.get(static.id)
        return iter(()) if record is None else iter_shape_aabbs(record.pm_shapes)

    def _compute_static_aabb(self, static: StaticBody) -> AABB:
        """Compute a static body's AABB from its position + shapes.

        Falls back to a 1x1 box when there are no shapes.
        """
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

        if min_x == max_x and min_y == max_y:
            return AABB(px - 0.5, py - 0.5, px + 0.5, py + 0.5)

        return AABB(min_x, min_y, max_x, max_y)

    def step(self, dt: float) -> None:
        """Advance the physics simulation by one step.

        Workflow:
        1. Sync NodeUnit transform → pymunk (kinematic bodies + areas)
        2. Step the pymunk space
        3. Sync pymunk → NodeUnit transform (dynamic bodies)

        Normally invoked through ``App.on_fixed_update``. Call it manually
        only when the service is not attached to an App.

        Args:
            dt: Fixed delta time (seconds).
        """
        if dt <= 0:
            return

        profiling = self.profile_enabled
        self._collision_dispatch_ms = 0.0
        pre_start = time.perf_counter() if profiling else 0.0
        self._pre_step_sync(dt)
        pre_ms = (time.perf_counter() - pre_start) * 1000.0 if profiling else 0.0

        step_start = time.perf_counter() if profiling else 0.0
        self._space.step(dt)
        self._flush_pending_reindexes()
        step_ms = (time.perf_counter() - step_start) * 1000.0 if profiling else 0.0

        post_start = time.perf_counter() if profiling else 0.0
        self._post_step_sync()
        post_ms = (time.perf_counter() - post_start) * 1000.0 if profiling else 0.0

        if profiling:
            self.last_step_profile = PhysicsStepProfile(
                pre_sync_ms=pre_ms,
                backend_step_ms=step_ms,
                post_sync_ms=post_ms,
                collision_dispatch_ms=self._collision_dispatch_ms,
                active_body_count=len(self._body_records),
                sleeping_body_count=sum(1 for r in self._body_records if r.is_sleeping),
                shape_count=sum(len(r.pm_shapes) for r in self._body_records)
                + sum(len(r.pm_shapes) for r in self._area_records)
                + sum(len(r.pm_shapes) for r in self._static_records.values()),
                arbiter_count=len(self._active_collisions) + len(self._active_overlaps),
            )

    def _pre_step_sync(self, dt: float) -> None:
        """Sync ``NodeUnit`` transforms → pymunk bodies (kinematic + areas)."""
        for record in self._body_records:
            body = record.owner
            pm_body = record.pm_body

            if record.body_type == BodyType.KINEMATIC and body is not None:
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
                if record.gravity_scale != 1.0:
                    gx, gy = self._space.gravity
                    scale_diff = record.gravity_scale - 1.0
                    pm_body.apply_force_at_world_point(
                        (gx * scale_diff * record.mass, gy * scale_diff * record.mass),
                        pm_body.local_to_world(pm_body.center_of_gravity),
                    )

                if record.linear_damping > 0:
                    v = pm_body.velocity
                    damp = max(0, 1.0 - record.linear_damping * dt)
                    pm_body.velocity = (v.x * damp, v.y * damp)

                if record.angular_damping > 0:
                    av = pm_body.angular_velocity
                    damp = max(0, 1.0 - record.angular_damping * dt)
                    pm_body.angular_velocity = av * damp

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
                moved_owners.append(body.unit)

        # Physics movers bypass transform dirty (apply_physics_state clears
        # _dirty), so mark them dirty in the SpatialIndex explicitly.
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

    @staticmethod
    def _pm_filter(filter: CollisionFilter | None) -> pymunk.ShapeFilter:
        """Convert a ``CollisionFilter`` to a ``pymunk.ShapeFilter``."""
        if filter is None:
            return pymunk.ShapeFilter()
        return pymunk.ShapeFilter(
            group=filter.group, categories=filter.layer, mask=filter.mask
        )

    def point_query(
        self,
        x: float,
        y: float,
        max_distance: float = 0.0,
        filter: CollisionFilter | None = None,
    ) -> list[PhysicsBody | PhysicsArea | StaticBody]:
        """Query all physics objects near a point."""
        results = self._space.point_query((x, y), max_distance, self._pm_filter(filter))
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
        """Cast a ray; returns ``(object, alpha, normal)`` sorted by distance."""
        results = self._space.segment_query(start, end, radius, self._pm_filter(filter))
        results.sort(key=lambda info: info.alpha)
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

        hits.sort(key=lambda h: h[1])
        return hits

    def area_query(
        self,
        aabb: AABB,
        filter: CollisionFilter | None = None,
    ) -> list[PhysicsBody | PhysicsArea | StaticBody]:
        """Query all objects inside an AABB."""
        pm_bb = pymunk.BB(aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y)
        results = self._space.bb_query(pm_bb, self._pm_filter(filter))
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

    def query_aabb_fast(
        self, aabb: AABB
    ) -> list[StaticBody | PymunkBodyRecord | PymunkAreaRecord]:
        """Fast AABB query using cached static AABBs + pymunk shape bounds."""
        results: list[StaticBody | PymunkBodyRecord | PymunkAreaRecord] = []
        for record in self._static_records.values():
            if record.aabb.intersects(aabb):
                results.append(record.static)
        query_bb = (aabb.min_x, aabb.min_y, aabb.max_x, aabb.max_y)
        for body_record in self._body_records:
            if self._shapes_intersect_bb(body_record.pm_shapes, query_bb):
                results.append(body_record)
        for area_record in self._area_records:
            if self._shapes_intersect_bb(area_record.pm_shapes, query_bb):
                results.append(area_record)
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

    def iter_contact_points(self) -> Iterator[tuple[float, float]]:
        """Yield current world-space contact points (deduplicated per pair)."""
        seen: set[tuple[int, int]] = set()
        points: list[tuple[float, float]] = []

        def collect(arbiter: pymunk.Arbiter) -> None:
            shape_a, shape_b = arbiter.shapes
            ida, idb = id(shape_a), id(shape_b)
            key = (ida, idb) if ida <= idb else (idb, ida)
            if key in seen:
                return
            seen.add(key)
            for contact in arbiter.contact_point_set.points:
                point = contact.point_a
                points.append((float(point.x), float(point.y)))

        for pm_body in self._space.bodies:
            pm_body.each_arbiter(collect)
        return iter(points)

    # ------------------------------------------------------------------
    # Configuration API
    # ------------------------------------------------------------------

    @property
    def gravity(self) -> tuple[float, float]:
        """The current world gravity ``(gx, gy)``."""
        g = self._space.gravity
        return (g[0], g[1])

    @gravity.setter
    def gravity(self, value: tuple[float, float]) -> None:
        if value == self.gravity:
            return
        self._space.gravity = value
        for record in self._body_records:
            if record.body_type == BodyType.DYNAMIC and record.is_sleeping:
                record.pm_body.activate()

    def set_gravity(self, gx: float, gy: float) -> None:
        """Set the world gravity ``(gx, gy)``."""
        self.gravity = (gx, gy)

    def set_sleeping(self, enabled: bool, threshold: float = 0.5) -> None:
        """Enable/disable body sleeping."""
        if enabled:
            self._space.sleep_time_threshold = threshold
        else:
            self._space.sleep_time_threshold = float("inf")

    def set_iterations(self, iterations: int) -> None:
        """Set the solver's iteration count (higher = more accurate)."""
        self._space.iterations = max(1, int(iterations))

    def set_damping(self, damping: float) -> None:
        """Set the global velocity damping (1.0 = none)."""
        self._space.damping = max(0.0, float(damping))

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
        """Selectively configure pymunk ``Space`` parameters (``None`` = keep)."""
        if iterations is not None:
            self.set_iterations(iterations)
        if damping is not None:
            self.set_damping(damping)
        if collision_slop is not None:
            self._space.collision_slop = max(0.0, float(collision_slop))
        if collision_bias is not None:
            self._space.collision_bias = float(collision_bias)
        if enable_spatial_hash is not None:
            self.spatial_hash_enabled = bool(enable_spatial_hash)
            if self.spatial_hash_enabled:
                self._space.use_spatial_hash(spatial_hash_dim, spatial_hash_count)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

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
