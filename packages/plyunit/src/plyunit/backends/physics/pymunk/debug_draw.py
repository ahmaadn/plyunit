"""Debug physics rendering for the current typed renderer.

This module provides :class:`PhysicsDebugDraw` — a component that draws a
debug overlay for every registered pymunk shape (dynamic bodies, static
bodies, areas/sensors, AABBs, and contact points). It is compatible with
plyunit's typed renderer (following ``RenderContext`` and ``Layer.DEBUG``).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from plyunit.core.components.component import Component
from plyunit.rendering.enum import BlendMode, Layer

if TYPE_CHECKING:
    from plyunit.backends.integrations.raylib.drawing import Canvas
    from plyunit.core.components.physics import PhysicsShape
    from plyunit.rendering.render_state import RenderContext
    from plyunit.rendering.renderer import Renderer

    from .physics_area import PhysicsArea
    from .physics_body import PhysicsBody
    from .service import Physics
    from .static_body import StaticBody

_COLOR_DYNAMIC = (0, 200, 50, 180)
_COLOR_DYNAMIC_SLEEPING = (80, 80, 80, 140)
_COLOR_KINEMATIC = (50, 100, 255, 180)
_COLOR_STATIC = (160, 160, 160, 140)
_COLOR_AREA = (255, 200, 0, 120)
_COLOR_CONTACT = (255, 0, 0, 255)

_DEBUG_PASS = "physics_debug"
_DEBUG_Z = 9999.0
_CULL_MARGIN = 100.0


def _transform_point(
    base_x: float,
    base_y: float,
    local_x: float,
    local_y: float,
    angle_deg: float,
) -> tuple[float, float]:
    """Transform a physics local point into world space.

    Args:
        base_x: World X pivot.
        base_y: World Y pivot.
        local_x: Local X (relative).
        local_y: Local Y (relative).
        angle_deg: Body rotation (degrees).

    Returns:
        World coordinates ``(x, y)`` after rotation + translation.
    """
    radians = math.radians(angle_deg)
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    return (
        base_x + local_x * cos_a - local_y * sin_a,
        base_y + local_x * sin_a + local_y * cos_a,
    )


class PhysicsDebugDraw(Component):
    """Debug draw overlay for all registered pymunk physics shapes."""

    def __init__(
        self,
        *,
        draw_bodies: bool = True,
        draw_statics: bool = True,
        draw_areas: bool = True,
        draw_aabb: bool = False,
        draw_contacts: bool = True,
        max_debug_shapes: int | None = None,
        max_contact_points: int | None = None,
    ) -> None:
        """Initialize the debug overlay and its drawing toggles.

        Args:
            draw_bodies: Whether to draw dynamic/kinematic bodies.
            draw_statics: Whether to draw static bodies.
            draw_areas: Whether to draw areas/sensors.
            draw_aabb: Whether to draw shape bounding boxes.
            draw_contacts: Whether to draw contact points.
            max_debug_shapes: Maximum number of debug shapes to submit,
                or ``None`` for no limit.
            max_contact_points: Maximum number of contact points to submit,
                or ``None`` for no limit.
        """
        super().__init__(name="PhysicsDebugDraw")
        self.draw_bodies = draw_bodies
        self.draw_statics = draw_statics
        self.draw_areas = draw_areas
        self.draw_aabb = draw_aabb
        self.draw_contacts = draw_contacts
        self.max_debug_shapes = max_debug_shapes
        self.max_contact_points = max_contact_points
        self._debug_shapes_submitted = 0
        self._physics_service: Physics | None = None

    def on_start(self) -> None:
        """Resolve and cache the global ``Physics`` service on component start."""
        self._resolve_physics_service()

    def render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Submit physics debug primitives to a world-space debug render pass."""
        _ = context
        if self._physics_service is None:
            self._resolve_physics_service()
        if self._physics_service is None:
            return

        self._ensure_debug_pass(renderer)
        view_bb = self._view_bb()
        self._debug_shapes_submitted = 0

        if self.draw_statics:
            for static in self._physics_service.get_statics():
                if self._is_visible(getattr(static, "_pm_shapes", None), view_bb):
                    self._submit_static(renderer, static)

        if self.draw_bodies:
            for record in self._physics_service.iter_body_states():
                if self._debug_cap_reached():
                    return
                if self._is_visible(record.pm_shapes, view_bb):
                    self._submit_body_record(renderer, record)

        if self.draw_areas:
            for record in self._physics_service._area_records:
                if self._debug_cap_reached():
                    return
                if self._is_visible(record.pm_shapes, view_bb):
                    self._submit_area_record(renderer, record)

        if self.draw_contacts:
            self._submit_contact_points(renderer, view_bb)

    def _debug_cap_reached(self) -> bool:
        """Return whether the max_debug_shapes budget has been exhausted."""
        if self.max_debug_shapes is None:
            return False
        return self._debug_shapes_submitted >= self.max_debug_shapes

    def _consume_debug_shapes(self, count: int) -> bool:
        """Try to consume ``count`` from the debug shape budget; return False
        when full."""
        if self.max_debug_shapes is None:
            return True
        if self._debug_shapes_submitted >= self.max_debug_shapes:
            return False
        self._debug_shapes_submitted += count
        return True

    def draw(self, canvas: Canvas) -> None:
        """Legacy custom-draw hook kept as a safe no-op for old callers."""
        _ = canvas

    def _resolve_physics_service(self) -> None:
        """Locate the global ``Physics`` service from the unit, if present."""
        if self.unit is None:
            return

        svc = self.unit.one_or_none("@Physics", scope="global")
        if svc is None:
            svc = self.unit.one_or_none("Physics", scope="global")
        if svc is None:
            return

        from .service import Physics

        if isinstance(svc, Physics):
            self._physics_service = svc

    def _ensure_debug_pass(self, renderer: Renderer) -> None:
        """Create the world-space ``physics_debug`` pass on the renderer if needed."""
        camera = self._resolve_camera()
        renderer.create_pass(
            _DEBUG_PASS,
            order=5,
            min_layer=Layer.DEBUG,
            max_layer=Layer.DEBUG,
            screen_space=False,
            camera=camera,
            viewport_scissor=getattr(camera, "viewport", None) if camera else None,
        )

    def _resolve_camera(self) -> Any | None:
        """Return the active ``Camera2D`` (or the App camera), if any."""
        if self.unit is None:
            return None

        camera = self.unit.one_or_none("Camera2D", scope="global")
        if camera is not None:
            return camera

        app = self.unit.one_or_none("@App", scope="global")
        return getattr(app, "camera", None) if app is not None else None

    def _view_bb(self) -> tuple[float, float, float, float] | None:
        """Return the camera view rect expanded by the cull margin, or ``None``."""
        camera = self._resolve_camera()
        if camera is None or not hasattr(camera, "get_view_rect"):
            return None

        left, top, right, bottom = camera.get_view_rect()
        min_x = min(left, right) - _CULL_MARGIN
        max_x = max(left, right) + _CULL_MARGIN
        min_y = min(top, bottom) - _CULL_MARGIN
        max_y = max(top, bottom) + _CULL_MARGIN
        return (min_x, min_y, max_x, max_y)

    @staticmethod
    def _is_visible(
        pm_shapes: Any, view_bb: tuple[float, float, float, float] | None
    ) -> bool:
        """Return whether any of the given pymunk shapes intersects the view
        bounding box."""
        if view_bb is None:
            return True
        if not pm_shapes:
            return False

        view_left, view_top, view_right, view_bottom = view_bb
        for pm_shape in pm_shapes:
            bb = getattr(pm_shape, "bb", None)
            if bb is None:
                continue
            left = float(min(bb.left, bb.right))
            right = float(max(bb.left, bb.right))
            top = float(min(bb.top, bb.bottom))
            bottom = float(max(bb.top, bb.bottom))
            if (
                right >= view_left
                and left <= view_right
                and bottom >= view_top
                and top <= view_bottom
            ):
                return True
        return False

    def _submit_body(self, renderer: Renderer, body: PhysicsBody) -> None:
        """Submit debug primitives for a ``PhysicsBody`` component."""
        from plyunit.core.components.physics import BodyType

        if body._pm_body is None:
            return

        if body.is_sleeping:
            color = _COLOR_DYNAMIC_SLEEPING
        elif body.body_type == BodyType.KINEMATIC:
            color = _COLOR_KINEMATIC
        else:
            color = _COLOR_DYNAMIC

        world = body.world_transform_lerp()
        pos_x, pos_y = world.position
        self._submit_shapes(
            renderer,
            body.shapes,
            pos_x,
            pos_y,
            world.rotation,
            color,
            sensor_fill=False,
        )
        if self.draw_aabb:
            self._submit_aabb(renderer, body._pm_shapes, color)

    def _submit_body_record(self, renderer: Renderer, record: Any) -> None:
        """Submit debug primitives for an SoA body state record."""
        from plyunit.core.components.physics import BodyType

        if record.pm_body.is_sleeping:
            color = _COLOR_DYNAMIC_SLEEPING
        elif record.body_type == BodyType.KINEMATIC:
            color = _COLOR_KINEMATIC
        else:
            color = _COLOR_DYNAMIC

        pos_x, pos_y, angle = self._record_transform(record)
        self._submit_shapes(
            renderer,
            record.shape_defs,
            pos_x,
            pos_y,
            angle,
            color,
            sensor_fill=False,
        )
        if self.draw_aabb:
            self._submit_aabb(renderer, record.pm_shapes, color)

    def _submit_static(self, renderer: Renderer, static: StaticBody) -> None:
        """Submit debug primitives for a ``StaticBody`` (no rotation)."""
        pos_x, pos_y = static.position
        self._submit_shapes(
            renderer,
            static.shapes,
            pos_x,
            pos_y,
            0.0,
            _COLOR_STATIC,
            sensor_fill=False,
        )
        if self.draw_aabb:
            self._submit_aabb(renderer, static._pm_shapes, _COLOR_STATIC)

    def _submit_area(self, renderer: Renderer, area: PhysicsArea) -> None:
        """Submit filled debug primitives for a ``PhysicsArea`` component."""
        if area._pm_body is None:
            return

        world = area.world_transform_lerp()
        pos_x, pos_y = world.position
        self._submit_shapes(
            renderer,
            area.shapes,
            pos_x,
            pos_y,
            world.rotation,
            _COLOR_AREA,
            sensor_fill=True,
        )
        if self.draw_aabb:
            self._submit_aabb(renderer, area._pm_shapes, _COLOR_AREA)

    def _submit_area_record(self, renderer: Renderer, record: Any) -> None:
        """Submit filled debug primitives for an SoA area record."""
        pos_x, pos_y, angle = self._record_transform(record)
        self._submit_shapes(
            renderer,
            record.shape_defs,
            pos_x,
            pos_y,
            angle,
            _COLOR_AREA,
            sensor_fill=True,
        )
        if self.draw_aabb:
            self._submit_aabb(renderer, record.pm_shapes, _COLOR_AREA)

    def _submit_shapes(
        self,
        renderer: Renderer,
        shapes: list[PhysicsShape],
        pos_x: float,
        pos_y: float,
        angle_deg: float,
        color: tuple[int, int, int, int],
        *,
        sensor_fill: bool,
    ) -> None:
        """Submit debug primitives for a list of shape definitions at a body
        transform."""
        from plyunit.core.components.physics import (
            BoxShape,
            CircleShape,
            PolygonShape,
            SegmentShape,
        )

        for shape in shapes:
            if not self._consume_debug_shapes(1):
                return
            ox, oy = shape.offset
            shape_x, shape_y = _transform_point(pos_x, pos_y, ox, oy, angle_deg)

            if isinstance(shape, CircleShape):
                fill = (color[0], color[1], color[2], 40) if sensor_fill else None
                renderer.render_circle(
                    center=(shape_x, shape_y),
                    radius=shape.radius,
                    color=fill,
                    border_color=color,
                    thickness=2.0,
                    **self._debug_state(),
                )
                end_x = shape_x + math.cos(math.radians(angle_deg)) * shape.radius
                end_y = shape_y + math.sin(math.radians(angle_deg)) * shape.radius
                renderer.render_line(
                    start=(shape_x, shape_y),
                    end=(end_x, end_y),
                    color=color,
                    thickness=1.5,
                    **self._debug_state(),
                )
                continue

            if isinstance(shape, BoxShape):
                renderer.render_rect(
                    rect=(shape_x, shape_y, shape.width, shape.height),
                    color=(color[0], color[1], color[2], 40) if sensor_fill else None,
                    border_color=color,
                    thickness=2.0,
                    rotation=angle_deg,
                    origin=(shape.width / 2.0, shape.height / 2.0),
                    **self._debug_state(),
                )
                continue

            if isinstance(shape, SegmentShape):
                start = _transform_point(
                    pos_x,
                    pos_y,
                    ox + shape.a[0],
                    oy + shape.a[1],
                    angle_deg,
                )
                end = _transform_point(
                    pos_x,
                    pos_y,
                    ox + shape.b[0],
                    oy + shape.b[1],
                    angle_deg,
                )
                renderer.render_line(
                    start=start,
                    end=end,
                    color=color,
                    thickness=max(2.0, shape.radius * 2.0),
                    **self._debug_state(),
                )
                continue

            if isinstance(shape, PolygonShape) and len(shape.vertices) >= 3:
                vertices = shape.vertices
                for index, start_local in enumerate(vertices):
                    end_local = vertices[(index + 1) % len(vertices)]
                    start = _transform_point(
                        pos_x,
                        pos_y,
                        ox + start_local[0],
                        oy + start_local[1],
                        angle_deg,
                    )
                    end = _transform_point(
                        pos_x,
                        pos_y,
                        ox + end_local[0],
                        oy + end_local[1],
                        angle_deg,
                    )
                    renderer.render_line(
                        start=start,
                        end=end,
                        color=color,
                        thickness=2.0,
                        **self._debug_state(),
                    )

    def _submit_aabb(
        self,
        renderer: Renderer,
        pm_shapes: Any,
        color: tuple[int, int, int, int],
    ) -> None:
        """Submit axis-aligned bounding boxes for the given pymunk shapes."""
        if not pm_shapes:
            return
        for pm_shape in pm_shapes:
            bb = getattr(pm_shape, "bb", None)
            if bb is None:
                continue
            left = float(min(bb.left, bb.right))
            right = float(max(bb.left, bb.right))
            top = float(min(bb.top, bb.bottom))
            bottom = float(max(bb.top, bb.bottom))
            renderer.render_rect(
                rect=(left, top, right - left, bottom - top),
                border_color=color,
                thickness=1.0,
                **self._debug_state(),
            )

    def _submit_contact_points(
        self,
        renderer: Renderer,
        view_bb: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Submit arbiter contact points, deduplicated and culled to the view."""
        if self._physics_service is None:
            return

        space = getattr(self._physics_service.backend, "_space", None)
        if space is None:
            return

        seen: set[int] = set()
        submitted = 0

        def submit_arbiter(arbiter: Any) -> None:
            """Submit contact points of one arbiter (deduplicated by id)."""
            nonlocal submitted
            arbiter_id = id(arbiter)
            if arbiter_id in seen:
                return
            seen.add(arbiter_id)
            contacts = getattr(arbiter, "contact_point_set", None)
            if contacts is None:
                return
            for contact in contacts.points:
                if (
                    self.max_contact_points is not None
                    and submitted >= self.max_contact_points
                ):
                    return
                point = contact.point_a
                px, py = float(point.x), float(point.y)
                if view_bb is not None:
                    left, top, right, bottom = view_bb
                    if px < left or px > right or py < top or py > bottom:
                        continue
                renderer.render_circle(
                    center=(px, py),
                    radius=3.0,
                    color=_COLOR_CONTACT,
                    **self._debug_state(),
                )
                submitted += 1

        for body_pm in list(getattr(space, "bodies", ())):
            each_arbiter = getattr(body_pm, "each_arbiter", None)
            if each_arbiter is not None:
                each_arbiter(submit_arbiter)

    def _record_transform(self, record: Any) -> tuple[float, float, float]:
        """Return the record's render-interpolated ``(x, y, angle)`` at the current
        alpha."""
        alpha = self._render_alpha()
        interpolated = getattr(record, "interpolated", None)
        if interpolated is not None:
            return interpolated(alpha)
        return (
            record.prev_x + (record.x - record.prev_x) * alpha,
            record.prev_y + (record.y - record.prev_y) * alpha,
            record.prev_angle + (record.angle - record.prev_angle) * alpha,
        )

    def _render_alpha(self) -> float:
        """Return the window's render interpolation alpha, defaulting to 1.0."""
        if self.unit is None:
            return 1.0

        window = self.unit.one_or_none("@Window", scope="global")
        if window is None:
            return 1.0
        return float(window.alpha)

    @staticmethod
    def _debug_state() -> dict[str, Any]:
        """Return the shared render state (z, layer, pass, blend) for debug
        primitives."""
        return {
            "z": _DEBUG_Z,
            "layer": Layer.DEBUG,
            "pass_name": _DEBUG_PASS,
            "blend_mode": BlendMode.ALPHA,
            "screen_space": False,
        }
