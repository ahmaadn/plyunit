"""Backend-neutral ports; importing this package never loads a backend."""

from .assets import IAssets, IImageProcessor
from .audio import IAudio
from .camera2d import ICamera2D
from .handler import (
    FontHandle,
    ImageHandle,
    PixelBuffer,
    RenderTextureHandle,
    ShaderHandle,
    StreamingTextureHandle,
    Texture2DHandle,
    TextureTarget,
)
from .imgui import DrawCallback, ImGuiPort
from .input import IGamepad, IInput, IMouse, ITouch
from .physics import AreaStateView, BodyStateView, IPhysics
from .renderer import ICanvas2D, IRenderPass, IUnifiedBufferBatch, IWindow
from .shaders import IShaders
from .text import IText, ITextRenderer, ShapedText, TemplateText

__all__ = (
    "AreaStateView",
    "BodyStateView",
    "DrawCallback",
    "FontHandle",
    "IAssets",
    "IAudio",
    "ICamera2D",
    "ICanvas2D",
    "IGamepad",
    "IImageProcessor",
    "IInput",
    "IMouse",
    "IPhysics",
    "IRenderPass",
    "IShaders",
    "IText",
    "ITextRenderer",
    "ITouch",
    "IUnifiedBufferBatch",
    "IWindow",
    "ImGuiPort",
    "ImageHandle",
    "PixelBuffer",
    "RenderTextureHandle",
    "ShaderHandle",
    "ShapedText",
    "StreamingTextureHandle",
    "TemplateText",
    "Texture2DHandle",
    "TextureTarget",
)
