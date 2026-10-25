"""Engine contract for the backend ``Input`` service.

The actual :class:`Input` is provided by the active backend — there is no
wrapper. Each backend has its own ``Input`` implementation and exposes it
under the same name. This protocol documents what every backend *must*
provide so domain code can type-annotate against the stable surface.

Exposed protocols:
- :class:`IInput` — action map + edge-state for keyboard/mouse/gamepad/
  touch.
- :class:`IMouse` — mouse state (position, count, cursor, edge).
- :class:`IGamepad` — gamepad availability and button/axis edge-state.
- :class:`ITouch` — touch state (count, position).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from plyunit._constants import DEFAULT_DEADZONE

if TYPE_CHECKING:
    from plyunit.services.input._types import (
        CursorShape,
        GamepadAxis,
        GamepadButton,
        MouseButton,
    )


__all__ = (
    "IGamepad",
    "IInput",
    "IMouse",
    "ITouch",
)


# ---
# MOUSE
# ---


@runtime_checkable
class IInput(Protocol):
    """Action map + edge-state service for keyboard / mouse / gamepad / touch.

    Backends implement this and expose it as ``Input``.
    """

    actions: dict[str, set[int]]
    emit_to_bus: bool

    def __init__(self, *, emit_to_bus: bool = False) -> None:
        """Initialize an Input instance with an empty action map.

        Args:
            emit_to_bus: Whether events are deferred to the EventBus.
        """
        ...

    def map(self, action: str, *keys: int) -> None:
        """Bind an action to keyboard keys.

        Args:
            action: Name of the action to map.
            *keys: One or more keyboard key codes.
        """
        ...

    def unmap(self, action: str, *keys: int) -> None:
        """Unbind an action or specific keyboard keys from an action.

        Args:
            action: Name of the action to unbind.
            *keys: Specific keyboard keys to unbind (optional).
        """
        ...

    def map_axis(
        self,
        name: str,
        *,
        key_neg: Sequence[int] | None = None,
        key_pos: Sequence[int] | None = None,
    ) -> None:
        """Define a 1D virtual axis from keyboard keys.

        Args:
            name: Name of the virtual axis.
            key_neg: Keyboard keys for the negative direction.
            key_pos: Keyboard keys for the positive direction.
        """
        ...

    def is_pressed(self, action: str) -> bool:
        """Check whether an action was just pressed (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: True if the action was pressed this frame.
        """
        ...

    def is_pressed_repeat(self, action: str) -> bool:
        """Check whether an action is pressed with auto-repeat (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: True if the action repeated this frame.
        """
        ...

    def is_down(self, action: str) -> bool:
        """Check whether an action is currently held down.

        Args:
            action: Name of the action to check.

        Returns:
            bool: True if the action is currently held.
        """
        ...

    def is_released(self, action: str) -> bool:
        """Check whether an action was just released (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: True if the action was released this frame.
        """
        ...

    def is_up(self, action: str) -> bool:
        """Check whether none of an action's keys are pressed.

        Args:
            action: Name of the action to check.

        Returns:
            bool: True if every key of the action is up.
        """
        ...

    def get_axis(self, left: str, right: str | None = None) -> float:
        """Get an axis value from two action names or one named axis.

        Args:
            left: Negative action name (or axis name if right is None).
            right: Positive action name (optional).

        Returns:
            float: Axis value between -1.0 and 1.0.
        """
        ...

    def get_vector(self, axis_x: str, axis_y: str) -> tuple[float, float]:
        """Get an X and Y axis pair as a 2D vector.

        Args:
            axis_x: Action/axis name for the horizontal component.
            axis_y: Action/axis name for the vertical component.

        Returns:
            tuple[float, float]: The (x, y) pair.
        """
        ...


# ---
# MOUSE
# ---


@runtime_checkable
class IMouse(Protocol):
    """Mouse state service (position, movement, cursor, button edges).

    Attributes:
        position: Current cursor position ``(x, y)`` in window pixels.
        movement: Per-frame cursor delta ``(dx, dy)``.
        emit_to_bus: Whether mouse events are emitted to the event bus.
        current_cursor: Backend cursor shape enum value.
    """

    emit_to_bus: bool
    current_cursor: int

    def __init__(self, cursor: CursorShape = "arrow"):
        """Initialize the mouse service.

        Args:
            cursor: Initial cursor shape name.
        """
        ...

    @property
    def position(self) -> tuple[float, float]: ...
    @property
    def movement(self) -> tuple[float, float]: ...

    @property
    def x(self) -> int:
        """Current cursor x position in window pixels."""
        ...

    @property
    def y(self) -> int:
        """Current cursor y position in window pixels."""
        ...

    def get_wheel_move(self) -> float:
        """Get the mouse wheel movement since the last frame.

        Returns:
            Wheel delta (positive = scrolling up).
        """
        ...

    def move(self, x: int, y: int) -> None:
        """Move the cursor to a window position.

        Args:
            x: Target x position in pixels.
            y: Target y position in pixels.
        """
        ...

    def hide(self) -> None:
        """Hide the cursor."""
        ...

    def show(self) -> None:
        """Show the cursor."""
        ...

    def disable(self) -> None:
        """Disable the cursor (hide and lock it from moving)."""
        ...

    def is_down(self, button: MouseButton) -> bool:
        """Check whether a mouse button is currently held down.

        Args:
            button: Mouse button name.

        Returns:
            True while the button is down.
        """
        ...

    def is_pressed(self, button: MouseButton) -> bool:
        """Check whether a mouse button was pressed this frame (edge).

        Args:
            button: Mouse button name.

        Returns:
            True on the frame the button goes down.
        """
        ...

    def is_released(self, button: MouseButton) -> bool:
        """Check whether a mouse button was released this frame (edge).

        Args:
            button: Mouse button name.

        Returns:
            True on the frame the button goes up.
        """
        ...

    def set_cursor(self, cursor: CursorShape) -> None:
        """Set the cursor shape.

        Args:
            cursor: Cursor shape name.
        """
        ...

    def get_cursor(self) -> int:
        """Get the current cursor shape as the backend enum value.

        Returns:
            The backend cursor enum value.
        """
        ...

    def get_cursor_name(self) -> CursorShape | Literal["unknown"]:
        """Get the current cursor shape name.

        Returns:
            The cursor shape name.
        """
        ...

    def is_cursor(self, cursor: CursorShape) -> bool:
        """Check whether the current cursor matches a shape name.

        Args:
            cursor: Cursor shape name to compare.

        Returns:
            True if the current cursor matches.
        """
        ...


# ---
# GAMEPAD
# ---


@runtime_checkable
class IGamepad(Protocol):
    """Gamepad state service (availability and button/axis edge-state).

    Attributes:
        player: Gamepad player index.
        deadzone: Analog stick deadzone (0.0..1.0).
    """

    player: int
    deadzone: float

    def __init__(
        self,
        player: int = 0,
        *,
        deadzone: float = DEFAULT_DEADZONE,
    ) -> None:
        """Initialize the gamepad service.

        Args:
            player: Gamepad player index.
            deadzone: Analog stick deadzone (0.0..1.0).
        """
        ...

    def is_available(self) -> bool:
        """Check whether the gamepad is connected.

        Returns:
            True if the gamepad is available.
        """
        ...

    @property
    def name_on_device(self) -> str:
        """Human-readable name reported by the device."""
        ...

    def is_pressed(self, button: GamepadButton) -> bool:
        """Check whether a button was pressed this frame (edge).

        Args:
            button: Button name or index.

        Returns:
            True on the frame the button goes down.
        """
        ...

    def is_down(self, button: GamepadButton) -> bool:
        """Check whether a button is currently held down.

        Args:
            button: Button name or index.

        Returns:
            True while the button is down.
        """
        ...

    def is_released(self, button: GamepadButton) -> bool:
        """Check whether a button was released this frame (edge).

        Args:
            button: Button name or index.

        Returns:
            True on the frame the button goes up.
        """
        ...

    def is_up(self, button: GamepadButton) -> bool:
        """Check whether a button is currently not held down.

        Args:
            button: Button name or index.

        Returns:
            True while the button is up.
        """
        ...

    def get_axis(self, axis: GamepadAxis, *, deadzone: float | None = None) -> float:
        """Read an analog axis.

        Args:
            axis: Axis name.

        Returns:
            The axis value in -1.0..1.0 (deadzone applied).
        """
        ...

    def get_vector(
        self,
        axis_x: GamepadAxis = "left_x",
        axis_y: GamepadAxis = "left_y",
        *,
        deadzone: float | None = None,
    ) -> tuple[float, float]:
        """Read a stick as a 2D vector.

        Args:
            axis_x: Horizontal axis name or index.
            axis_y: Vertical axis name or index.
            deadzone: Per-call deadzone; ``None`` uses the service default.

        Returns:
            The ``(x, y)`` vector, each component in -1.0..1.0.
        """
        ...

    def set_vibration(
        self,
        left_motor: float = 0.0,
        right_motor: float = 0.0,
        *,
        duration: float = 0.25,
    ) -> None:
        """Set controller vibration.

        Args:
            left_motor: Left (low-frequency) motor intensity (0.0..1.0).
            right_motor: Right (high-frequency) motor intensity (0.0..1.0).
            duration: Vibration duration in seconds.
        """
        ...


# ---
# Touch
# ---


@runtime_checkable
class ITouch(Protocol):
    """Touch state service (count, position, edges).

    Attributes:
        count: Number of active touch points.
        position: First touch point position ``(x, y)`` in window pixels.
        emit_to_bus: Whether touch events are emitted to the event bus.
    """

    count: int
    position: tuple[float, float]
    emit_to_bus: bool

    def is_down(self) -> bool:
        """Check whether a touch is currently held down.

        Returns:
            True while at least one touch point is active.
        """
        ...

    def is_pressed(self) -> bool:
        """Check whether a touch started this frame (edge).

        Returns:
            True on the frame a touch begins.
        """
        ...

    def is_released(self) -> bool:
        """Check whether a touch ended this frame (edge).

        Returns:
            True on the frame a touch ends.
        """
        ...


__all__ = ["IGamepad", "IInput", "IMouse", "ITouch"]
