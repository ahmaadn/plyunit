"""Shared OpenGL FFI helper for the raylib integration modules.

Used by stencil masking and PBO streaming textures. Loads GL entry points
via ``rl_get_proc_address`` / ``glfw_get_proc_address`` and caches them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyray as pr

_gl_funcs: dict[str, Any] = {}


def get_gl_func(name: str, signature: str) -> Callable[..., Any]:
    """Resolve and cache an OpenGL function pointer.

    Args:
        name: GL function name (e.g. ``"glEnable"``).
        signature: CFFI signature used to cast the function pointer.

    Returns:
        FFI callable for the GL function.

    Raises:
        RuntimeError: If the function pointer cannot be found.
    """
    cached = _gl_funcs.get(name)
    if cached is not None:
        return cached

    addr = None
    if hasattr(pr, "rl_get_proc_address"):
        try:
            addr = pr.rl_get_proc_address(name)
        except Exception:
            addr = None
    if addr in (None, 0, pr.ffi.NULL) and hasattr(pr, "glfw_get_proc_address"):
        try:
            addr = pr.glfw_get_proc_address(name.encode("utf-8"))
        except Exception:
            addr = None
    if addr in (None, 0, pr.ffi.NULL):
        raise RuntimeError(f"Failed to get OpenGL function: {name}")

    func = pr.ffi.cast(signature, addr)
    _gl_funcs[name] = func
    return func


def flush_render_batch() -> None:
    """Flush pending raylib/rlgl batched rendering before GL state changes."""
    pr.rl_draw_render_batch_active()


def reset_gl_funcs() -> None:
    """Clear the cached GL function pointers (tests / context re-creation)."""
    _gl_funcs.clear()


def has_gl_func(name: str) -> bool:
    """Return ``True`` if ``name`` is already cached in ``_gl_funcs``."""
    return name in _gl_funcs


__all__ = [
    "flush_render_batch",
    "get_gl_func",
    "has_gl_func",
    "reset_gl_funcs",
]
