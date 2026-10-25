from typing import Literal

MouseButton = Literal[
    "left",
    "right",
    "middle",
    "side",
    "extra",
    "forward",
    "back",
]

CursorShape = Literal[
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


GamepadButton = Literal[
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

GamepadAxis = Literal[
    "left_x",
    "left_y",
    "right_x",
    "right_y",
    "left_trigger",
    "right_trigger",
]
