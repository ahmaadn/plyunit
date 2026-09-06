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

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from plyunit._constants import DEFAULT_DEADZONE

__all__ = (
    "BUTTON_MOUSE_KEY",
    "CURSOR_MOUSE_KEY",
    "GAMEPAD_AXIS_KEY",
    "GAMEPAD_BUTTON_KEY",
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

    Backends implement this and expose it as ``Input``. Domain code treats
    it as a ``ServiceUnit`` (``plyunit.services.input.Input`` is the type alias that
    resolves to the active backend's class).
    """

    actions: dict[str, set[int]]
    deadzone: float
    emit_to_bus: bool
    gamepad: IGamepad | None

    def __init__(
        self,
        *,
        gamepad: bool | IGamepad | None = None,
        deadzone: float = DEFAULT_DEADZONE,
    ) -> None:
        """Initialize the input service.

        Args:
            gamepad: ``True`` to create a default gamepad, an existing
                :class:`IGamepad` instance to attach, or ``None`` for no
                gamepad.
            deadzone: Default analog stick deadzone (0.0..1.0).
        """
        ...

    def map(self, action: str, *key: int, buttons: list[str] | None = None) -> None:
        """Bind keys and mouse buttons to an action.

        Args:
            action: Action name.
            *key: Key codes to bind.
            buttons: Optional mouse button names to bind.
        """
        ...

    def unmap(self, action: str, *keys: int) -> None:
        """Unbind keys from an action.

        Args:
            action: Action name.
            *keys: Key codes to unbind; none removes all bindings.
        """
        ...

    def map_axis(
        self,
        name: str,
        *,
        key_neg: list[int] | None = None,
        key_pos: list[int] | None = None,
        pad_axis: str | None = None,
        pad_buttons_neg: list[str] | None = None,
        pad_buttons_pos: list[str] | None = None,
        deadzone: float | None = None,
    ) -> None:
        """Define a named axis from keyboard keys and/or gamepad inputs.

        Args:
            name: Axis name.
            key_neg: Key codes contributing -1.0.
            key_pos: Key codes contributing +1.0.
            pad_axis: Gamepad axis name driving the axis.
            pad_buttons_neg: Gamepad buttons contributing -1.0.
            pad_buttons_pos: Gamepad buttons contributing +1.0.
            deadzone: Per-axis deadzone; ``None`` uses the service default.
        """
        ...

    def is_pressed(self, action: str) -> bool:
        """Check whether the action was pressed this frame (edge).

        Args:
            action: Action name.

        Returns:
            True on the frame the action becomes active.
        """
        ...

    def is_pressed_repeat(self, action: str) -> bool:
        """Check whether the action is pressed with key-repeat semantics.

        Args:
            action: Action name.

        Returns:
            True while held, re-firing at the OS repeat rate.
        """
        ...

    def is_down(self, action: str) -> bool:
        """Check whether the action is currently held down.

        Args:
            action: Action name.

        Returns:
            True while any bound input is down.
        """
        ...

    def is_released(self, action: str) -> bool:
        """Check whether the action was released this frame (edge).

        Args:
            action: Action name.

        Returns:
            True on the frame the action stops being active.
        """
        ...

    def is_up(self, action: str) -> bool:
        """Check whether the action is currently not held down.

        Args:
            action: Action name.

        Returns:
            True while no bound input is down.
        """
        ...

    def get_axis(self, left: str, right: str | None = None) -> float:
        """Compute a 1D axis value from two actions or a mapped axis.

        Args:
            left: Action contributing -1.0, or a mapped axis name.
            right: Optional action contributing +1.0.

        Returns:
            The axis value in -1.0..1.0.
        """
        ...

    def load(self, path: str | Path) -> None:
        """Load the keymap (action bindings) from a file.

        Args:
            path: Keymap file path.
        """
        ...

    def save(self, path: str | Path) -> None:
        """Save the current keymap (action bindings) to a file.

        Args:
            path: Keymap file path.
        """
        ...


# ---
# MOUSE
# ---

BUTTON_MOUSE_KEY = Literal[
    "left",
    "right",
    "middle",
    "side",
    "extra",
    "forward",
    "back",
]

CURSOR_MOUSE_KEY = Literal[
    "arrow",
    "ibeam",
    "crosshair",
    "pointing_hand",
    "resize_ew",
    "resize_ns",
    "resize_nwse",
    "resize_nesw",
    "resize_all",
    "not_allowed",
    "unknown",
]


@runtime_checkable
class IMouse(Protocol):
    """Mouse state service (position, movement, cursor, button edges).

    Attributes:
        position: Current cursor position ``(x, y)`` in window pixels.
        movement: Per-frame cursor delta ``(dx, dy)``.
        emit_to_bus: Whether mouse events are emitted to the event bus.
        current_cursor: Backend cursor shape enum value.
    """

    position: tuple[float, float]
    movement: tuple[float, float]
    emit_to_bus: bool
    current_cursor: int

    def __init__(self, cursor: CURSOR_MOUSE_KEY = "arrow"):
        """Initialize the mouse service.

        Args:
            cursor: Initial cursor shape name.
        """
        ...

    def update(self, dt: float) -> None:
        """Refresh mouse state for the current frame.

        Args:
            dt: Frame delta time in seconds.
        """
        ...

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

    def is_down(self, button: BUTTON_MOUSE_KEY) -> bool:
        """Check whether a mouse button is currently held down.

        Args:
            button: Mouse button name.

        Returns:
            True while the button is down.
        """
        ...

    def is_pressed(self, button: BUTTON_MOUSE_KEY) -> bool:
        """Check whether a mouse button was pressed this frame (edge).

        Args:
            button: Mouse button name.

        Returns:
            True on the frame the button goes down.
        """
        ...

    def is_released(self, button: BUTTON_MOUSE_KEY) -> bool:
        """Check whether a mouse button was released this frame (edge).

        Args:
            button: Mouse button name.

        Returns:
            True on the frame the button goes up.
        """
        ...

    def set_cursor(self, cursor: CURSOR_MOUSE_KEY) -> None:
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

    def get_cursor_name(self) -> CURSOR_MOUSE_KEY:
        """Get the current cursor shape name.

        Returns:
            The cursor shape name.
        """
        ...

    def is_cursor(self, cursor: CURSOR_MOUSE_KEY) -> bool:
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

    def is_pressed(self, button: str | int) -> bool:
        """Check whether a button was pressed this frame (edge).

        Args:
            button: Button name or index.

        Returns:
            True on the frame the button goes down.
        """
        ...

    def is_down(self, button: str | int) -> bool:
        """Check whether a button is currently held down.

        Args:
            button: Button name or index.

        Returns:
            True while the button is down.
        """
        ...

    def is_released(self, button: str | int) -> bool:
        """Check whether a button was released this frame (edge).

        Args:
            button: Button name or index.

        Returns:
            True on the frame the button goes up.
        """
        ...

    def is_up(self, button: str | int) -> bool:
        """Check whether a button is currently not held down.

        Args:
            button: Button name or index.

        Returns:
            True while the button is up.
        """
        ...

    def get_axis(self, axis: str) -> float:
        """Read an analog axis.

        Args:
            axis: Axis name.

        Returns:
            The axis value in -1.0..1.0 (deadzone applied).
        """
        ...

    def get_vector(
        self,
        axis_x: str | int = "left_x",
        axis_y: str | int = "left_y",
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


GAMEPAD_BUTTON_KEY = Literal[
    "a",
    "cross",
    "b",
    "circle",
    "x",
    "square",
    "y",
    "triangle",
    "lb",
    "rb",
    "lt",
    "rt",
    "ls",
    "rs",
    "dpad_up",
    "dpad_down",
    "dpad_left",
    "dpad_right",
    "start",
    "select",
    "guide",
]

GAMEPAD_AXIS_KEY = Literal[
    "left_x",
    "left_y",
    "right_x",
    "right_y",
    "left_trigger",
    "right_trigger",
]

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

    def update(self, dt: float):
        """Refresh touch state for the current frame.

        Args:
            dt: Frame delta time in seconds.
        """
        ...

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
