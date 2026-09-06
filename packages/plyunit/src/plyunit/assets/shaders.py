"""Shader handling: uniform types, handles, and the ``ServiceUnit`` service.

This module provides the uniform type enum (``ShaderUniform``), the
shader handle wrapper (``ShaderHandle``), the shader loading/setting
service (``Shaders``), plus the default raylib-based backend and a
global backend access helper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

from plyunit.backends.interfaces.i_shader import IShaderLoader
from plyunit.core.units.service_unit import ServiceUnit


class ShaderUniform(IntEnum):
    """Uniform type IDs matching the numeric ``SHADER_UNIFORM_*`` raylib values.

    The enum values intentionally match the raylib constants so they can
    be passed straight to the backend without extra mapping.
    """

    FLOAT = 0  # Single float uniform.
    VEC2 = 1  # 2-component (float) vector uniform.
    VEC3 = 2  # 3-component (float) vector uniform.
    VEC4 = 3  # 4-component (float) vector uniform.
    INT = 4  # Single integer uniform.
    IVEC2 = 5  # 2-component (integer) vector uniform.
    IVEC3 = 6  # 3-component (integer) vector uniform.
    IVEC4 = 7  # 4-component (integer) vector uniform.
    SAMPLER2D = 8  # 2D texture sampler.


@dataclass(slots=True)
class ShaderHandle:
    """Opaque wrapper around a loaded backend shader object.

    The handle stores the raw shader reference along with a uniform
    location cache and validity state, so callers never need to touch
    the backend directly.
    """

    raw: Any
    """The raw shader object from the raylib backend (or ``None`` after unload)."""
    _locations: dict[str, int] = field(default_factory=dict, repr=False)
    """Cache of already-resolved uniform locations per name (internal)."""
    _valid: bool = True
    """Whether the handle is still valid and not yet unloaded (internal)."""

    @property
    def shader(self) -> Any:
        """Any: The raw shader object wrapped by the handle (alias for ``raw``)."""
        return self.raw


class Shaders(ServiceUnit):
    """Shader loading and name-based uniform setting service.

    This ``ServiceUnit`` keeps the set of active handles, supports
    loading from files or memory, setting uniforms by name with location
    caching, and releasing shaders that are no longer used.
    """

    def __init__(self, loader: IShaderLoader | None = None) -> None:
        """Initialize the shader service.

        Args:
            loader: Optional shader loader; when ``None`` it is lazily
                resolved to the built-in raylib loader.
        """
        super().__init__(name="Shaders", tags={"service", "shaders"})

        if loader is None:
            from plyunit.backends.integrations import ShaderLoader

            loader = ShaderLoader()
        self._loader = loader
        self._handles: set[int] = set()

    def load(
        self,
        vs_path: str | Path | None = None,
        fs_path: str | Path | None = None,
    ) -> ShaderHandle:
        """Load a shader from files on disk and wrap it in a handle.

        Args:
            vs_path: Path to the vertex shader file (``None``/empty = no
                vertex shader).
            fs_path: Path to the fragment shader file (``None``/empty = no
                fragment shader).

        Returns:
            ShaderHandle: The newly loaded shader handle.
        """
        vs = str(vs_path) if vs_path is not None else ""
        fs = str(fs_path) if fs_path is not None else ""
        raw = self._loader.load_shader(vs, fs)
        handle = ShaderHandle(raw=raw)
        self._handles.add(id(handle))
        return handle

    def load_from_memory(self, vs_code: str, fs_code: str) -> ShaderHandle:
        """Load a shader from in-memory code strings and wrap it in a handle.

        Args:
            vs_code: Vertex shader source code (may be empty).
            fs_code: Fragment shader source code (may be empty).

        Returns:
            ShaderHandle: The newly loaded shader handle.
        """
        raw = self._loader.load_shader_from_memory(vs_code, fs_code)
        handle = ShaderHandle(raw=raw)
        self._handles.add(id(handle))
        return handle

    def unload(self, handle: ShaderHandle | None) -> None:
        """Release the shader and mark the handle as invalid.

        Args:
            handle: The shader handle to release; ``None`` or an already
                invalid handle is skipped with no effect.
        """
        if handle is None or not handle._valid:
            return
        if handle.raw is not None:
            self._loader.unload_shader(handle.raw)
        handle._valid = False
        handle.raw = None
        self._handles.discard(id(handle))

    def is_valid(self, handle: ShaderHandle | None) -> bool:
        """Check whether a handle is still valid and its raw shader still exists.

        Args:
            handle: The shader handle to check (may be ``None``).

        Returns:
            bool: ``True`` if the handle is valid and its raw shader is not None.
        """
        if handle is None:
            return False
        return bool(handle._valid and handle.raw is not None)

    def get_shader(self, handle: ShaderHandle) -> Any:
        """Fetch the raw shader object from a valid handle.

        Args:
            handle: A still-valid shader handle.

        Returns:
            Any: The raw raylib shader object.

        Raises:
            ValueError: If the handle is invalid.
        """
        if not self.is_valid(handle):
            raise ValueError("invalid shader handle")
        return handle.raw

    def _location(self, handle: ShaderHandle, name: str) -> int:
        """Resolve a uniform location by name, cached per handle.

        Args:
            handle: A still-valid shader handle.
            name: The uniform name to look up.

        Returns:
            int: The uniform location index; negative if not found.
        """
        cached = handle._locations.get(name)
        if cached is not None:
            return cached
        loc = self._loader.get_shader_location(handle.raw, name)
        handle._locations[name] = loc
        return loc

    def set_value(
        self,
        handle: ShaderHandle,
        name: str,
        value: float | int | Sequence[float] | Sequence[int],
        uniform_type: ShaderUniform | int,
    ) -> None:
        """Set a uniform value by name on a valid shader.

        Args:
            handle: The target shader handle; silently skipped if not
                valid.
            name: The uniform name to set.
            value: The uniform value (scalar or sequence of numbers).
            uniform_type: The uniform type from ``ShaderUniform`` or an int.
        """
        if not self.is_valid(handle):
            return
        loc = self._location(handle, name)
        if loc < 0:
            return
        self._loader.set_shader_value(handle.raw, loc, value, int(uniform_type))


__all__ = [
    "ShaderHandle",
    "ShaderUniform",
    "Shaders",
]
