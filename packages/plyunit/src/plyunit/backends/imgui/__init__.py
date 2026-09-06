"""Lazy facade for the active ImGui backend.

Public names (``ImGuiBackend``, ``ImGui``, …) are forwarded lazily from
the active backend that follows the integration host (see
``_selector.imgui_module``) via ``__getattr__`` — this package can be
imported even when imgui-bundle is not installed; the error only appears
when an attribute is first accessed.

For a concrete host path (rare):

    from plyunit.backends.imgui.raylib import ImGui
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from plyunit.backends._selector import imgui_module

_active_backend = None


def _get_active_backend():
    """Import and cache the active ImGui backend module on first use."""
    global _active_backend
    if _active_backend is None:
        _active_backend = import_module(imgui_module())
    return _active_backend


# TYPE SAFE
if TYPE_CHECKING:
    from .raylib import (
        ImGui as ImGui,
        ImGuiBackend as ImGuiBackend,
        build_imgui_service as build_imgui_service,
    )


__all__ = ("ImGui", "ImGuiBackend", "build_imgui_service")

_SUBS = {
    "ImGuiBackend": "backend",
    "ImGui": "service",
    "build_imgui_service": "service",
}


def __getattr__(name: str):
    """Lazy dispatcher for attributes of the active ImGui backend.

    Args:
        name: Requested attribute name.

    Returns:
        The attribute value from the active ImGui backend.

    Raises:
        AttributeError: If the attribute is not found in the bundle or
            submodules.
    """
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    # 1. Try the bundle root first.
    try:
        value = getattr(_get_active_backend(), name)
        globals()[name] = value
        return value
    except AttributeError:
        pass

    # 2. Try the explicit submodule (e.g. ``service``).
    sub = _SUBS.get(name)
    if sub is not None:
        try:
            value = getattr(import_module(f"{imgui_module()}.{sub}"), name)
            globals()[name] = value
            return value
        except (ImportError, AttributeError) as exc:
            raise AttributeError(
                f"module 'plyunit.backends.imgui' has no attribute {name!r} "
                f"(checked {_get_active_backend().__name__} and {sub})"
            ) from exc
    # 3. Final fallback: look for ``name`` as a submodule of the bundle.
    try:
        value = getattr(import_module(f"{imgui_module()}.{name}"), name)
        globals()[name] = value
        return value
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            f"module 'plyunit.backends.imgui' has no attribute {name!r} "
            f"(checked {_get_active_backend().__name__})"
        ) from exc


def __dir__() -> list[str]:
    """Return the attribute list for :func:`dir`.

    Returns:
        The sorted list of attribute names.
    """
    return sorted(set(globals()) | set(_SUBS))
