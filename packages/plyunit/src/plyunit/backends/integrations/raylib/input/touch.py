"""raylib touch service unit (primary touch point, index 0).

Defines the :class:`Touch` class for reading the primary touch
state (point 0) with edge detection against the previous frame, and
deferring ``touch.*`` events to the EventBus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyray as pr

from plyunit.backends.interfaces.i_input import ITouch
from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from plyunit.events.event_bus import EventBus


__all__ = ("Touch",)


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
        self._event_bus: EventBus | None = None
        self._prev_down = False
        self._down = False
        self.position: tuple[float, float] = (0.0, 0.0)
        self.count: int = 0

    def _defer_if_listened(self, bus: EventBus, event_name: str, **kwargs: Any) -> None:
        """Defer an event to the EventBus only when it has listeners.

        Args:
            bus: Target EventBus instance.
            event_name: Name of the event to defer.
            **kwargs: Additional event payload.
        """
        if bus.has_listeners(event_name):
            bus.defer(event_name, **kwargs)

    def _allow_edge(self) -> bool:
        """Check whether edge polling is allowed on this substep.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        app = self.one_or_none("@App", scope="global")
        return True if app is None else bool(app.is_first_fixed_step)

    def update(self, dt: float) -> None:
        """Update the touch state and defer ``touch.*`` events to the EventBus.

        Args:
            dt: Delta time of the current frame, in seconds. Not
                used directly; raylib polling is frame-based.
        """
        _ = dt
        self._prev_down = self._down
        self.count = pr.get_touch_point_count()
        self._down = self.count > 0
        if self._down:
            pos = pr.get_touch_position(0)
            self.position = (pos.x, pos.y)

        if not self.emit_to_bus:
            return
        bus = bus = self.one_or_none("@EventBus", scope="global")
        if bus is None:
            return
        payload = {
            "device": "touch",
            "position": self.position,
            "count": self.count,
        }
        if self.is_pressed():
            self._defer_if_listened(bus, "touch.pressed", **payload)
        if self.is_down():
            self._defer_if_listened(bus, "touch.down", **payload)
        if self.is_released():
            self._defer_if_listened(bus, "touch.released", **payload)

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
        return self._allow_edge() and self._down and not self._prev_down

    def is_released(self) -> bool:
        """Check whether the screen was just released (edge up).

        Returns:
            bool: ``True`` if the touch was released this frame.
        """
        return self._allow_edge() and (not self._down) and self._prev_down
