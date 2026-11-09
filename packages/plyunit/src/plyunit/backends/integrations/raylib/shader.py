"""Raylib shader service with handle-based resource ownership."""

from __future__ import annotations

from pathlib import Path

import pyray as pr

from plyunit._enums import ShaderUniform
from plyunit.backends.ports._unit import IServiceUnit
from plyunit.core.types import UniformValue
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.services.shaders.uniform import uniform_components

from .handler import Shader

__all__ = ("Shaders",)


def _to_uniform_buffer(value: UniformValue, uniform_type: ShaderUniform) -> object:
    """Build a correctly sized CFFI buffer for one validated numeric uniform."""
    values = uniform_components(value, uniform_type)
    storage = "float[]" if uniform_type <= ShaderUniform.VEC4 else "int[]"
    return pr.ffi.new(storage, values)


class Shaders(ServiceUnit):
    """Load shader handles and update named uniforms through raylib.

    Handles are strongly retained until explicit unload or service teardown.
    This service alone owns its loaded programs; other services' handles are
    never unloaded or updated. The built-in shader is always borrowed.
    """

    def __init__(self, tags: set[str] | None = None) -> None:
        """Initialize the shader service without requiring a graphics context.

        Args:
            tags: Extra tags added to the service unit.
        """
        super().__init__(name="Shaders", tags={"service", "shaders"} | (tags or set()))
        self._handles: dict[int, Shader] = {}
        self._owned: set[int] = set()

    def load(
        self, vs_path: str | Path | None = None, fs_path: str | Path | None = None
    ) -> Shader:
        """Load shader files, omitting empty or absent stages.

        Args:
            vs_path: Vertex shader path, or ``None`` to use the default stage.
            fs_path: Fragment shader path, or ``None`` to use the default stage.

        Returns:
            A tracked shader handle. With both stages absent, the default
            shader is borrowed rather than owned.

        Raises:
            RuntimeError: If loading fails, including raylib's default fallback
                after a requested shader fails to compile.
        """
        vs = str(vs_path) if vs_path else None
        fs = str(fs_path) if fs_path else None
        # Pyray accepts None for nullable C strings despite its str-only stubs.
        raw = pr.load_shader(vs, fs)  # pyrefly: ignore [bad-argument-type]
        return self._register(
            raw,
            stages_requested=bool(vs or fs),
            source=f"files {vs!r}, {fs!r}",
        )

    def load_from_memory(
        self, vs_code: str | None = None, fs_code: str | None = None
    ) -> Shader:
        """Load source strings, omitting empty or absent stages.

        Args:
            vs_code: Vertex source, or ``None`` to use the default stage.
            fs_code: Fragment source, or ``None`` to use the default stage.

        Returns:
            A tracked owned shader, or a borrowed default if both stages are
            absent.

        Raises:
            RuntimeError: If compilation fails or no valid shader is returned.
        """
        vs, fs = vs_code or None, fs_code or None
        # Pyray accepts None for nullable C strings despite its str-only stubs.
        raw = pr.load_shader_from_memory(vs, fs)  # pyrefly: ignore [bad-argument-type]
        return self._register(
            raw,
            stages_requested=bool(vs or fs),
            source="in-memory source",
        )

    def unload(self, handle: Shader | None) -> None:
        """Release a tracked shader and invalidate only its owning handle.

        Args:
            handle: Handle created by this service. ``None``, foreign handles,
                and previously released handles are ignored.

        An unload error leaves the handle tracked for a later retry. Borrowed
        default programs and their shared location arrays are never freed.
        """
        if handle is None or self._handles.get(id(handle)) is not handle:
            return
        raw = handle.raw_shader
        if raw is not None and id(handle) in self._owned:
            pr.unload_shader(raw)
        handle.raw_shader = None
        handle._valid = False
        handle.locations.clear()
        del self._handles[id(handle)]
        self._owned.discard(id(handle))

    def unload_all(self) -> None:
        """Attempt every tracked unload, retaining failures for retry.

        Raises:
            ExceptionGroup: If one or more backend unloads fail.
        """
        errors: list[Exception] = []
        for handle in list(self._handles.values()):
            try:
                self.unload(handle)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("failed to unload shaders", errors)

    def is_valid(self, handle: Shader | None) -> bool:
        """Return whether this service owns a live, usable shader handle."""
        if handle is None or self._handles.get(id(handle)) is not handle:
            return False
        raw = handle.raw_shader
        return bool(
            handle._valid and raw is not None and raw.id > 0 and pr.is_shader_valid(raw)
        )

    def get_shader(self, handle: Shader) -> Shader:
        """Return the same validated handle, never a raw backend shader.

        Args:
            handle: Shader handle owned by this service.

        Returns:
            The input handle, suitable for core rendering APIs.

        Raises:
            ValueError: If the handle is released, foreign, or invalid.
        """
        if not self.is_valid(handle):
            raise ValueError("invalid shader handle")
        return handle

    def set_value(
        self,
        handle: Shader,
        name: str,
        value: UniformValue,
        uniform_type: ShaderUniform | int,
    ) -> None:
        """Set one named scalar or vector uniform using a numeric value.

        Args:
            handle: Shader handle owned by this service; invalid handles are
                ignored.
            name: Uniform name; unknown names are ignored and cached.
            value: Scalar or numeric sequence with exactly the required number
                of components. Raw backend pointers are not accepted.
            uniform_type: Shared uniform enum or its integer value.

        Raises:
            TypeError: If values are not numeric.
            ValueError: If the type, component count, range, or precision is
                invalid.
        """
        if not self.is_valid(handle):
            return
        loc = self._location(handle, name)
        if loc < 0:
            return
        uniform = ShaderUniform(uniform_type)
        buffer = _to_uniform_buffer(value, uniform)
        raw = handle.raw_shader
        if raw is not None:
            pr.set_shader_value(raw, loc, buffer, int(uniform))

    def _register(
        self, raw: pr.Shader | None, *, stages_requested: bool, source: str
    ) -> Shader:
        """Validate a load result and track only resources this service may own."""
        default_id = int(pr.rl_get_shader_id_default())
        borrowed = default_id > 0 and raw is not None and int(raw.id) == default_id
        if raw is None or raw.id <= 0 or not pr.is_shader_valid(raw):
            if raw is not None and not borrowed:
                pr.unload_shader(raw)
            raise RuntimeError(f"failed to load shader from {source}")
        if borrowed and stages_requested:
            raise RuntimeError(
                f"failed to load shader from {source}; "
                "raylib returned its default shader"
            )
        try:
            handle = Shader.from_raw(raw)
        except BaseException:
            if not borrowed:
                pr.unload_shader(raw)
            raise
        self._handles[id(handle)] = handle
        if not borrowed:
            self._owned.add(id(handle))
        return handle

    def _location(self, handle: Shader, name: str) -> int:
        """Resolve uniform locations once per handle, including zero and misses."""
        cached = handle.locations.get(name)
        if cached is not None:
            return cached
        raw = handle.raw_shader
        if raw is None:
            return -1
        loc = int(pr.get_shader_location(raw, name))
        handle.locations[name] = loc
        return loc

    def on_detach(self, app: IServiceUnit) -> None:
        """Release shaders before the owning app closes its graphics context."""
        self.unload_all()

    def destroy(self) -> None:
        """Release shaders even if this service was never attached to an app."""
        self.unload_all()
        super().destroy()
