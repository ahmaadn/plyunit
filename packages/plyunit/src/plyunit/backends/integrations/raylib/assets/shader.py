"""Shader loading and uniform binding for the raylib backend."""

from typing import Any

import pyray as pr

# Float-based raylib uniform types (FLOAT, VEC2, VEC3, VEC4)
_FLOAT_UNIFORM_TYPES = frozenset({0, 1, 2, 3})

# Integer-based raylib uniform types (INT, IVEC2..IVEC4, SAMPLER2D)
_INT_UNIFORM_TYPES = frozenset({4, 5, 6, 7, 8})


def _to_uniform_buffer(value: Any, uniform_type: int) -> Any:
    """Convert a Python value into a cffi buffer for ``SetShaderValue``.

    The pyray cffi binding expects a cdata pointer for uniform value
    arguments; scalars and numeric sequences are wrapped into ``float[]``/
    ``int[]`` arrays according to the raylib ``SHADER_UNIFORM_*`` type.
    Anything else (e.g. a caller-made cdata pointer) is passed through
    unchanged.

    Args:
        value: Uniform value (scalar, numeric sequence, or cdata buffer).
        uniform_type: Raylib ``SHADER_UNIFORM_*`` uniform type.

    Returns:
        Any: A buffer ready to pass to ``pr.set_shader_value``.
    """
    ffi = getattr(pr, "ffi", None)
    if ffi is None:
        return value

    if isinstance(value, (int, float)):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return value

    if uniform_type in _FLOAT_UNIFORM_TYPES:
        return ffi.new("float[]", [float(v) for v in values])
    if uniform_type in _INT_UNIFORM_TYPES:
        return ffi.new("int[]", [int(v) for v in values])
    return value


def load_shader(vs_path: str, fs_path: str) -> Any:
    """Load a shader from vertex and fragment files on disk.

    Args:
        vs_path: Path to the vertex shader file (may be empty).
        fs_path: Path to the fragment shader file (may be empty).

    Returns:
        Any: Raw shader object from raylib.
    """

    return pr.load_shader(vs_path, fs_path)


def load_shader_from_memory(vs_code: str, fs_code: str) -> Any:
    """Load a shader from in-memory source strings.

    Args:
        vs_code: Vertex shader source code (may be empty).
        fs_code: Fragment shader source code (may be empty).

    Returns:
        Any: Raw shader object from raylib.
    """

    return pr.load_shader_from_memory(vs_code, fs_code)


def unload_shader(raw: Any) -> None:
    """Release a raw shader from GPU memory.

    Args:
        raw: Raw raylib shader object; skipped when ``None``.
    """

    if raw is not None:
        pr.unload_shader(raw)


def get_shader_location(raw: Any, name: str) -> int:
    """Look up a uniform location by name in a raw shader.

    Args:
        raw: Raw raylib shader object.
        name: The uniform name to look up.

    Returns:
        int: The uniform location index; negative when not found.
    """

    return pr.get_shader_location(raw, name)


def set_shader_value(raw: Any, loc: int, value: Any, uniform_type: int) -> None:
    """Set a uniform value on a raw shader.

    Scalars and numeric sequences are automatically wrapped into the cffi
    buffer the raylib binding expects; ready-made cdata pointers are
    passed through directly.

    Args:
        raw: Raw raylib shader object.
        loc: Uniform location index from ``get_shader_location``.
        value: Uniform value (scalar, numeric sequence, or cdata buffer).
        uniform_type: Uniform type from ``ShaderUniform``.
    """
    buffer = _to_uniform_buffer(value, uniform_type)
    pr.set_shader_value(raw, loc, buffer, uniform_type)
