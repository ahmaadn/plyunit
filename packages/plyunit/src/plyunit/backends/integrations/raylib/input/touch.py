"""raylib touch service unit (primary touch point, index 0).

Defines the :class:`Touch` class for reading the primary touch
state (point 0) with edge detection against the previous frame, and
deferring ``touch.*`` events to the EventBus.
"""

from __future__ import annotations

import logging

import pyray as pr

from plyunit.backends.ports.input import ITouch
from plyunit.core.units.service_unit import ServiceUnit

__all__ = ("Touch",)

logger = logging.getLogger(__name__)


EVENT_PRESSED = "touch.pressed"
EVENT_DOWN = "touch.down"
EVENT_RELEASED = "touch.released"


# TODO: CURENTLY NOT TESTED TO TOUCH
class Touch(ServiceUnit, ITouch):
    """Primary touch (point 0) with edges against the previous frame.

    Attributes:
        emit_to_bus: Whether touch events are deferred to the EventBus.
        position: The last touch position ``(x, y)``.
        count: Number of active touch points this frame.
    """

    def __init__(self) -> None:
        """Initialize a Touch instance with an empty touch state."""
        super().__init__("Touch", tags={"service", "input", "touch"})
        self.emit_to_bus: bool = True
        self.position: tuple[float, float] = (0.0, 0.0)
        self.count: int = 0
        self._prev_down: bool = False
        self._down: bool = False
        self._app = None
        self._bus = None

    def on_attach(self, app) -> None:
        """Remember the owning app."""
        self._app = app

        bus = app.one_or_none("@EventBus", scope="global")
        if bus:
            self._bus = bus
        if bus is None and self.emit_to_bus:
            self.emit_to_bus = False
            logger.info("Event bus not found and emit to bus auto disable")

    def on_detach(self, app) -> None:
        """Forget the owning app and the cached EventBus."""
        self._app = None
        self._bus = None

    def _allow_edge(self) -> bool:
        """Check whether edge polling is allowed on this substep.

        Returns ``True`` when there is no App (e.g. isolated unit
        tests) or when this is the first fixed step within the
        current wall-clock frame.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        return self._app is None or bool(self._app.is_first_fixed_step)

    def update(self, dt: float) -> None:
        """Update the touch state and defer ``touch.*`` events to the EventBus.

        Args:
            dt: Delta time of the current frame, in seconds. Not
                used directly; raylib polling is frame-based.
        """
        self._prev_down = self._down
        self.count = pr.get_touch_point_count()
        self._down = self.count > 0
        if self._down:
            pos = pr.get_touch_position(0)
            self.position = (pos.x, pos.y)

        # Idle frames (no touch now or before) can never fire an event,
        # so skip the EventBus lookup entirely.
        if self.emit_to_bus and (self._down or self._prev_down):
            self._emit_events()

    def _emit_events(self) -> None:
        """Defer the ``touch.*`` events that fired this frame."""
        bus = self.one_or_none("@EventBus", scope="global")
        if bus is None:
            return
        # A press/release edge is exactly a change of state, so the
        # (cheap) comparison runs before the App lookup.
        changed = self._down != self._prev_down and self._allow_edge()
        fired = (
            (EVENT_PRESSED, changed and self._down),
            (EVENT_DOWN, self._down),
            (EVENT_RELEASED, changed and not self._down),
        )
        for event_name, is_fired in fired:
            if is_fired and bus.has_listeners(event_name):
                bus.defer(
                    event_name,
                    device="touch",
                    position=self.position,
                    count=self.count,
                )

    def is_down(self) -> bool:
        """Check whether the screen is currently touched (hold).

        Returns:
            bool: ``True`` if at least one touch point is active.
        """
        return self._down

    def is_pressed(self) -> bool:
        """Check whether the screen was just touched (edge down).

        Returns:
            bool: ``True`` if the touch started this frame.
        """
        return self._down and not self._prev_down and self._allow_edge()

    def is_released(self) -> bool:
        """Check whether the screen was just released (edge up).

        Returns:
            bool: ``True`` if the touch was released this frame.
        """
        return self._prev_down and not self._down and self._allow_edge()
