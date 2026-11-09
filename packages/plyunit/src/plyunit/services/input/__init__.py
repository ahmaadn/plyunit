"""Backend-neutral input names and action-event data.

Backend input services live in ``plyunit.backends.integrations``. Importing
these data types never selects or loads a backend.
"""

from ._types import CursorShape, GamepadAxis, GamepadButton, MouseButton
from .action_event import AxisBinding, InputEvents, MouseEvents

__all__ = (
    "AxisBinding",
    "CursorShape",
    "GamepadAxis",
    "GamepadButton",
    "InputEvents",
    "MouseButton",
    "MouseEvents",
)
