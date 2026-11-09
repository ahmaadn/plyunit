"""Raylib service adapters and their backend-owned resource handles."""

from .assets import Assets, ImageProcessor
from .audio import Audio
from .camera2d import Camera2D
from .handler import Font, Image, RenderTexture, Shader, StreamingTexture, Texture2D
from .input import Gamepad, Input, Mouse, Touch
from .renderer import Canvas2D, UnifiedBufferBatch
from .shader import Shaders
from .text import Text
from .window import Window

__all__ = (
    "Assets",
    "Audio",
    "Camera2D",
    "Canvas2D",
    "Font",
    "Gamepad",
    "Image",
    "ImageProcessor",
    "Input",
    "Mouse",
    "RenderTexture",
    "Shader",
    "Shaders",
    "StreamingTexture",
    "Text",
    "Texture2D",
    "Touch",
    "UnifiedBufferBatch",
    "Window",
)
