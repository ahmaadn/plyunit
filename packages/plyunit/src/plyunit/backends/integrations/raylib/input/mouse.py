"""raylib mouse service unit and button/cursor mapping constants.

Defines the button mapping constants (``MAP_BUTTON_MOUSE``) and
cursor mapping constants (``MAP_CURSOR_MOUSE``), the
:data:`CursorType` type alias, and the :class:`Mouse` class for
reading and controlling mouse input.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Literal

import pyray as pr

from packages.plyunit.src.plyunit.backends.interfaces import IMouse
from packages.plyunit.src.plyunit.backends.interfaces.i_input import (
    BUTTON_MOUSE_KEY,
    CURSOR_MOUSE_KEY,
)
from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from plyunit.events.event_bus import EventBus


__all__ = ("MAP_BUTTON_MOUSE", "MAP_CURSOR_MOUSE", "Mouse")

# Mapping of mouse button names to ``pr.MouseButton`` constants. Each
# key is a user-facing name string; each value is a raylib constant.
# Mapping by category:
#   left / right / middle: standard primary buttons
#   side / extra: side buttons
#   forward / back: browser navigation buttons
MAP_BUTTON_MOUSE: dict[BUTTON_MOUSE_KEY, int] = {
    "left": pr.MouseButton.MOUSE_BUTTON_LEFT,
    "right": pr.MouseButton.MOUSE_BUTTON_RIGHT,
    "middle": pr.MouseButton.MOUSE_BUTTON_MIDDLE,
    "side": pr.MouseButton.MOUSE_BUTTON_SIDE,
    "extra": pr.MouseButton.MOUSE_BUTTON_EXTRA,
    "forward": pr.MouseButton.MOUSE_BUTTON_FORWARD,
    "back": pr.MouseButton.MOUSE_BUTTON_BACK,
}

# Mapping of cursor names to ``pr.MouseCursor`` constants. Each key
# is a cursor name string; each value is a raylib constant:
#   arrow: standard cursor
#   ibeam: text/caret cursor
#   crosshair: precision cursor
#   pointing_hand: link cursor
#   resize_ew / resize_ns / resize_nwse / resize_nesw / resize_all:
#     directional resize cursors
#   not_allowed: prohibition cursor
MAP_CURSOR_MOUSE: dict[CURSOR_MOUSE_KEY, int] = {
    "arrow": pr.MouseCursor.MOUSE_CURSOR_ARROW,
    "ibeam": pr.MouseCursor.MOUSE_CURSOR_IBEAM,
    "crosshair": pr.MouseCursor.MOUSE_CURSOR_CROSSHAIR,
    "pointing_hand": pr.MouseCursor.MOUSE_CURSOR_POINTING_HAND,
    "resize_ew": pr.MouseCursor.MOUSE_CURSOR_RESIZE_EW,
    "resize_ns": pr.MouseCursor.MOUSE_CURSOR_RESIZE_NS,
    "resize_nwse": pr.MouseCursor.MOUSE_CURSOR_RESIZE_NWSE,
    "resize_nesw": pr.MouseCursor.MOUSE_CURSOR_RESIZE_NESW,
    "resize_all": pr.MouseCursor.MOUSE_CURSOR_RESIZE_ALL,
    "not_allowed": pr.MouseCursor.MOUSE_CURSOR_NOT_ALLOWED,
}


class Mouse(ServiceUnit, IMouse):
    """Service for reading and controlling mouse input.

    Attributes:
        position: The last stored mouse position ``(x, y)``.
        movement: Mouse position delta since the last update
            ``(dx, dy)``.
        emit_to_bus: Whether mouse events are deferred to the EventBus.
        current_cursor: The current cursor constant value (integer).
    """

    def __init__(self, cursor: CURSOR_MOUSE_KEY = "arrow"):
        """Initialize a Mouse instance with the given initial cursor."""
        super().__init__("Mouse", tags={"service", "mouse"})
        self.position: tuple[float, float] = (0.0, 0.0)
        self.movement: tuple[float, float] = (0.0, 0.0)
        self.emit_to_bus: bool = True
        self._event_bus: EventBus | None = None

        self.current_cursor: int = 0
        self.set_cursor(cursor)

    def _defer_if_listened(self, bus: EventBus, event_name: str, **kwargs) -> None:
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

        Edge polling only runs on the first fixed step within the
        current wall-clock frame. Without an App (isolated unit
        tests), edges stay active.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        app = self.one_or_none("@App", scope="global")
        if app is None:
            return True
        return bool(app.is_first_fixed_step)

    def update(self, dt: float) -> None:
        """Update mouse position/delta and defer mouse.* events to the EventBus.

        Args:
            dt: Delta time of the current frame.
        """
        _ = dt
        mpos = pr.get_mouse_position()
        self.movement = (mpos.x - self.position[0], mpos.y - self.position[1])
        self.position = (mpos.x, mpos.y)

        if not self.emit_to_bus:
            return
        bus = self.one_or_none("@EventBus", scope="global")
        if bus is None:
            return

        pos = self.position
        for button in MAP_BUTTON_MOUSE:
            payload = {"action": button, "device": "mouse", "position": pos}
            if self.is_pressed(button):
                self._defer_if_listened(bus, f"mouse.{button}.pressed", **payload)
            if self.is_down(button):
                self._defer_if_listened(bus, f"mouse.{button}.down", **payload)
            if self.is_released(button):
                self._defer_if_listened(bus, f"mouse.{button}.released", **payload)

    @property
    def x(self) -> int:
        """int: The current mouse X position."""
        return pr.get_mouse_x()

    @property
    def y(self) -> int:
        """int: The current mouse Y position."""
        return pr.get_mouse_y()

    def get_wheel_move(self) -> float:
        """Get the scroll wheel delta since the last frame (Y axis).

        Returns:
            float: The vertical scroll wheel delta.
        """
        return pr.get_mouse_wheel_move()

    def move(self, x: int, y: int) -> None:
        """Move the mouse cursor to the given coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        pr.set_mouse_position(x, y)

    def hide(self) -> None:
        """Hide the mouse cursor."""
        pr.hide_cursor()

    def show(self) -> None:
        """Show the mouse cursor."""
        pr.show_cursor()

    def disable(self) -> None:
        """Disable the mouse cursor (lock to the application window)."""
        pr.disable_cursor()

    def is_down(
        self,
        button: Literal["left", "right", "middle", "side", "extra", "forward", "back"],
    ) -> bool:
        """Check whether the given mouse button is currently held down.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button is held, ``False`` if not
                or when the button is unrecognized.
        """
        if button not in MAP_BUTTON_MOUSE:
            warnings.warn(f"Invalid mouse button: {button}", stacklevel=2)
            return False

        return pr.is_mouse_button_down(MAP_BUTTON_MOUSE[button])

    def is_pressed(
        self,
        button: Literal["left", "right", "middle", "side", "extra", "forward", "back"],
    ) -> bool:
        """Check whether the given mouse button was just pressed.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button was just pressed, ``False``
                if not or when the button is unrecognized.
        """
        if button not in MAP_BUTTON_MOUSE:
            warnings.warn(f"Invalid mouse button: {button}", stacklevel=2)
            return False
        if not self._allow_edge():
            return False

        return pr.is_mouse_button_pressed(MAP_BUTTON_MOUSE[button])

    def is_released(
        self,
        button: Literal["left", "right", "middle", "side", "extra", "forward", "back"],
    ) -> bool:
        """Check whether the given mouse button was just released.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button was just released, ``False``
                if not or when the button is unrecognized.
        """
        if button not in MAP_BUTTON_MOUSE:
            warnings.warn(f"Invalid mouse button: {button}", stacklevel=2)
            return False
        if not self._allow_edge():
            return False

        return pr.is_mouse_button_released(MAP_BUTTON_MOUSE[button])

    def set_cursor(
        self,
        cursor: CURSOR_MOUSE_KEY,
    ) -> None:
        """Set the mouse cursor to the given kind.

        Args:
            cursor: Cursor kind name (mapped via
                ``MAP_CURSOR_MOUSE``).
        """
        if cursor not in MAP_CURSOR_MOUSE:
            warnings.warn(f"Invalid mouse cursor: {cursor}", stacklevel=2)
            return

        self.current_cursor = MAP_CURSOR_MOUSE[cursor]
        pr.set_mouse_cursor(self.current_cursor)

    def get_cursor(self) -> int:
        """Get the current mouse cursor kind.

        Returns:
            int: The current cursor kind constant value (e.g.:
                ``pr.MOUSE_CURSOR_POINTING_HAND``).
        """
        return self.current_cursor

    def get_cursor_name(self) -> CURSOR_MOUSE_KEY:
        """Get the name of the current mouse cursor kind.

        Returns:
            str: The current cursor kind name (e.g.:
                ``"pointing_hand"``), or ``"unknown"`` when not
                found.
        """
        for name, value in MAP_CURSOR_MOUSE.items():
            if value == self.current_cursor:
                return name
        return "unknown"

    def is_cursor(self, cursor: CURSOR_MOUSE_KEY) -> bool:
        """Check whether the current cursor kind equals the given one.

        Args:
            cursor: Cursor kind name to compare against (mapped
                via ``MAP_CURSOR_MOUSE``).

        Returns:
            bool: ``True`` if the current cursor kind matches,
                ``False`` if not or when the cursor is unrecognized.
        """
        if cursor not in MAP_CURSOR_MOUSE:
            warnings.warn(f"Invalid mouse cursor: {cursor}", stacklevel=2)
            return False

        return self.current_cursor == MAP_CURSOR_MOUSE[cursor]
