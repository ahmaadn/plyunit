"""Stencil buffer masking via OpenGL (shared raylib context).

Typical usage (the Canvas wrapper is preferred)::

    Canvas.begin_stencil_mask()
    canvas.draw_circle(center=(200, 200), radius=80, color=WHITE)
    Canvas.end_stencil_mask()          # content only inside the mask
    canvas.draw_texture(...)
    Canvas.end_stencil_mode()
"""

from __future__ import annotations

import logging

from .gl_ffi import flush_render_batch, get_gl_func, reset_gl_funcs

logger = logging.getLogger(__name__)

# OpenGL constants
GL_STENCIL_TEST = 0x0B90
GL_DEPTH_TEST = 0x0B71
GL_STENCIL_BUFFER_BIT = 0x00000400
GL_ALWAYS = 0x0207
GL_KEEP = 0x1E00
GL_REPLACE = 0x1E01
GL_EQUAL = 0x0202
GL_NOTEQUAL = 0x0205

_initialized = False
_active = False
_depth_was_enabled = True


def init_stencil() -> bool:
    """Load GL stencil entry points. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return True
    try:
        get_gl_func("glEnable", "void(*)(unsigned int)")
        get_gl_func("glDisable", "void(*)(unsigned int)")
        get_gl_func("glIsEnabled", "unsigned char(*)(unsigned int)")
        get_gl_func("glClear", "void(*)(unsigned int)")
        get_gl_func("glClearStencil", "void(*)(int)")
        get_gl_func("glStencilFunc", "void(*)(unsigned int, int, unsigned int)")
        get_gl_func("glStencilOp", "void(*)(unsigned int, unsigned int, unsigned int)")
        get_gl_func("glStencilMask", "void(*)(unsigned int)")
        get_gl_func(
            "glColorMask",
            "void(*)(unsigned char, unsigned char, unsigned char, unsigned char)",
        )
        _initialized = True
        return True
    except RuntimeError as exc:
        logger.warning("Stencil init failed: %s", exc)
        reset_gl_funcs()
        _initialized = False
        return False


def reset_stencil() -> None:
    """Reset module state (tests / window recreate)."""
    global _initialized, _active, _depth_was_enabled
    _initialized = False
    _active = False
    _depth_was_enabled = True


def is_stencil_available() -> bool:
    """Return ``True`` if stencil entry points have been initialized."""
    return _initialized


def is_stencil_active() -> bool:
    """Return ``True`` while a stencil mask/mode session is active."""
    return _active


def begin_stencil_mask() -> None:
    """Start writing the stencil mask (geometry drawn here is invisible)."""
    global _active, _depth_was_enabled
    if not _initialized and not init_stencil():
        return

    flush_render_batch()

    gl_enable = get_gl_func("glEnable", "void(*)(unsigned int)")
    gl_disable = get_gl_func("glDisable", "void(*)(unsigned int)")
    gl_is_enabled = get_gl_func("glIsEnabled", "unsigned char(*)(unsigned int)")
    gl_stencil_func = get_gl_func(
        "glStencilFunc", "void(*)(unsigned int, int, unsigned int)"
    )
    gl_stencil_op = get_gl_func(
        "glStencilOp", "void(*)(unsigned int, unsigned int, unsigned int)"
    )
    gl_stencil_mask = get_gl_func("glStencilMask", "void(*)(unsigned int)")
    gl_color_mask = get_gl_func(
        "glColorMask",
        "void(*)(unsigned char, unsigned char, unsigned char, unsigned char)",
    )
    gl_clear = get_gl_func("glClear", "void(*)(unsigned int)")
    gl_clear_stencil = get_gl_func("glClearStencil", "void(*)(int)")

    _depth_was_enabled = bool(gl_is_enabled(GL_DEPTH_TEST))
    if _depth_was_enabled:
        gl_disable(GL_DEPTH_TEST)

    gl_enable(GL_STENCIL_TEST)
    gl_stencil_mask(0xFF)
    gl_clear_stencil(0)
    gl_clear(GL_STENCIL_BUFFER_BIT)
    gl_stencil_func(GL_ALWAYS, 1, 0xFF)
    gl_stencil_op(GL_KEEP, GL_KEEP, GL_REPLACE)
    gl_stencil_mask(0xFF)
    gl_color_mask(0, 0, 0, 0)
    _active = True


def _end_stencil_mask(*, equal: bool) -> None:
    """Finish mask writing and set stencil test to EQUAL or NOTEQUAL."""
    if not _initialized:
        return

    flush_render_batch()

    gl_stencil_func = get_gl_func(
        "glStencilFunc", "void(*)(unsigned int, int, unsigned int)"
    )
    gl_stencil_op = get_gl_func(
        "glStencilOp", "void(*)(unsigned int, unsigned int, unsigned int)"
    )
    gl_stencil_mask = get_gl_func("glStencilMask", "void(*)(unsigned int)")
    gl_color_mask = get_gl_func(
        "glColorMask",
        "void(*)(unsigned char, unsigned char, unsigned char, unsigned char)",
    )

    gl_color_mask(1, 1, 1, 1)
    gl_stencil_func(GL_EQUAL if equal else GL_NOTEQUAL, 1, 0xFF)
    gl_stencil_op(GL_KEEP, GL_KEEP, GL_KEEP)
    gl_stencil_mask(0x00)


def end_stencil_mask() -> None:
    """Finish mask write; subsequent draws only appear where mask == 1."""
    _end_stencil_mask(equal=True)


def end_stencil_mask_inverse() -> None:
    """Finish mask write; subsequent draws only appear where mask != 1."""
    _end_stencil_mask(equal=False)


def end_stencil_mode() -> None:
    """Disable stencil testing and restore normal rendering."""
    global _active
    if not _initialized:
        return

    flush_render_batch()

    gl_enable = get_gl_func("glEnable", "void(*)(unsigned int)")
    gl_disable = get_gl_func("glDisable", "void(*)(unsigned int)")
    gl_stencil_mask = get_gl_func("glStencilMask", "void(*)(unsigned int)")
    gl_color_mask = get_gl_func(
        "glColorMask",
        "void(*)(unsigned char, unsigned char, unsigned char, unsigned char)",
    )

    gl_color_mask(1, 1, 1, 1)
    gl_disable(GL_STENCIL_TEST)
    gl_stencil_mask(0xFF)
    if _depth_was_enabled:
        gl_enable(GL_DEPTH_TEST)
    _active = False


__all__ = [
    "begin_stencil_mask",
    "end_stencil_mask",
    "end_stencil_mask_inverse",
    "end_stencil_mode",
    "init_stencil",
    "is_stencil_active",
    "is_stencil_available",
    "reset_stencil",
]
