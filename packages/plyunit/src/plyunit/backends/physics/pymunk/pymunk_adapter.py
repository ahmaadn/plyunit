"""PhysicsBackend — thin wrapper over pymunk.Space.

Responsible for:

- Creating and configuring the pymunk Space.
- Enabling the spatial hash and sleeping.
- Simulation stepping.
- Converting plyunit shapes → pymunk shapes.
- Registering collision handlers.
- Query API (point, segment/ray, bounding box).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pymunk

from plyunit.core.components.physics import (
    BoxShape,
    CircleShape,
    CollisionFilter,
    PhysicsShape,
    PolygonShape,
    SegmentShape,
)

if TYPE_CHECKING:
    pass

# Collision handler callback types — pymunk 7
# Callback signature: (arbiter: Arbiter, space: Space, data: Any) -> None
type CollisionCallback = Callable[[pymunk.Arbiter, pymunk.Space, Any], None]


class PhysicsBackend:
    """Low-level wrapper over pymunk.Space.

    Handles all direct interaction with pymunk: body/shape creation,
    spatial hash, sleeping, stepping, and queries.

    Args:
        gravity: World gravity (gx, gy). Default ``(0, 0)``.
        spatial_hash_dim: pymunk spatial hash cell dimension (pixels).
        spatial_hash_count: Number of hash buckets. Larger = fewer collisions.
        sleep_time_threshold: Time (seconds) a body must stay idle before
            sleeping. ``0`` = sleeping disabled.
        idle_speed_threshold: Speed below which a body is considered idle.
    """

    __slots__ = ("_space", "spatial_hash_enabled")

    def __init__(
        self,
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
        """Create and configure the underlying pymunk Space."""
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

        # Enable sleeping
        if sleep_time_threshold > 0:
            self._space.sleep_time_threshold = sleep_time_threshold
            self._space.idle_speed_threshold = idle_speed_threshold

    # ------------------------------------------------------------------
    # Space Configuration
    # ------------------------------------------------------------------

    @property
    def gravity(self) -> tuple[float, float]:
        """The world gravity ``(gx, gy)``."""
        g = self._space.gravity
        return (g[0], g[1])

    @gravity.setter
    def gravity(self, value: tuple[float, float]) -> None:
        self._space.gravity = value

    @property
    def damping(self) -> float:
        """Global velocity damping (0-1). 1.0 = no damping."""
        return self._space.damping

    @damping.setter
    def damping(self, value: float) -> None:
        self._space.damping = value

    @property
    def iterations(self) -> int:
        """The solver's iteration count."""
        return int(self._space.iterations)

    @iterations.setter
    def iterations(self, value: int) -> None:
        self._space.iterations = max(1, int(value))

    @property
    def collision_slop(self) -> float:
        """The allowed overlap between shapes (penetration slop)."""
        return float(self._space.collision_slop)

    @collision_slop.setter
    def collision_slop(self, value: float) -> None:
        self._space.collision_slop = max(0.0, float(value))

    @property
    def collision_bias(self) -> float:
        """The fraction of penetration fixed per step (0-1)."""
        return float(self._space.collision_bias)

    @collision_bias.setter
    def collision_bias(self, value: float) -> None:
        self._space.collision_bias = float(value)

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
        """Selectively configure pymunk Space parameters.

        Only arguments that are not ``None`` are applied.
        """
        if iterations is not None:
            self.iterations = iterations
        if damping is not None:
            self.damping = max(0.0, float(damping))
        if collision_slop is not None:
            self.collision_slop = collision_slop
        if collision_bias is not None:
            self.collision_bias = collision_bias
        if enable_spatial_hash is not None:
            self.spatial_hash_enabled = bool(enable_spatial_hash)
            if self.spatial_hash_enabled:
                self._space.use_spatial_hash(spatial_hash_dim, spatial_hash_count)

    def set_sleeping(self, enabled: bool, threshold: float = 0.5) -> None:
        """Enable or disable sleeping."""
        if enabled:
            self._space.sleep_time_threshold = threshold
        else:
            self._space.sleep_time_threshold = float("inf")

    def create_dynamic_body(
        self,
        mass: float,
        moment: float,
        position: tuple[float, float] = (0.0, 0.0),
        angle: float = 0.0,
    ) -> pymunk.Body:
        """Create a dynamic body and add it to the space.

        Args:
            mass: Body mass.
            moment: Moment of inertia.
            position: Initial world position ``(x, y)``.
            angle: Initial angle (radians).

        Returns:
            The pymunk.Body, already added to the space.
        """
        body = pymunk.Body(mass, moment, body_type=pymunk.Body.DYNAMIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def create_kinematic_body(
        self,
        position: tuple[float, float] = (0.0, 0.0),
        angle: float = 0.0,
    ) -> pymunk.Body:
        """Create a kinematic body and add it to the space.

        Args:
            position: Initial world position ``(x, y)``.
            angle: Initial angle (radians).

        Returns:
            The pymunk.Body, already added to the space.
        """
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def create_static_body(
        self,
        position: tuple[float, float] = (0.0, 0.0),
        angle: float = 0.0,
    ) -> pymunk.Body:
        """Create a static body and add it to the space.

        Args:
            position: Initial world position ``(x, y)``.
            angle: Initial angle (radians).

        Returns:
            The pymunk.Body, already added to the space.
        """
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = position
        body.angle = angle
        self._space.add(body)
        return body

    def add_shape_to_body(
        self,
        body: pymunk.Body,
        shape_def: PhysicsShape,
        body_filter: CollisionFilter | None = None,
    ) -> pymunk.Shape:
        """Convert a PhysicsShape → pymunk.Shape, attach it to the body, and add it
        to the space.

        Args:
            body: The target pymunk body.
            shape_def: The plyunit shape definition.
            body_filter: The body's default filter (used when the shape has
                no filter of its own).

        Returns:
            The pymunk.Shape, already added to the space.
        """
        pm_shape = self._convert_shape(body, shape_def)

        # Set sensor
        pm_shape.sensor = shape_def.is_sensor

        # Set material properties
        pm_shape.friction = shape_def.friction
        pm_shape.elasticity = shape_def.elasticity

        # Set collision filter
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

    def _convert_shape(
        self, body: pymunk.Body, shape_def: PhysicsShape
    ) -> pymunk.Shape:
        """Convert a plyunit shape definition to a native pymunk shape."""
        ox, oy = shape_def.offset

        if isinstance(shape_def, CircleShape):
            return pymunk.Circle(body, shape_def.radius, offset=(ox, oy))

        elif isinstance(shape_def, BoxShape):
            w, h = shape_def.width, shape_def.height
            hw, hh = w / 2, h / 2
            vertices = [
                (ox - hw, oy - hh),
                (ox + hw, oy - hh),
                (ox + hw, oy + hh),
                (ox - hw, oy + hh),
            ]
            if shape_def.radius > 0:
                return pymunk.Poly(body, vertices, radius=shape_def.radius)
            return pymunk.Poly(body, vertices)

        elif isinstance(shape_def, SegmentShape):
            a = (shape_def.a[0] + ox, shape_def.a[1] + oy)
            b = (shape_def.b[0] + ox, shape_def.b[1] + oy)
            return pymunk.Segment(body, a, b, shape_def.radius)

        elif isinstance(shape_def, PolygonShape):
            if len(shape_def.vertices) < 3:
                raise ValueError("PolygonShape needs at least 3 vertices")
            verts = [(v[0] + ox, v[1] + oy) for v in shape_def.vertices]
            return pymunk.Poly(body, verts)

        raise TypeError(f"Unknown shape type: {type(shape_def)}")

    def remove_body(self, body: pymunk.Body) -> None:
        """Remove a body and all of its shapes from the space."""
        shapes = list(body.shapes)
        for s in shapes:
            self._space.remove(s)
        self._space.remove(body)

    def remove_shape(self, shape: pymunk.Shape) -> None:
        """Remove a shape from the space."""
        self._space.remove(shape)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance the physics simulation by one step.

        Args:
            dt: Fixed delta time (seconds).
        """
        self._space.step(dt)

    # ------------------------------------------------------------------
    # Collision Handlers
    # ------------------------------------------------------------------

    def set_default_collision_handler(
        self,
        begin: CollisionCallback | None = None,
        pre_solve: CollisionCallback | None = None,
        post_solve: CollisionCallback | None = None,
        separate: CollisionCallback | None = None,
    ) -> None:
        """Set the default collision handler for all collisions (pymunk 7 API)."""
        self._space.on_collision(
            collision_type_a=None,
            collision_type_b=None,
            begin=begin,
            pre_solve=pre_solve,
            post_solve=post_solve,
            separate=separate,
        )

    def add_collision_handler(
        self,
        collision_type_a: int,
        collision_type_b: int,
        begin: CollisionCallback | None = None,
        pre_solve: CollisionCallback | None = None,
        post_solve: CollisionCallback | None = None,
        separate: CollisionCallback | None = None,
    ) -> None:
        """Add a collision handler for a specific collision type pair."""
        self._space.on_collision(
            collision_type_a=collision_type_a,
            collision_type_b=collision_type_b,
            begin=begin,
            pre_solve=pre_solve,
            post_solve=post_solve,
            separate=separate,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def point_query(
        self,
        point: tuple[float, float],
        max_distance: float = 0.0,
        shape_filter: pymunk.ShapeFilter | None = None,
    ) -> list[pymunk.PointQueryInfo]:
        """Query all shapes near a point.

        Args:
            point: Query point (x, y).
            max_distance: Maximum distance from the point.
            shape_filter: Optional filter.

        Returns:
            The list of PointQueryInfo hits found.
        """
        if shape_filter is None:
            shape_filter = pymunk.ShapeFilter()
        return self._space.point_query(point, max_distance, shape_filter)

    def segment_query(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        radius: float = 0.0,
        shape_filter: pymunk.ShapeFilter | None = None,
    ) -> list[pymunk.SegmentQueryInfo]:
        """Ray/segment cast query.

        Args:
            start: Ray start point (x, y).
            end: Ray end point (x, y).
            radius: Ray thickness.
            shape_filter: Optional filter.

        Returns:
            The list of SegmentQueryInfo hits found.
        """
        if shape_filter is None:
            shape_filter = pymunk.ShapeFilter()
        return self._space.segment_query(start, end, radius, shape_filter)

    def bb_query(
        self,
        bb: tuple[float, float, float, float],
        shape_filter: pymunk.ShapeFilter | None = None,
    ) -> list[pymunk.Shape]:
        """Bounding box query.

        Args:
            bb: Bounding box (left, bottom, right, top).
            shape_filter: Optional filter.

        Returns:
            The list of pymunk Shapes found.
        """
        if shape_filter is None:
            shape_filter = pymunk.ShapeFilter()
        pmbb = pymunk.BB(bb[0], bb[1], bb[2], bb[3])
        return self._space.bb_query(pmbb, shape_filter)

    def shape_query(self, shape: pymunk.Shape) -> list[pymunk.ShapeQueryInfo]:
        """Query all shapes that overlap the given shape."""
        return self._space.shape_query(shape)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_moment_for_shapes(mass: float, shapes: list[PhysicsShape]) -> float:
        """Compute the total moment of inertia for a set of shapes.

        Args:
            mass: Total body mass.
            shapes: The list of shape definitions.

        Returns:
            The total moment of inertia.
        """
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
                # Segments have no moment function in pymunk,
                # approximate as a thin rod
                a = shape_def.a
                b = shape_def.b
                length = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
                # Thin rod moment of inertia: (1/12) * m * L^2
                total_moment += (1.0 / 12.0) * mass_per_shape * length * length
            else:
                total_moment += pymunk.moment_for_circle(mass_per_shape, 0, 10)

        return max(total_moment, 1.0)  # Minimum moment of 1.0 for stability
