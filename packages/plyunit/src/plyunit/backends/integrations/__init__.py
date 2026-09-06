"""Platform bundle root for the active integration backend.

The composition root (``init``/``create_app``) lives in
:mod:`plyunit.backends.integrations._bootstrap`. Everything else is
forwarded from the active backend via ``__getattr__``.

Generic public names (``Window``, ``Canvas``, ``AssetsLoader``, …) —
not ``Raylib*``. For concrete host paths (rare):

    from plyunit.backends.integrations.raylib.core import Window
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from plyunit.backends._selector import integration_module

from ._bootstrap import create_app, init

_active_integration = None


def _get_active_integration():
    """Import and cache the active integration module."""
    global _active_integration
    if _active_integration is None:
        _active_integration = import_module(integration_module())
    return _active_integration


# TYPE SAFE
if TYPE_CHECKING:
    from .raylib.assets import (
        FILTER_MODE_MAP as FILTER_MODE_MAP,
        WRAP_MODE_MAP as WRAP_MODE_MAP,
        AssetsLoader as AssetsLoader,
        Font as Font,
        ShaderLoader as ShaderLoader,
        get_assets_loader as get_assets_loader,
        get_font as get_font,
        get_shader_loader as get_shader_loader,
    )

    # AUDIO MODULE
    from .raylib.audio import (
        AudioBackend as AudioBackend,
        audio_backend as audio_backend,
        get_audio_backend as get_audio_backend,
    )

    # CORE
    from .raylib.core import (
        Camera2D as Camera2D,
        Window as Window,
        get_window as get_window,
    )

    # DRAWING
    from .raylib.drawing import (
        BatchingBackend as BatchingBackend,
        Canvas as Canvas,
        StreamingTexture as StreamingTexture,
        UnifiedBufferBatch as UnifiedBufferBatch,
        begin_stencil_mask as begin_stencil_mask,
        create_streaming_texture as create_streaming_texture,
        destroy_streaming_texture as destroy_streaming_texture,
        end_stencil_mask as end_stencil_mask,
        end_stencil_mask_inverse as end_stencil_mask_inverse,
        end_stencil_mode as end_stencil_mode,
        get_batching_backend as get_batching_backend,
        get_canvas as get_canvas,
        get_unified_buffer_batch as get_unified_buffer_batch,
        init_stencil as init_stencil,
        init_streaming as init_streaming,
        is_stencil_active as is_stencil_active,
        is_stencil_available as is_stencil_available,
        is_streaming_available as is_streaming_available,
        reset_unified_buffer_batch as reset_unified_buffer_batch,
        update_streaming_texture as update_streaming_texture,
    )

    # INPUT MODULE
    from .raylib.input import (
        GAMEPAD_AXES as GAMEPAD_AXES,
        GAMEPAD_BUTTONS as GAMEPAD_BUTTONS,
        MAP_BUTTON_MOUSE as MAP_BUTTON_MOUSE,
        MAP_CURSOR_MOUSE as MAP_CURSOR_MOUSE,
        Gamepad as Gamepad,
        Input as Input,
        Mouse as Mouse,
        Touch as Touch,
    )


__all__ = (
    "FILTER_MODE_MAP",
    "GAMEPAD_AXES",
    "GAMEPAD_BUTTONS",
    "MAP_BUTTON_MOUSE",
    "MAP_CURSOR_MOUSE",
    "WRAP_MODE_MAP",
    "AssetsLoader",
    "AudioBackend",
    "BatchingBackend",
    "Camera2D",
    "Canvas",
    "Font",
    "Gamepad",
    "Input",
    "Mouse",
    "ShaderLoader",
    "StreamingTexture",
    "Touch",
    "UnifiedBufferBatch",
    "Window",
    "audio_backend",
    "begin_stencil_mask",
    "create_app",
    "create_streaming_texture",
    "destroy_streaming_texture",
    "end_stencil_mask",
    "end_stencil_mask_inverse",
    "end_stencil_mode",
    "get_assets_loader",
    "get_audio_backend",
    "get_batching_backend",
    "get_canvas",
    "get_font",
    "get_shader_loader",
    "get_unified_buffer_batch",
    "get_window",
    "init",
    "init_stencil",
    "init_streaming",
    "is_stencil_active",
    "is_stencil_available",
    "is_streaming_available",
    "reset_unified_buffer_batch",
    "update_streaming_texture",
)

_SUBS = {
    # Assets
    "FILTER_MODE_MAP": "assets",
    "WRAP_MODE_MAP": "assets",
    "AssetsLoader": "assets",
    "get_assets_loader": "assets",
    # Shader
    "ShaderLoader": "assets",
    "get_shader_loader": "assets",
    # Font
    "Font": "assets",
    "get_font": "assets",
    # Audio
    "AudioBackend": "audio",
    "audio_backend": "audio",
    "get_audio_backend": "audio",
    # Batching (UBR)
    "BatchingBackend": "drawing",
    "UnifiedBufferBatch": "drawing",
    "get_batching_backend": "drawing",
    "get_unified_buffer_batch": "drawing",
    "reset_unified_buffer_batch": "drawing",
    # Core
    "Camera2D": "core",
    "Window": "core",
    "get_window": "core",
    # Drawing
    "Canvas": "drawing",
    "StreamingTexture": "drawing",
    "begin_stencil_mask": "drawing",
    "create_streaming_texture": "drawing",
    "destroy_streaming_texture": "drawing",
    "end_stencil_mask": "drawing",
    "end_stencil_mask_inverse": "drawing",
    "end_stencil_mode": "drawing",
    "get_canvas": "drawing",
    "init_stencil": "drawing",
    "init_streaming": "drawing",
    "is_stencil_active": "drawing",
    "is_stencil_available": "drawing",
    "is_streaming_available": "drawing",
    "update_streaming_texture": "drawing",
    # Input
    "GAMEPAD_AXES": "input",
    "GAMEPAD_BUTTONS": "input",
    "MAP_BUTTON_MOUSE": "input",
    "MAP_CURSOR_MOUSE": "input",
    "Gamepad": "input",
    "Input": "input",
    "Mouse": "input",
    "Touch": "input",
}


def __getattr__(name: str):
    """Lazy dispatcher for active integration backend attributes.

    Args:
        name: The requested attribute name.

    Returns:
        The attribute value from the active integration backend.

    Raises:
        AttributeError: If the attribute is not found in the bundle or a submodule.
    """
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    # 1. Try the bundle root first.
    try:
        value = getattr(_get_active_integration(), name)
        globals()[name] = value
        return value
    except AttributeError:
        pass

    # 2. Try the explicit submodule (e.g. ``audio``).
    sub = _SUBS.get(name)
    if sub is not None:
        try:
            value = getattr(import_module(f"{integration_module()}.{sub}"), name)
            globals()[name] = value
            return value
        except (ImportError, AttributeError) as exc:
            raise AttributeError(
                f"module 'plyunit.backends.integrations' has no attribute {name!r} "
                f"(checked {_get_active_integration().__name__} and {sub})"
            ) from exc
    # 3. Final fallback: look for ``name`` as a submodule of the bundle.
    try:
        value = getattr(import_module(f"{integration_module()}.{name}"), name)
        globals()[name] = value
        return value
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            f"module 'plyunit.backends.integrations' has no attribute {name!r} "
            f"(checked {_get_active_integration().__name__})"
        ) from exc


def __dir__() -> list[str]:
    """Return the attribute list for :func:`dir`.

    Returns:
        Sorted attribute names.
    """
    return sorted(set(globals()) | set(_SUBS))
