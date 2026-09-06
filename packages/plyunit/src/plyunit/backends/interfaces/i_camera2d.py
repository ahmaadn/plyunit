"""Center-follow 2D camera contract for the host backend.

This module defines :class:`ICamera2D` — a pygpen-style 2D camera protocol
(center-follow + dead zone + letterbox). The host backend implements a
concrete type satisfying this protocol's attributes and methods so domain
code can type-annotate against the stable camera surface.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ICamera2D(Protocol):
    """Center-follow 2D camera (pygpen-style).

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

    size: tuple[int, int]
    rotation: float
    pos: list[float]
    slowness: float
    target_node: Any | None
    target_position: tuple[float, float] | None
    pivot: tuple[float, float]
    use_clamping: bool
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    use_dead_zone: bool
    dead_zone_width: float
    dead_zone_height: float
    viewport: tuple[float, float, float, float]

    def setup(
        self, window_width: int | None = None, window_height: int | None = None
    ) -> None:
        """Initialize the camera for the given window size.

        Args:
            window_width: Window width in pixels; ``None`` queries the backend.
            window_height: Window height in pixels; ``None`` queries the
                backend.
        """
        ...

    def update(self, dt: float) -> None:
        """Advance the follow, dead-zone, and clamping logic by one frame.

        Args:
            dt: Frame delta time in seconds.
        """
        ...

    def start_frame(self) -> None:
        """Begin a camera-transformed rendering pass (push the camera)."""
        ...

    def end_frame(self) -> None:
        """End the camera-transformed rendering pass (pop the camera)."""
        ...

    def set_target(self, target: Any | tuple[float, float] | None) -> None:
        """Set the follow target.

        Args:
            target: A node-like object with ``pos``/``center``, a world
                ``(x, y)`` tuple, or ``None`` to stop following.
        """
        ...

    def set_pivot(
        self,
        x: float,
        y: float,
        sprite_size: tuple[float, float] | None = None,
    ) -> None:
        """Set the pivot offset added to the follow target.

        Args:
            x: Horizontal pivot offset in world units.
            y: Vertical pivot offset in world units.
            sprite_size: Optional sprite size; when given, the pivot is
                computed as a fraction of it.
        """
        ...

    def set_limits(
        self, min_x: float, min_y: float, max_x: float, max_y: float
    ) -> None:
        """Enable clamping of ``pos`` to the given world bounds.

        Args:
            min_x: Minimum world x.
            min_y: Minimum world y.
            max_x: Maximum world x.
            max_y: Maximum world y.
        """
        ...

    def set_dead_zone(self, width: float, height: float) -> None:
        """Enable a dead zone of the given size around ``pos``.

        Args:
            width: Dead zone width in world units.
            height: Dead zone height in world units.
        """
        ...

    def clear_dead_zone(self) -> None:
        """Disable the dead zone."""
        ...

    def set_zoom(self, zoom: float) -> None:
        """Set an explicit zoom multiplier.

        Args:
            zoom: Zoom multiplier (1.0 = no zoom).
        """
        ...

    def set_virtual_size(self, width: int, height: int) -> None:
        """Set the virtual viewport size kept letterboxed to the window.

        Args:
            width: Virtual width in world units.
            height: Virtual height in world units.
        """
        ...

    def teleport(self, target: Any | tuple[float, float]) -> None:
        """Snap the camera directly onto a target without follow easing.

        Args:
            target: A node-like object or a world ``(x, y)`` tuple.
        """
        ...

    def move(self, movement: tuple[float, float]) -> None:
        """Move the camera focus by an offset.

        Args:
            movement: ``(dx, dy)`` offset in world units.
        """
        ...

    def calculate_zoom(self) -> float:
        """Compute the effective zoom from window and virtual sizes.

        Returns:
            The effective zoom multiplier.
        """
        ...

    def get_view_rect(self) -> tuple[float, float, float, float]:
        """Compute the axis-aligned world rectangle currently in view.

        Returns:
            The ``(x, y, width, height)`` view rectangle in world units.
        """
        ...

    def world_to_screen(
        self, world_x: float, world_y: float
    ) -> tuple[float, float]:
        """Convert a world point to screen (window) coordinates.

        Args:
            world_x: World x coordinate.
            world_y: World y coordinate.

        Returns:
            The ``(x, y)`` screen coordinates in pixels.
        """
        ...

    def screen_to_world(
        self, screen_x: float, screen_y: float
    ) -> tuple[float, float]:
        """Convert a screen (window) point to world coordinates.

        Args:
            screen_x: Screen x coordinate in pixels.
            screen_y: Screen y coordinate in pixels.

        Returns:
            The ``(x, y)`` world coordinates.
        """
        ...


__all__ = ["ICamera2D"]
