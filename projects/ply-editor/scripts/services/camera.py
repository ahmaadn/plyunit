"""Editor camera with explicit, clamped 2D zoom control.

Extends the engine's ``Camera2D`` with bounded zoom, fit-to-rect, and
pan-by helpers tailored for the editor viewport.
"""

import logging

import plyunit
from plyunit.core.types import PosType, RectType, SizeType
from scripts import constants as const

logger = logging.getLogger(__name__)


class CameraCanvas2D(plyunit.Camera2D):
    """2D camera with explicit, clamped zoom control.

    Attributes:
        zoom_min: Minimum zoom allowed.
        zoom_max: Maximum zoom allowed.
    """

    def __init__(
        self,
        size: SizeType,
        position: PosType = (0.0, 0.0),
        pivot: PosType = (0.0, 0.0),
        rotation: float = 0.0,
        zoom: float = 1.0,
        slowness: float = 1.0,
        *,
        zoom_min: float = const.ZOOM_MIN,
        zoom_max: float = const.ZOOM_MAX,
    ) -> None:
        """Create a camera and clamp the initial zoom.

        Args:
            size: Virtual camera size ``(width, height)`` in pixels.
            position: Initial world position.
            pivot: Rotation pivot in world units.
            rotation: Initial rotation in degrees.
            zoom: Initial user zoom, clamped to ``zoom_min``..``zoom_max``.
            slowness: Follow smoothing; ``1.0`` snaps immediately.
            zoom_min: Minimum allowed user zoom.
            zoom_max: Maximum allowed user zoom.
        """
        self.zoom_min = zoom_min
        self.zoom_max = zoom_max
        clamped = min(max(zoom, zoom_min), zoom_max)
        super().__init__(
            size=size,
            position=position,
            pivot=pivot,
            rotation=rotation,
            zoom=clamped,
            slowness=slowness,
        )
        self._user_zoom: float = clamped

    @property
    def zoom(self) -> float:
        """User-requested zoom (before letterbox scaling)."""
        return self._user_zoom

    @zoom.setter
    def zoom(self, value: float) -> None:
        """Set user zoom, clamped to the editor range."""
        self.set_zoom(value)

    def set_zoom(self, zoom: float) -> None:
        """Set user zoom, clamped to the editor range."""
        clamped = min(max(float(zoom), self.zoom_min), self.zoom_max)
        self._user_zoom = clamped
        super().set_zoom(clamped)

    def zoom_by(self, delta: float) -> float:
        """Change zoom multiplicatively (suitable for the scroll wheel).

        Args:
            delta: Relative step; positive zooms in.

        Returns:
            The clamped zoom value.
        """
        self.set_zoom(self._user_zoom * (1.0 + delta))
        return self._user_zoom

    def effective_zoom(self) -> float:
        """Final zoom including letterbox scaling (world pixels to screen
        pixels)."""
        try:
            return float(self.calculate_zoom())
        except Exception:
            logger.debug(
                "calculate_zoom failed, falling back to user zoom", exc_info=True
            )
            return self._user_zoom

    def center_on(self, world_x: float, world_y: float) -> None:
        """Move the camera to a world position without follow animation."""
        self.pos[0] = float(world_x)
        self.pos[1] = float(world_y)
        self.set_target((float(world_x), float(world_y)))

    def pan_by(self, dx: float, dy: float) -> None:
        """Shift the camera relative to its current position."""
        self.center_on(self.pos[0] + dx, self.pos[1] + dy)

    def zoom_step(self, steps: float, step_size: float = const.ZOOM_STEP) -> float:
        """Change zoom by a fixed number of steps (for buttons and shortcuts).

        Args:
            steps: Number of steps; positive zooms in.
            step_size: Relative size of one step.

        Returns:
            The clamped zoom value.
        """
        return self.zoom_by(steps * step_size)

    def zoom_to_actual_size(self) -> None:
        """Set zoom to 1:1 so one image pixel equals one screen pixel."""
        self.set_zoom(1.0)

    def fit_to_rect(
        self, rect: RectType, viewport: SizeType, *, padding: float = 0.92
    ) -> None:
        """Adjust zoom and position so a world rect fits in the viewport.

        Args:
            rect: World rect ``(x, y, w, h)`` to show in full.
            viewport: Display area ``(width, height)`` in screen pixels.
            padding: Fraction of space used; < 1 leaves a thin margin.

        Note:
            Non-positive rects or viewports are silently ignored to
            prevent the camera from jumping to infinity.
        """
        _, _, width, height = rect
        view_w, view_h = viewport
        if width <= 0 or height <= 0 or view_w <= 0 or view_h <= 0:
            return

        scale = min(view_w / width, view_h / height) * max(0.01, padding)
        effective = self.effective_zoom()
        current = self._user_zoom
        if effective > 0 and current > 0:
            scale *= current / effective

        self.set_zoom(scale)
        self.center_on(rect[0] + width * 0.5, rect[1] + height * 0.5)
