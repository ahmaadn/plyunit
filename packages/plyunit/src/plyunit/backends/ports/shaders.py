"""Port for shader loading, lifetime management, and uniform updates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ._unit import IServiceUnit

if TYPE_CHECKING:
    from plyunit._enums import ShaderUniform
    from plyunit.core.types import UniformValue

    from .handler import ShaderHandle

__all__ = ("IShaders",)


@runtime_checkable
class IShaders(IServiceUnit, Protocol):
    """Shader service contract using dedicated handles, never raw shaders."""

    def load(
        self,
        vs_path: str | Path | None = None,
        fs_path: str | Path | None = None,
    ) -> ShaderHandle:
        """Load shader files, omitting stages passed as ``None`` or empty strings.

        With both stages omitted, return a borrowed default-shader handle.
        Failed compilation raises an error rather than owning the default.
        """
        ...

    def load_from_memory(
        self, vs_code: str | None = None, fs_code: str | None = None
    ) -> ShaderHandle:
        """Load source strings with the same stage-omission rules as ``load``."""
        ...

    def unload(self, handle: ShaderHandle | None) -> None:
        """Release a handle from this service and invalidate it.

        ``None``, released handles, and handles owned by another service are
        ignored. A backend unload error leaves the handle tracked for retry.
        """
        ...

    def unload_all(self) -> None:
        """Release all tracked handles, attempting every unload even on errors."""
        ...

    def is_valid(self, handle: ShaderHandle | None) -> bool:
        """Return whether this service owns a live handle with a valid shader."""
        ...

    def get_shader(self, handle: ShaderHandle) -> ShaderHandle:
        """Return the same validated handle, or raise ``ValueError``.

        Backend adapters unwrap ``raw_shader``; core callers keep the handle.
        """
        ...

    def set_value(
        self,
        handle: ShaderHandle,
        name: str,
        value: UniformValue,
        uniform_type: ShaderUniform | int,
    ) -> None:
        """Update a named scalar or vector uniform using numeric values.

        Invalid handles and unknown names are ignored. Values for known
        uniforms must contain exactly the component count required by the
        uniform type; raw backend pointers are not part of this port.
        """
        ...
