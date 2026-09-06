"""GPU shader load/uniform contracts for the host backend.

This module defines :class:`IShaderLoader` — the protocol every shader
backend must satisfy (injected; default = raylib). Backends implement
loading shaders from file or memory, unloading, looking up uniform
locations, and setting uniform values.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IShaderLoader(Protocol):
    """Backend ops for loading/setting shaders (injected; default = raylib)."""

    def load_shader(self, vs_path: str, fs_path: str) -> Any:
        """Load a shader program from vertex and fragment shader files.

        Args:
            vs_path: Vertex shader file path (empty string for none).
            fs_path: Fragment shader file path (empty string for none).

        Returns:
            The backend shader handle.
        """
        ...

    def load_shader_from_memory(self, vs_code: str, fs_code: str) -> Any:
        """Load a shader program from vertex and fragment source strings.

        Args:
            vs_code: Vertex shader GLSL source (empty string for none).
            fs_code: Fragment shader GLSL source (empty string for none).

        Returns:
            The backend shader handle.
        """
        ...

    def unload_shader(self, raw: Any) -> None:
        """Unload a shader program and free its GPU resources.

        Args:
            raw: Shader handle to unload.
        """
        ...

    def get_shader_location(self, raw: Any, name: str) -> int:
        """Look up a uniform (or attribute) location in a shader.

        Args:
            raw: Shader handle to query.
            name: Uniform variable name.

        Returns:
            The location handle, or -1 when not found.
        """
        ...

    def set_shader_value(
        self, raw: Any, loc: int, value: Any, uniform_type: int
    ) -> None:
        """Set a uniform value on a shader.

        Args:
            raw: Shader handle to update.
            loc: Uniform location from :meth:`get_shader_location`.
            value: Uniform value (backend-dependent buffer or sequence).
            uniform_type: Backend uniform-type constant describing ``value``.
        """
        ...


__all__ = ["IShaderLoader"]
