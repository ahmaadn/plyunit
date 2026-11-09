"""Shared OpenGL FFI helper for the raylib integration modules.

Used by stencil masking, PBO streaming textures and the native UBR. Loads GL
entry points via ``rl_get_proc_address`` / ``glfw_get_proc_address`` and caches
them. This module is the *only* place that touches raw cffi objects: every
other module sees the small typed facade below (no ``Any`` leaks out).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, cast

import pyray as pr
import raylib as rl

from plyunit.backends.ports.handler import PixelBuffer

if TYPE_CHECKING:
    # The native CFFI extension is installed but does not ship a type stub.
    from _cffi_backend import FFI  # pyrefly: ignore [missing-import]

    type _CData = FFI.CData


class GlFunction(Protocol):
    """A resolved OpenGL entry point (cffi function pointer)."""

    def __call__(self, *args: object) -> object:
        """Invoke the GL function; arguments and result follow its C signature."""
        ...


class UIntBuffer(Protocol):
    """Native ``unsigned int[N]`` array (e.g. buffer object names)."""

    def __getitem__(self, index: int, /) -> int:
        """Return the element at ``index``."""
        ...


NULL_POINTER: object = pr.ffi.NULL
"""cffi ``NULL``; compare with :func:`is_null`."""

_gl_funcs: dict[str, GlFunction] = {}


def _native(value: object) -> _CData:
    """View an opaque pointer/function value as a cffi ``CData`` (no conversion)."""
    return cast("_CData", value)


def is_null(pointer: object) -> bool:
    """Return ``True`` if ``pointer`` is ``None`` or a NULL cffi pointer."""
    return pointer is None or bool(pointer == pr.ffi.NULL)


def ctype_of(value: object) -> object:
    """Return the cffi ctype of a native value (raises ``TypeError`` for non-cdata)."""
    return pr.ffi.typeof(_native(value))


def to_int(value: object) -> int:
    """Convert a GL return value (Python int or cffi integer) to ``int``."""
    if isinstance(value, int):
        return value
    return int(pr.ffi.cast("long long", _native(value)))


def address_of(symbol: object) -> int:
    """Return the integer address of a cffi function pointer / symbol."""
    return int(pr.ffi.cast("uintptr_t", _native(symbol)))


def proc_address(name: str) -> int:
    """Resolve a GL function address through ``rlGetProcAddress``.

    Args:
        name: GL function name (e.g. ``"glDrawElements"``).

    Returns:
        The function address as an integer.

    Raises:
        RuntimeError: If the symbol cannot be resolved.
    """
    raw = rl.rlGetProcAddress(name.encode("utf-8"))
    if is_null(raw):
        raise RuntimeError(f"glGetProcAddress failed for {name}")
    return address_of(raw)


def get_gl_func(name: str, signature: str) -> GlFunction:
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

    addr = _lookup_proc(name)
    if addr is None:
        raise RuntimeError(f"Failed to get OpenGL function: {name}")

    func: GlFunction = pr.ffi.cast(signature, addr)
    _gl_funcs[name] = func
    return func


def _lookup_proc(name: str) -> int | None:
    """Try raylib's loader first, then GLFW's; ``None`` if both fail."""
    for loader_name in ("rl_get_proc_address", "glfw_get_proc_address"):
        loader = getattr(pr, loader_name, None)
        if loader is None:
            continue
        try:
            raw = loader(name)
            if not is_null(raw) and raw != 0:
                return address_of(raw)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            continue
    return None


def new_uint_buffer(size: int, values: Sequence[int] | None = None) -> UIntBuffer:
    """Allocate a native ``unsigned int[size]`` array.

    Args:
        size: Number of elements.
        values: Optional initial values.
    """
    init = list(values) if values is not None else None
    return pr.ffi.new(f"unsigned int[{size}]", init)


def get_gl_integer(parameter: int) -> int:
    """Read a scalar OpenGL integer state value through the shared FFI facade.

    Args:
        parameter: OpenGL state enumeration accepted by ``glGetIntegerv``.

    Returns:
        The current state value.
    """
    value = pr.ffi.new("int[1]")
    get_gl_func("glGetIntegerv", "void(*)(unsigned int, int*)")(parameter, value)
    return int(value[0])


def new_float_buffer(values: Sequence[float]) -> object:
    """Allocate a native ``float[N]`` array initialised from ``values``."""
    return pr.ffi.new(f"float[{len(values)}]", list(values))


def copy_to_native(destination: object, source: PixelBuffer, size: int) -> None:
    """Copy ``size`` bytes of ``source`` into a native pointer (``memmove``)."""
    data = source if isinstance(source, (bytes, bytearray)) else bytes(source)
    pr.ffi.memmove(_native(destination), data, size)


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
    "NULL_POINTER",
    "GlFunction",
    "UIntBuffer",
    "address_of",
    "copy_to_native",
    "ctype_of",
    "flush_render_batch",
    "get_gl_func",
    "get_gl_integer",
    "has_gl_func",
    "is_null",
    "new_float_buffer",
    "new_uint_buffer",
    "proc_address",
    "reset_gl_funcs",
    "to_int",
]
