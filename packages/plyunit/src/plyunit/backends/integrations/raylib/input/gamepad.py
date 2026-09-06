"""raylib gamepad service unit and button/action mapping constants.

Defines the button (``BUTTONS``) and axis (``AXES``) mapping
constants, the default dead zone value, name conversion helpers, the
``apply_deadzone`` function, and the :class:`Gamepad` class for
polling a single gamepad by player index.
"""

from __future__ import annotations

import pyray as pr

from plyunit._constants import DEFAULT_DEADZONE
from plyunit.backends.interfaces.i_input import GAMEPAD_BUTTON_KEY, IGamepad
from plyunit.core.units.service_unit import ServiceUnit

__all__ = ["GAMEPAD_AXES", "GAMEPAD_BUTTONS", "Gamepad"]


# Mapping of gamepad button names (PlayStation & Xbox aliases) to
# ``pr.GAMEPAD_BUTTON_*`` constants. Each key is a user-facing name;
# each value is a raylib button constant. Mapping by category:
#   Face: a/cross, b/circle, x/square, y/triangle
#   Bumper/trigger: lb, rb, lt, rt
#   Stick click: ls, rs
#   D-pad: dpad_up, dpad_down, dpad_left, dpad_right
#   Middle: start, select, guide
GAMEPAD_BUTTONS: dict[GAMEPAD_BUTTON_KEY, int] = {
    "a": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_DOWN,
    "cross": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_DOWN,
    "b": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT,
    "circle": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT,
    "x": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_LEFT,
    "square": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_LEFT,
    "y": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_UP,
    "triangle": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_FACE_UP,
    "lb": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_TRIGGER_1,
    "rb": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_TRIGGER_1,
    "lt": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_TRIGGER_2,
    "rt": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_TRIGGER_2,
    "ls": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_THUMB,
    "rs": pr.GamepadButton.GAMEPAD_BUTTON_RIGHT_THUMB,
    "dpad_up": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_FACE_UP,
    "dpad_down": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_FACE_DOWN,
    "dpad_left": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_FACE_LEFT,
    "dpad_right": pr.GamepadButton.GAMEPAD_BUTTON_LEFT_FACE_RIGHT,
    "start": pr.GamepadButton.GAMEPAD_BUTTON_MIDDLE_RIGHT,
    "select": pr.GamepadButton.GAMEPAD_BUTTON_MIDDLE_LEFT,
    "guide": pr.GamepadButton.GAMEPAD_BUTTON_MIDDLE,
}

# Mapping of analog axis names to ``pr.GAMEPAD_AXIS_*`` constants.
# Each key is a user-facing axis name; each value is a raylib axis
# constant:
#   left_x / left_y: left stick (horizontal / vertical)
#   right_x / right_y: right stick (horizontal / vertical)
#   left_trigger / right_trigger: L2 / R2 triggers
GAMEPAD_AXES: dict[str, int] = {
    "left_x": pr.GamepadAxis.GAMEPAD_AXIS_LEFT_X,
    "left_y": pr.GamepadAxis.GAMEPAD_AXIS_LEFT_Y,
    "right_x": pr.GamepadAxis.GAMEPAD_AXIS_RIGHT_X,
    "right_y": pr.GamepadAxis.GAMEPAD_AXIS_RIGHT_Y,
    "left_trigger": pr.GamepadAxis.GAMEPAD_AXIS_LEFT_TRIGGER,
    "right_trigger": pr.GamepadAxis.GAMEPAD_AXIS_RIGHT_TRIGGER,
}

# Default dead zone for analog axes; values below this threshold are
# treated as zero to avoid stick drift.


def _button(name: str | int) -> int:
    """Convert a gamepad button name to a raylib integer constant.

    Args:
        name: Button name (string, mapped via ``BUTTONS``) or an
            already-valid integer constant.

    Returns:
        int: The raylib button constant.

    Raises:
        ValueError: If ``name`` is a string not recognized in
            ``BUTTONS``.
    """
    if isinstance(name, int):
        return name
    key = name.lower()
    if key not in GAMEPAD_BUTTONS:
        raise ValueError(f"Unknown gamepad button {name!r}")
    return GAMEPAD_BUTTONS[key]


def _axis(name: str | int) -> int:
    """Convert a gamepad axis name to a raylib integer constant.

    Args:
        name: Axis name (string, mapped via ``AXES``) or an
            already-valid integer constant.

    Returns:
        int: The raylib axis constant.

    Raises:
        ValueError: If ``name`` is a string not recognized in
            ``AXES``.
    """
    if isinstance(name, int):
        return name
    key = name.lower()
    if key not in GAMEPAD_AXES:
        raise ValueError(f"Unknown gamepad axis {name!r}")
    return GAMEPAD_AXES[key]


def apply_deadzone(value: float, deadzone: float = DEFAULT_DEADZONE) -> float:
    """Apply a dead zone to an analog axis value.

    If the absolute value is smaller than ``deadzone``, return
    ``0.0`` to avoid stick drift; otherwise return the original
    value.

    Args:
        value: Raw analog axis value (range ``-1.0`` to ``1.0``).
        deadzone: Dead zone threshold; absolute values below this
            are zeroed out.

    Returns:
        float: The value after the dead zone is applied.
    """
    return 0.0 if abs(value) < deadzone else value


class Gamepad(ServiceUnit, IGamepad):
    """Poll a single gamepad by player index (device service).

    Does not use an action map; polls the raylib bindings directly
    for one gamepad device.

    Args:
        player: Player index (starting from 0). Defaults to 0.
        deadzone: Dead zone threshold for analog axes. Defaults to
            :data:`DEFAULT_DEADZONE`.

    Attributes:
        player: The gamepad's player index.
        deadzone: The active analog axis dead zone threshold.
    """

    def __init__(self, player: int = 0, *, deadzone: float = DEFAULT_DEADZONE) -> None:
        """Initialize a Gamepad instance for the given player index."""
        name = "Gamepad" if player == 0 else f"Gamepad{player}"
        super().__init__(name, tags={"service", "input", "gamepad"})
        self.player = player
        self.deadzone = deadzone

    def _allow_edge(self) -> bool:
        """Check whether edge polling is allowed on this substep.

        Returns ``True`` when there is no App (e.g. isolated unit
        tests) or when this is the first fixed step within the
        current wall-clock frame.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        app = self.one_or_none("@App", scope="global")
        return True if app is None else bool(app.is_first_fixed_step)

    def is_available(self) -> bool:
        """Check whether a gamepad is available at this player index.

        Returns:
            bool: ``True`` if a gamepad is connected and available.
        """
        return pr.is_gamepad_available(self.player)

    @property
    def name_on_device(self) -> str:
        """str: The gamepad device name (empty when unavailable)."""
        if not self.is_available():
            return ""
        return pr.get_gamepad_name(self.player) or ""

    def is_pressed(self, button: str | int) -> bool:
        """Check whether a gamepad button was just pressed (edge).

        Args:
            button: Button name (string) or a raylib integer
                constant.

        Returns:
            bool: ``True`` if the button was pressed this frame.
        """
        if not self._allow_edge() or not self.is_available():
            return False
        return pr.is_gamepad_button_pressed(self.player, _button(button))

    def is_down(self, button: str | int) -> bool:
        """Check whether a gamepad button is currently held down.

        Args:
            button: Button name (string) or a raylib integer
                constant.

        Returns:
            bool: ``True`` if the button is currently held.
        """
        if not self.is_available():
            return False
        return pr.is_gamepad_button_down(self.player, _button(button))

    def is_released(self, button: str | int) -> bool:
        """Check whether a gamepad button was just released (edge).

        Args:
            button: Button name (string) or a raylib integer
                constant.

        Returns:
            bool: ``True`` if the button was released this frame.
        """
        if not self._allow_edge() or not self.is_available():
            return False
        return pr.is_gamepad_button_released(self.player, _button(button))

    def is_up(self, button: str | int) -> bool:
        """Check whether a gamepad button is currently not pressed.

        Args:
            button: Button name (string) or a raylib integer
                constant.

        Returns:
            bool: ``True`` if the button is released / inactive.
        """
        if not self.is_available():
            return True
        return pr.is_gamepad_button_up(self.player, _button(button))

    def get_axis(self, axis: str | int, *, deadzone: float | None = None) -> float:
        """Get an analog axis value after applying the dead zone.

        Args:
            axis: Axis name (string) or a raylib integer constant.
            deadzone: Dead zone override; ``None`` means use
                ``self.deadzone``.

        Returns:
            float: The axis value after the dead zone is applied
                (``0.0`` when the gamepad is unavailable).
        """
        if not self.is_available():
            return 0.0
        raw = pr.get_gamepad_axis_movement(self.player, _axis(axis))
        return apply_deadzone(raw, self.deadzone if deadzone is None else deadzone)

    def get_vector(
        self,
        axis_x: str | int = "left_x",
        axis_y: str | int = "left_y",
        *,
        deadzone: float | None = None,
    ) -> tuple[float, float]:
        """Get an X and Y axis pair as a 2D vector.

        Args:
            axis_x: Horizontal axis name/constant. Defaults to
                ``"left_x"``.
            axis_y: Vertical axis name/constant. Defaults to
                ``"left_y"``.
            deadzone: Dead zone override; ``None`` means use
                ``self.deadzone``.

        Returns:
            tuple[float, float]: The ``(x, y)`` pair after the dead
                zone is applied.
        """
        return (
            self.get_axis(axis_x, deadzone=deadzone),
            self.get_axis(axis_y, deadzone=deadzone),
        )

    def set_vibration(
        self,
        left_motor: float = 0.0,
        right_motor: float = 0.0,
        *,
        duration: float = 0.25,
    ) -> None:
        """Set gamepad vibration for both motors.

        Args:
            left_motor: Left motor strength (``0.0`` - ``1.0``).
            right_motor: Right motor strength (``0.0`` - ``1.0``).
            duration: Vibration duration in seconds.

        Note:
            Does nothing when the gamepad is unavailable.
        """
        if self.is_available():
            pr.set_gamepad_vibration(self.player, left_motor, right_motor, duration)
