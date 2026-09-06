"""Protocol contracts every backend implementation must satisfy.

This module exports all interfaces (Protocol/ABC) used by domain code to
type-annotate against the stable backend surface, without being tied to a
specific active backend (e.g. raylib, pymunk).
"""

from .i_assets_loader import IAssetsLoader
from .i_audio import IAudioBackend
from .i_camera2d import ICamera2D
from .i_input import IGamepad, IInput, IMouse, ITouch
from .i_renderer import (
    IBatchingBackend,
    ICanvas2D,
    IRenderPass,
    IUnifiedBufferBatch,
    IWindow,
)
from .i_shader import IShaderLoader
from .i_text import IFont

__all__ = [
    "IAssetsLoader",
    "IAudioBackend",
    "IBatchingBackend",
    "ICamera2D",
    "ICanvas2D",
    "IFont",
    "IGamepad",
    "IInput",
    "IMouse",
    "IRenderPass",
    "IShaderLoader",
    "ITouch",
    "IUnifiedBufferBatch",
    "IWindow",
]
