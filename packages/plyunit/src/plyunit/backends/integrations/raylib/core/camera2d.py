"""Camera2D — center-follow camera (pygpen style).

This module provides :class:`Camera2D` — a 2D camera service that follows
a target with easing, dead zone, letterbox, and world bounds options.

:meth:`Camera2D.update` is called by the user once per frame from
``App.update(dt)`` — ``App`` no longer owns a render pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyray as pr

from plyunit.backends.interfaces import ICamera2D
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils import math

if TYPE_CHECKING:
    from plyunit.core.units.node_unit import NodeUnit


def _smooth_approach(val: float, target: float, slowness: float, dt: float) -> float:
    """Pygpen ``smooth_approach``: ease toward the target with slowness.

    Args:
        val: Current value.
        target: The target to chase.
        slowness: Easing factor. ``<= 0`` = snap directly to the target.
        dt: Delta time (seconds).

    Returns:
        The new value after easing.
    """
    if slowness <= 0.0:
        return target
    return val + (target - val) / slowness * min(dt, slowness)


class Camera2D(ServiceUnit, ICamera2D):
    """Center-follow 2D camera + optional dead zone + letterbox.

    Attributes:
        size: Virtual viewport (world units) kept letterboxed to the window.
        rotation: Degrees.
        pos: Current focus point (world center), float list ``[x, y]``.
        slowness: Follow ease (pygpen). ``<= 0`` snaps; higher = slower.
        target_node / target_position: What to follow.
        pivot: Offset added to follow target.
        use_clamping / min_* / max_*: Optional world bounds on ``pos``.
        use_dead_zone / dead_zone: Soft box around ``pos`` before follow moves.
    """

    def __init__(
        self,
        size: tuple[int, int],
        position: tuple[float, float] = (0.0, 0.0),
        pivot: tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        zoom: float = 1.0,
        slowness: float = 1.0,
    ) -> None:
        """Initialize the camera with a virtual size and follow parameters.

        Args:
            size: Virtual viewport size ``(width, height)`` in world units.
            position: Initial focus point (world center).
            pivot: Offset added to the follow target.
            rotation: Initial rotation in degrees.
            zoom: User zoom factor (multiplied with the letterbox base zoom).
            slowness: Follow easing factor; ``<= 0`` snaps instantly.
        """
        super().__init__("Camera2D", tags={"service", "camera2d", "camera"})

        self.size = size
        self.rotation = rotation
        self.pos = [position[0], position[1]]
        self.target_position: tuple[float, float] | None = (
            position[0],
            position[1],
        )
        self.pivot = (pivot[0], pivot[1])
        self.target_node = None
        self.slowness = slowness

        self.use_clamping = False
        self.min_x = self.min_y = 0.0
        self.max_x = self.max_y = 0.0

        self.use_dead_zone = False
        self.dead_zone_width = 0.0
        self.dead_zone_height = 0.0

        self._zoom = max(0.0, zoom)
        self._camera = None
        self._offset = (0.0, 0.0)
        self._window_size = size
        self._viewport = (0.0, 0.0, float(size[0]), float(size[1]))

        self._temp_vec_ws = pr.Vector2(0.0, 0.0)
        self._temp_vec_sw = pr.Vector2(0.0, 0.0)

        self._is_snap_next_frame = False

    @property
    def viewport(self) -> tuple[float, float, float, float]:
        """Letterboxed screen-space viewport ``(x, y, w, h)``."""
        return self._viewport

    @property
    def lerp_speed(self) -> float:
        """Alias for :attr:`slowness` (legacy example compatibility)."""
        return self.slowness

    @lerp_speed.setter
    def lerp_speed(self, value: float) -> None:
        self.slowness = value

    @property
    def target(self) -> tuple[float, float]:
        """Desired world focus = follow target + pivot."""
        if self.target_node is not None:
            x, y = self.target_node.transform.world.position
            return (x + self.pivot[0], y + self.pivot[1])
        if self.target_position is not None:
            return (
                self.target_position[0] + self.pivot[0],
                self.target_position[1] + self.pivot[1],
            )
        return (self.pos[0], self.pos[1])

    def start_frame(self) -> None:
        """Enter raylib 2D camera mode for this frame.

        Raises:
            RuntimeError: If :meth:`setup` has not been called.
        """
        if self._camera is None:
            raise RuntimeError(
                "Camera2D belum di-setup. Panggil setup() sebelum begin()."
            )
        pr.begin_mode_2d(self._camera)

    def end_frame(self) -> None:
        """Exit raylib 2D camera mode."""
        pr.end_mode_2d()

    def setup(
        self, window_width: int | None = None, window_height: int | None = None
    ) -> None:
        """Initialize zoom/viewport calculations against the window size.

        Args:
            window_width: Window width (optional; keeps the current stored
                size when None).
            window_height: Window height (optional; keeps the current stored
                size when None).
        """
        if window_width and window_height:
            self._window_size = (window_width, window_height)
        self._recalc_zoom_and_viewport()

    def _recalc_zoom_and_viewport(self) -> None:
        """Recalculate the camera zoom, viewport, and offset.

        Creates the ``pr.Camera2D`` on the first call and updates its
        fields on subsequent calls.
        """
        width, height = self.size
        window_width, window_height = self._window_size
        base_zoom = min(window_width / width, window_height / height)

        viewport_width = width * base_zoom
        viewport_height = height * base_zoom
        viewport_x = (window_width - viewport_width) * 0.5
        viewport_y = (window_height - viewport_height) * 0.5
        self._viewport = (viewport_x, viewport_y, viewport_width, viewport_height)
        self._offset = (
            viewport_x + viewport_width / 2,
            viewport_y + viewport_height / 2,
        )
        total_zoom = base_zoom * self._zoom
        if self._camera is None:
            self._camera = pr.Camera2D(
                pr.Vector2(self._offset[0], self._offset[1]),
                pr.Vector2(self.pos[0], self.pos[1]),
                self.rotation,
                total_zoom,
            )
        else:
            self._camera.offset = pr.Vector2(self._offset[0], self._offset[1])
            self._camera.target = pr.Vector2(self.pos[0], self.pos[1])
            self._camera.zoom = total_zoom
            self._camera.rotation = self.rotation

    def calculate_zoom(self) -> float:
        """Return the final zoom value used by the camera.

        Returns:
            The effective zoom (letterbox base * user zoom).
        """
        window_width, window_height = self._window_size
        return (
            min(window_width / self.size[0], window_height / self.size[1]) * self._zoom
        )

    def set_target(self, target: NodeUnit | tuple[float, float] | None) -> None:
        """Set the follow target (Node, tuple, or None for raw pos).

        Args:
            target: A NodeUnit, an ``(x, y)`` tuple, or ``None`` to
                disable following.
        """
        from plyunit.core.units.node_unit import NodeUnit

        if isinstance(target, NodeUnit):
            self.target_node = target
            self.target_position = None
        elif isinstance(target, tuple) and len(target) == 2:
            self.target_position = (target[0], target[1])
            self.target_node = None
        else:
            self.target_position = None
            self.target_node = None

    def set_pivot(
        self, x: float, y: float, sprite_size: tuple[float, float] | None = None
    ) -> None:
        """Set the pivot offset (optionally scaled by sprite size).

        Args:
            x: Pivot X (or a fraction when ``sprite_size`` is given).
            y: Pivot Y (or a fraction when ``sprite_size`` is given).
            sprite_size: ``(w, h)`` used to convert fractions to world units.
        """
        if sprite_size is not None:
            x = x * sprite_size[0]
            y = y * sprite_size[1]
        self.pivot = (x, y)

    def set_limits(
        self, min_x: float, min_y: float, max_x: float, max_y: float
    ) -> None:
        """Enable world bounds (``pos`` will be clamped to this box).

        Args:
            min_x: Left bound.
            min_y: Bottom bound.
            max_x: Right bound.
            max_y: Top bound.
        """
        self.use_clamping = True
        self.min_x = float(min_x)
        self.min_y = float(min_y)
        self.max_x = float(max_x)
        self.max_y = float(max_y)

    def set_dead_zone(self, width: float, height: float) -> None:
        """Enable a dead zone (world units) around the ``pos`` focus."""
        self.use_dead_zone = True
        self.dead_zone_width = max(0.0, float(width))
        self.dead_zone_height = max(0.0, float(height))

    def clear_dead_zone(self) -> None:
        """Disable the dead zone."""
        self.use_dead_zone = False
        self.dead_zone_width = 0.0
        self.dead_zone_height = 0.0

    def set_zoom(self, zoom: float) -> None:
        """Set the user zoom (multiplied with the letterbox base zoom)."""
        self._zoom = max(0.0, float(zoom))
        if self._camera is not None:
            self._recalc_zoom_and_viewport()

    def set_virtual_size(self, width: int, height: int) -> None:
        """Set the virtual size (world units) for letterboxing."""
        self.size = (int(width), int(height))
        self._recalc_zoom_and_viewport()

    def teleport(
        self,
        target: NodeUnit | tuple[float, float],
        instant: bool = True,
    ) -> None:
        """Set the follow target; by default snap ``pos`` + camera immediately.

        Args:
            target: NodeUnit or ``(x, y)`` to follow.
            instant: If ``True`` (default), ``pos`` and ``_camera.target``
                snap to the target right away and the next frame also
                skips smoothing (so ``pivot``/target changes made after
                :meth:`teleport` are absorbed too). If ``False``, only
                ``set_target`` is called — ``pos`` is left as-is and the
                smooth transition is performed by :meth:`update` via
                smoothing.
        """
        self.set_target(target)
        if instant:
            self._is_snap_next_frame = True

        tx, ty = self.target
        self.pos[0] = float(tx)
        self.pos[1] = float(ty)
        if self.use_clamping:
            self.pos[0] = math.clamp(self.pos[0], self.min_x, self.max_x)
            self.pos[1] = math.clamp(self.pos[1], self.min_y, self.max_y)
        if self._camera is not None:
            self._camera.target = pr.Vector2(self.pos[0], self.pos[1])

    def move(self, movement: tuple[float, float]) -> None:
        """Shift the camera's ``pos`` by ``movement`` (without smoothing)."""
        self.pos[0] += movement[0]
        self.pos[1] += movement[1]

    def draw_letterbox(self) -> None:
        """Draw black letterbox bars over the area outside the virtual viewport."""
        if self._camera is None:
            return
        window_w, window_h = self._window_size
        vx, vy, vw, vh = self._viewport
        if vx > 0:
            pr.draw_rectangle(0, 0, int(vx), int(window_h), pr.BLACK)
            pr.draw_rectangle(int(vx + vw), 0, int(vx), int(window_h), pr.BLACK)
        if vy > 0:
            pr.draw_rectangle(0, 0, int(window_w), int(vy), pr.BLACK)
            pr.draw_rectangle(0, int(vy + vh), int(window_w), int(vy), pr.BLACK)

    def update(self, dt: float) -> None:
        """Once per frame: resize + dead zone + ease ``pos`` + push to raylib.

        Called by the user from ``App.update(dt)`` once per frame.

        Args:
            dt: Delta time (seconds).
        """
        if pr.is_window_resized() and self._camera is not None:
            self._window_size = (pr.get_screen_width(), pr.get_screen_height())
            self._recalc_zoom_and_viewport()

        if self._camera is None:
            return

        if self._is_snap_next_frame:
            tx, ty = self.target
            self.pos[0] = float(tx)
            self.pos[1] = float(ty)
            if self.use_clamping:
                self.pos[0] = math.clamp(self.pos[0], self.min_x, self.max_x)
                self.pos[1] = math.clamp(self.pos[1], self.min_y, self.max_y)
            self._camera.target.x = self.pos[0]
            self._camera.target.y = self.pos[1]
            self._camera.rotation = self.rotation
            self._is_snap_next_frame = False
            return

        tx, ty = self.target
        move_x, move_y = tx, ty

        if self.use_dead_zone:
            half_w = self.dead_zone_width * 0.5
            half_h = self.dead_zone_height * 0.5
            dx = tx - self.pos[0]
            dy = ty - self.pos[1]
            move_x = self.pos[0]
            move_y = self.pos[1]
            if abs(dx) > half_w:
                move_x = tx - (half_w if dx > 0 else -half_w)
            if abs(dy) > half_h:
                move_y = ty - (half_h if dy > 0 else -half_h)

        self.pos[0] = _smooth_approach(self.pos[0], move_x, self.slowness, dt)
        self.pos[1] = _smooth_approach(self.pos[1], move_y, self.slowness, dt)

        if self.use_clamping:
            self.pos[0] = math.clamp(self.pos[0], self.min_x, self.max_x)
            self.pos[1] = math.clamp(self.pos[1], self.min_y, self.max_y)

        self._camera.target.x = self.pos[0]
        self._camera.target.y = self.pos[1]
        self._camera.rotation = self.rotation

    def get_view_rect(self) -> tuple[float, float, float, float]:
        """Return the world view rect ``(left, top, right, bottom)``."""
        if self._camera is None:
            return 0.0, 0.0, float(self.size[0]), float(self.size[1])
        left, top = self.screen_to_world(0, 0)
        right, bottom = self.screen_to_world(self._window_size[0], self._window_size[1])
        return float(left), float(top), float(right), float(bottom)

    def world_to_screen(self, world_x: float, world_y: float) -> tuple[float, float]:
        """Convert world coordinates to screen coordinates."""
        if self._camera is None:
            return (world_x, world_y)
        self._temp_vec_ws.x = world_x
        self._temp_vec_ws.y = world_y
        result = pr.get_world_to_screen_2d(self._temp_vec_ws, self._camera)
        return (result.x, result.y)

    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen coordinates to world coordinates."""
        if self._camera is None:
            return (screen_x, screen_y)
        self._temp_vec_sw.x = screen_x
        self._temp_vec_sw.y = screen_y
        result = pr.get_screen_to_world_2d(self._temp_vec_sw, self._camera)
        return (result.x, result.y)
