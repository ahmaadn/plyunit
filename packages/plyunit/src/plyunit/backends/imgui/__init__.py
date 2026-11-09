"""Lazy facade for the active ImGui integration.

``ImGui`` is forwarded lazily from the integration selected by
``_selector.imgui_module``. Importing this package does not require
imgui-bundle or a live graphics context.

For a concrete host path:

    from plyunit.backends.imgui.raylib_integration import ImGui
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

from plyunit.backends._selector import imgui_module

if TYPE_CHECKING:
    from .raylib_integration import ImGui as ImGui


__all__ = ("ImGui",)

_active_backend: ModuleType | None = None


def _get_active_backend() -> ModuleType:
    """Import and cache the active ImGui integration on first use."""
    global _active_backend
    if _active_backend is None:
        _active_backend = import_module(imgui_module())
    return _active_backend


def __getattr__(name: str):
    """Resolve and cache public attributes of the active ImGui integration."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_get_active_backend(), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return the attribute list including lazy public exports."""
    return sorted(set(globals()) | set(__all__))
