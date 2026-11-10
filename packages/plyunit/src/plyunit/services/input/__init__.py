"""Backend-neutral input names and action-event data.

Backend input services live in ``plyunit.backends.integrations``. Importing
these data types never selects or loads a backend.
"""

from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

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


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Gamepad": "plyunit.backends.integrations",
        "Input": "plyunit.backends.integrations",
        "Mouse": "plyunit.backends.integrations",
        "Touch": "plyunit.backends.integrations",
    },
    global_dict=globals(),
    all_exports=__all__,
)
