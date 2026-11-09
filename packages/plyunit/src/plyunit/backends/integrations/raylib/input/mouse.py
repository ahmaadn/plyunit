"""raylib mouse service unit and button/cursor mapping constants.

Defines the button mapping constants (``MAP_BUTTON_MOUSE``) and
cursor mapping constants (``MAP_CURSOR_MOUSE``), and the
:class:`Mouse` class for reading and controlling mouse input.
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Literal

import pyray as pr

from plyunit.backends.ports.input import IMouse
from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from plyunit.events.event_bus import EventBus
    from plyunit.services.input._types import CursorShape, MouseButton
    from plyunit.services.input.action_event import MouseEvents


__all__ = ("Mouse",)


logger = logging.getLogger(__name__)


UNKNOWN_CURSOR: Literal["unknown"] = "unknown"

# Mapping of mouse button names to ``pr.MouseButton`` constants. Each
# key is a user-facing name string; each value is a raylib constant.
# Mapping by category:
#   left / right / middle: standard primary buttons
#   side / extra: side buttons
#   forward / back: browser navigation buttons
MAP_BUTTON_MOUSE: dict[MouseButton, int] = {
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
MAP_CURSOR_MOUSE: dict[CursorShape, int] = {
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


# Built once on first use (a snapshot of ``MAP_BUTTON_MOUSE``) so that
# ``update`` never formats event-name strings per frame.
_BUTTON_EVENTS: tuple[MouseEvents, ...] | None = None


def _button_events() -> tuple[MouseEvents, ...]:
    """Return the per-button event snapshot, building it on first call.

    The import is deferred to first call (not import time) so importing
    this module never imports ``plyunit.services.input`` while the
    integration package is still loading.

    Returns:
        tuple[MouseEvents, ...]: One entry per mapped mouse button.
    """
    global _BUTTON_EVENTS
    if _BUTTON_EVENTS is None:
        from plyunit.services.input.action_event import MouseEvents

        _BUTTON_EVENTS = tuple(
            MouseEvents.for_action(action=action, code=code)
            for action, code in MAP_BUTTON_MOUSE.items()
        )
    return _BUTTON_EVENTS


class Mouse(ServiceUnit, IMouse):
    """Service for reading and controlling mouse input.

    Attributes:
        position: The last stored mouse position ``(x, y)``.
        movement: Mouse position delta since the last update
            ``(dx, dy)``.
        emit_to_bus: Whether mouse events are deferred to the EventBus.
        current_cursor: The current cursor constant value (integer).
    """

    def __init__(self, cursor: CursorShape = "arrow") -> None:
        """Initialize a Mouse instance with the given initial cursor."""
        super().__init__("Mouse", tags={"service", "mouse"})
        self.emit_to_bus: bool = True
        self.current_cursor: int = 0
        self.set_cursor(cursor)
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

        Edge polling only runs on the first fixed step within the
        current wall-clock frame. Without an App (isolated unit
        tests), edges stay active.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        return self._app is None or bool(self._app.is_first_fixed_step)

    def update(self, dt: float) -> None:
        """Update mouse position/delta and defer mouse.* events to the EventBus.

        Args:
            dt: Delta time of the current frame. Not used directly;
                raylib polling is frame-based.
        """
        if not self.emit_to_bus:
            return

        if self._bus is None:
            return

        edge = self._allow_edge()  # once per frame, not once per button
        for button in _button_events():
            self._emit_button(self._bus, button, edge)

    def _emit_button(self, bus: EventBus, button: MouseEvents, edge: bool) -> None:
        """Defer the ``mouse.<button>.*`` events that fired this frame.

        An event is only polled when something is listening to it.

        Args:
            bus: Target EventBus instance.
            button: Button to poll, with its event names.
            edge: Whether edge events (pressed/released) may fire.
        """
        code = button.code
        if edge and bus.has_listeners(button.pressed):  # noqa: SIM102
            if pr.is_mouse_button_pressed(code):
                self._defer(bus, button.pressed, button)
        if bus.has_listeners(button.down) and pr.is_mouse_button_down(code):
            self._defer(bus, button.down, button)
        if edge and bus.has_listeners(button.released):  # noqa: SIM102
            if pr.is_mouse_button_released(code):
                self._defer(bus, button.released, button)

    def _defer(self, bus: EventBus, event_name: str, button: MouseEvents) -> None:
        """Defer one mouse event with the standard payload.

        Args:
            bus: Target EventBus instance.
            event_name: Name of the event to defer.
            button: The button that triggered the event.
        """
        bus.defer(
            event_name,
            action=button.action,
            device="mouse",
            position=self.position,
        )

    @property
    def position(self) -> tuple[float, float]:
        """Current mouse cursor position in screen coordinates.

        Returns:
            A tuple of ``(x, y)`` pixel coordinates.
        """
        pos = pr.get_mouse_position()
        return pos.x, pos.y

    @property
    def movement(self) -> tuple[float, float]:
        """Mouse movement delta since the previous frame.

        Returns:
            A tuple of ``(dx, dy)`` displacement values in pixels.
        """
        delta = pr.get_mouse_delta()
        return delta.x, delta.y

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

    @staticmethod
    def _button_code(button: MouseButton) -> int | None:
        """Resolve a button name, warning when it is unrecognized.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            int | None: The raylib constant, or ``None`` if unknown.
                Note ``0`` (left button) is a valid code, so compare
                against ``None`` explicitly.
        """
        code = MAP_BUTTON_MOUSE.get(button)
        if code is None:
            # stacklevel=3: skip this helper and the public method.
            warnings.warn(f"Invalid mouse button: {button}", stacklevel=3)
        return code

    def is_down(self, button: MouseButton) -> bool:
        """Check whether the given mouse button is currently held down.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button is held, ``False`` if not
                or when the button is unrecognized.
        """
        code = self._button_code(button)
        return code is not None and pr.is_mouse_button_down(code)

    def is_pressed(self, button: MouseButton) -> bool:
        """Check whether the given mouse button was just pressed.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button was just pressed, ``False``
                if not or when the button is unrecognized.
        """
        code = self._button_code(button)
        if code is None or not self._allow_edge():
            return False
        return pr.is_mouse_button_pressed(code)

    def is_released(self, button: MouseButton) -> bool:
        """Check whether the given mouse button was just released.

        Args:
            button: Mouse button name (mapped via
                ``MAP_BUTTON_MOUSE``).

        Returns:
            bool: ``True`` if the button was just released, ``False``
                if not or when the button is unrecognized.
        """
        code = self._button_code(button)
        if code is None or not self._allow_edge():
            return False
        return pr.is_mouse_button_released(code)

    @staticmethod
    def _cursor_code(cursor: CursorShape) -> int | None:
        """Resolve a cursor name, warning when it is unrecognized.

        Args:
            cursor: Cursor kind name (mapped via
                ``MAP_CURSOR_MOUSE``).

        Returns:
            int | None: The raylib constant, or ``None`` if unknown.
                Note ``0`` is a valid code, so compare against
                ``None`` explicitly.
        """
        code = MAP_CURSOR_MOUSE.get(cursor)
        if code is None:
            warnings.warn(f"Invalid mouse cursor: {cursor}", stacklevel=3)
        return code

    def set_cursor(self, cursor: CursorShape) -> None:
        """Set the mouse cursor to the given kind.

        Args:
            cursor: Cursor kind name (mapped via
                ``MAP_CURSOR_MOUSE``).
        """
        code = self._cursor_code(cursor)
        if code is None:
            return
        self.current_cursor = code
        pr.set_mouse_cursor(code)

    def get_cursor(self) -> int:
        """Get the current mouse cursor kind.

        Returns:
            int: The current cursor kind constant value (e.g.:
                ``pr.MOUSE_CURSOR_POINTING_HAND``).
        """
        return self.current_cursor

    def get_cursor_name(self) -> CursorShape | Literal["unknown"]:
        """Get the name of the current mouse cursor kind.

        Returns:
            str: The current cursor kind name (e.g.:
                ``"pointing_hand"``), or ``"unknown"`` when not
                found.
        """
        return next(
            (
                name
                for name, value in MAP_CURSOR_MOUSE.items()
                if value == self.current_cursor
            ),
            UNKNOWN_CURSOR,
        )

    def is_cursor(self, cursor: CursorShape) -> bool:
        """Check whether the current cursor kind equals the given one.

        Args:
            cursor: Cursor kind name to compare against (mapped
                via ``MAP_CURSOR_MOUSE``).

        Returns:
            bool: ``True`` if the current cursor kind matches,
                ``False`` if not or when the cursor is unrecognized.
        """
        code = self._cursor_code(cursor)
        return code is not None and self.current_cursor == code
