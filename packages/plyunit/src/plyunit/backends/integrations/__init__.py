"""Select backend implementations at the public composition boundary.

Domain code imports contracts from ``plyunit.backends.ports`` instead of this
module. Resolving a public name loads only the selected integration backend.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

from plyunit.backends._selector import integration_module

if TYPE_CHECKING:
    from .raylib import (
        Assets as Assets,
        Audio as Audio,
        Camera2D as Camera2D,
        Canvas2D as Canvas2D,
        Font as Font,
        Gamepad as Gamepad,
        Image as Image,
        ImageProcessor as ImageProcessor,
        Input as Input,
        Mouse as Mouse,
        RenderTexture as RenderTexture,
        Shader as Shader,
        Shaders as Shaders,
        StreamingTexture as StreamingTexture,
        Text as Text,
        Texture2D as Texture2D,
        Touch as Touch,
        UnifiedBufferBatch as UnifiedBufferBatch,
        Window as Window,
    )

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

_active_integration: ModuleType | None = None


def _get_active_integration() -> ModuleType:
    """Import and cache the selected integration module."""
    global _active_integration
    if _active_integration is None:
        _active_integration = import_module(integration_module())
    return _active_integration


def __getattr__(name: str):
    """Resolve a declared public name from the selected backend.

    Args:
        name: Exported implementation or resource-handle name.

    Returns:
        The selected backend's implementation.

    Raises:
        AttributeError: If the name is not an export.
    """
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_get_active_integration(), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return cached attributes and declared public exports."""
    return sorted(set(globals()) | set(__all__))
