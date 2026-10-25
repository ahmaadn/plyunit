"""Engine input protocols and active-backend input implementations."""

from __future__ import annotations

from plyunit.backends.integrations import Gamepad, Input, Mouse, Touch
from plyunit.backends.interfaces.i_input import IGamepad, IInput, IMouse, ITouch

__all__ = [
    "Gamepad",
    "IGamepad",
    "IInput",
    "IMouse",
    "ITouch",
    "Input",
    "Mouse",
    "Touch",
]
