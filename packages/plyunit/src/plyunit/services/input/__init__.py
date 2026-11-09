"""Backend-neutral input names and action-event data.

Backend input services live in ``plyunit.backends.integrations``. Importing
these data types never selects or loads a backend.
"""

from typing import TYPE_CHECKING

from ._types import CursorShape, GamepadAxis, GamepadButton, MouseButton
from .action_event import AxisBinding, InputEvents, MouseEvents

if TYPE_CHECKING:
    from plyunit.backends.integrations import Gamepad, Input, Mouse, Touch

__all__ = (
    "AxisBinding",
    "CursorShape",
    "Gamepad",
    "GamepadAxis",
    "GamepadButton",
    "Input",
    "InputEvents",
    "Mouse",
    "MouseButton",
    "MouseEvents",
    "Touch",
)


def __getattr__(name: str):
    if name not in {"Gamepad", "Input", "Mouse", "Touch"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends import integrations

    value = getattr(integrations, name)
    globals()[name] = value
    return value
