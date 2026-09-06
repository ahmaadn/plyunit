"""Engine input protocols and active-backend input implementations."""

from __future__ import annotations

from plyunit.backends.integrations import (
    GAMEPAD_AXES,
    GAMEPAD_BUTTONS,
    MAP_BUTTON_MOUSE,
    MAP_CURSOR_MOUSE,
    Gamepad,
    Input,
    Mouse,
    Touch,
)
from plyunit.backends.interfaces.i_input import (
    BUTTON_MOUSE_KEY,
    CURSOR_MOUSE_KEY,
    GAMEPAD_AXIS_KEY,
    GAMEPAD_BUTTON_KEY,
    IGamepad,
    IInput,
    IMouse,
    ITouch,
)

from .._constants import DEFAULT_DEADZONE

__all__ = [
    "BUTTON_MOUSE_KEY",
    "CURSOR_MOUSE_KEY",
    "DEFAULT_DEADZONE",
    "GAMEPAD_AXES",
    "GAMEPAD_AXIS_KEY",
    "GAMEPAD_BUTTONS",
    "GAMEPAD_BUTTON_KEY",
    "MAP_BUTTON_MOUSE",
    "MAP_CURSOR_MOUSE",
    "Gamepad",
    "IGamepad",
    "IInput",
    "IMouse",
    "ITouch",
    "Input",
    "Mouse",
    "Touch",
]
