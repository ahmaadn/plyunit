"""Raylib adapter: native UBR expand/upload + raw glDrawElements.

Shader/MVP setup cached in Python (cffi Matrix). Draw uses raw GL because
``rlDrawVertexArrayElements`` does not produce pixels for custom VAOs
on raylib-python-cffi (verified).
"""

from __future__ import annotations

import contextlib
import importlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np
import pyray as pr
import raylib as rl

from plyunit._constants import MAX_SPRITES
from plyunit.backends.ports.renderer import IUnifiedBufferBatch

from ..handler import RenderTexture, Texture2D
from .gl_ffi import (
    address_of,
    get_gl_func,
    new_float_buffer,
    proc_address,
    to_int,
)

if TYPE_CHECKING:
    import numpy.typing as npt

    from plyunit.backends.ports.renderer import FrameArray

logger = logging.getLogger(__name__)

_GL_TEXTURE0 = 0x84C0
_GL_TEXTURE_2D = 0x0DE1
_GL_ELEMENT_ARRAY_BUFFER = 0x8893
_GL_TRIANGLES = 0x0004
_GL_UNSIGNED_INT = 0x1405
_RL_FLOAT = 0x1406  # rlgl RL_FLOAT (== GL_FLOAT)
_RL_UNSIGNED_BYTE = 0x1401  # rlgl RL_UNSIGNED_BYTE (== GL_UNSIGNED_BYTE)
_SHADER_LOC_COUNT = 32
_SAMPLER_UNIFORM = b"texture0"
_WHITE = (1.0, 1.0, 1.0, 1.0)

# dispatch key -> rlgl symbol (address taken from the raylib shared library)
_RLGL_SYMBOLS: Mapping[str, str] = {
    "rl_load_vertex_array": "rlLoadVertexArray",
    "rl_enable_vertex_array": "rlEnableVertexArray",
    "rl_disable_vertex_array": "rlDisableVertexArray",
    "rl_unload_vertex_array": "rlUnloadVertexArray",
    "rl_load_vertex_buffer": "rlLoadVertexBuffer",
    "rl_load_vertex_buffer_element": "rlLoadVertexBufferElement",
    "rl_update_vertex_buffer": "rlUpdateVertexBuffer",
    "rl_unload_vertex_buffer": "rlUnloadVertexBuffer",
    "rl_set_vertex_attribute": "rlSetVertexAttribute",
    "rl_enable_vertex_attribute": "rlEnableVertexAttribute",
}

# dispatch key -> OpenGL entry point (resolved through rlGetProcAddress)
_GL_SYMBOLS: Mapping[str, str] = {
    "gl_bind_vertex_array": "glBindVertexArray",
    "gl_bind_buffer": "glBindBuffer",
    "gl_active_texture": "glActiveTexture",
    "gl_bind_texture": "glBindTexture",
    "gl_draw_elements": "glDrawElements",
    "gl_uniform1i": "glUniform1i",
}


class NativeBatchModule(Protocol):
    """Surface of the ``plyunit._plyunit_batch`` C extension used here."""

    def set_rlgl(self, dispatch: Mapping[str, int], /) -> None:
        """Hand rlgl/GL function addresses and constants to the extension."""
        ...

    def has_rlgl(self) -> bool:
        """Return whether :meth:`set_rlgl` took effect."""
        ...

    def ubr_init(self, max_sprites: int, /) -> None:
        """Allocate the persistent VBO/EBO for ``max_sprites`` sprites."""
        ...

    def ubr_is_ready(self) -> bool:
        """Return whether :meth:`ubr_init` completed."""
        ...

    def ubr_shutdown(self) -> None:
        """Free the native buffers."""
        ...

    def ubr_submit_frame(
        self,
        pos: npt.NDArray[np.float32],
        size: npt.NDArray[np.float32],
        origin: npt.NDArray[np.float32],
        rotation: npt.NDArray[np.float32],
        rgba: npt.NDArray[np.uint8],
        uv: npt.NDArray[np.float32],
        run_starts: npt.NDArray[np.int32],
        run_counts: npt.NDArray[np.int32],
        run_tex_ids: npt.NDArray[np.uint32],
        n_sprites: int,
        n_runs: int,
        /,
    ) -> None:
        """Expand, upload and draw one frame of sprites."""
        ...


@dataclass(frozen=True, slots=True)
class _ShaderState:
    """Default-shader bindings resolved once after the GL context exists."""

    shader_id: int
    sampler_loc: int
    loc_mvp: int
    loc_diff: int
    uniform_vec4: int
    white: object


def _load_native() -> NativeBatchModule:
    """Import the native batch C-extension or raise a helpful RuntimeError."""
    try:
        module = importlib.import_module("plyunit._plyunit_batch")
    except Exception as exc:
        raise RuntimeError(
            "C-extension plyunit._plyunit_batch is required for sprite rendering "
            "(no Python draw path). Reinstall with a C compiler available:\n"
            "  uv sync --reinstall-package plyunit-native\n"
            "  cd packages/plyunit-native && "
            "python setup.py build_ext --inplace --compiler=mingw32\n"
            "See also: ./init.sh and ./verify.sh in the repository root."
        ) from exc
    return cast(NativeBatchModule, module)


def _rlgl_address(name: str) -> int:
    """Return the address of an rlgl symbol exported by the raylib library."""
    symbol: object | None = getattr(rl.rl, name, None)
    if symbol is None:
        raise AttributeError(f"rlgl symbol missing: {name}")
    return address_of(symbol)


def _bind_dispatch(ext: NativeBatchModule, *, sampler_loc: int) -> None:
    """Pass rlgl/GL function addresses and constants to the native module."""
    dispatch: dict[str, int] = {
        **{key: _rlgl_address(name) for key, name in _RLGL_SYMBOLS.items()},
        **{key: proc_address(name) for key, name in _GL_SYMBOLS.items()},
        "rl_float": _RL_FLOAT,
        "rl_unsigned_byte": _RL_UNSIGNED_BYTE,
        "sampler_uniform_loc": int(sampler_loc),
        "gl_texture0": _GL_TEXTURE0,
        "gl_texture_2d": _GL_TEXTURE_2D,
        "gl_element_array_buffer": _GL_ELEMENT_ARRAY_BUFFER,
        "gl_triangles": _GL_TRIANGLES,
        "gl_unsigned_int": _GL_UNSIGNED_INT,
    }
    ext.set_rlgl(dispatch)
    if not ext.has_rlgl():
        raise RuntimeError("set_rlgl did not stick (has_rlgl==0)")


def _query_sampler_location(shader_id: int, default_locs: list[int]) -> int:
    """Locate the ``texture0`` sampler uniform of the default shader."""
    try:
        get_location = get_gl_func(
            "glGetUniformLocation", "int(*)(unsigned int, const char *)"
        )
        use_program = get_gl_func("glUseProgram", "void(*)(unsigned int)")
    except RuntimeError:
        return int(default_locs[int(rl.SHADER_LOC_MAP_ALBEDO)])
    use_program(shader_id)
    location = to_int(get_location(shader_id, _SAMPLER_UNIFORM))
    use_program(0)
    return location


def _resolve_shader_state() -> _ShaderState:
    """Resolve default shader id and uniform locations (needs a GL context)."""
    shader_id = int(rl.rlGetShaderIdDefault())
    locs = [
        int(v) for v in pr.ffi.unpack(rl.rlGetShaderLocsDefault(), _SHADER_LOC_COUNT)
    ]
    return _ShaderState(
        shader_id=shader_id,
        sampler_loc=_query_sampler_location(shader_id, locs),
        loc_mvp=locs[int(rl.SHADER_LOC_MATRIX_MVP)],
        loc_diff=locs[int(rl.SHADER_LOC_COLOR_DIFFUSE)],
        uniform_vec4=int(rl.SHADER_UNIFORM_VEC4),
        white=new_float_buffer(_WHITE),
    )


def _prepare_shader(state: _ShaderState) -> None:
    """Flush raylib batch; bind default shader + MVP (cached locs)."""
    rl.rlDrawRenderBatchActive()
    rl.rlEnableShader(state.shader_id)
    mvp = rl.MatrixMultiply(rl.rlGetMatrixModelview(), rl.rlGetMatrixProjection())
    if state.loc_mvp >= 0:
        rl.rlSetUniformMatrix(state.loc_mvp, mvp)
    if state.loc_diff >= 0:
        rl.rlSetUniform(state.loc_diff, state.white, state.uniform_vec4, 1)
    rl.rlDisableBackfaceCulling()
    rl.rlEnableColorBlend()


def _frame_view[T: np.generic](
    array: FrameArray, length: int, dtype: type[T]
) -> npt.NDArray[T]:
    """Return the first ``length`` rows as a C-contiguous ``dtype`` array.

    Zero-copy when ``array`` already matches; otherwise one copy.
    """
    view = array if array.shape[0] == length else array[:length]
    return np.ascontiguousarray(view, dtype=dtype)


class UnifiedBufferBatch(IUnifiedBufferBatch):
    """Native expand/upload/glDraw; Python prepares raylib default shader."""

    def __init__(self, max_sprites: int = MAX_SPRITES) -> None:
        """Initialize bookkeeping; native resources are created lazily by init().

        Args:
            max_sprites: Maximum sprites per frame (batch capacity).
        """
        if (
            isinstance(max_sprites, bool)
            or not isinstance(max_sprites, int)
            or max_sprites <= 0
        ):
            raise ValueError("max_sprites must be a positive integer")
        self._max_sprites = max_sprites
        self._capacity = 0
        self._ext: NativeBatchModule | None = None
        self._shader: _ShaderState | None = None

    @property
    def capacity(self) -> int:
        """Current sprite batch capacity (0 until init() succeeds)."""
        return self._capacity

    def texture_id(self, handle: Texture2D | RenderTexture) -> int:
        """Resolve a concrete raylib handle to its native GPU texture name.

        Args:
            handle: Raylib texture or render target. Logical asset/region IDs
                are metadata and are never submitted to the native batch.

        Returns:
            The color texture's numeric raylib ID, shared by region handles.

        Raises:
            TypeError: If the argument is not a concrete raylib handle.
        """
        if not isinstance(handle, (Texture2D, RenderTexture)):
            raise TypeError("UBR requires a raylib Texture2D or RenderTexture handle")
        return int(handle.raw_texture.id)

    def init(self, max_sprites: int | None = None) -> None:
        """Resolve shader uniforms, bind the native dispatch, and allocate buffers.

        Args:
            max_sprites: Optional new maximum sprite count.

        Raises:
            RuntimeError: If the native module fails to initialize.
            ValueError: If capacity is invalid or would change a live batch.
        """
        requested = self._max_sprites if max_sprites is None else max_sprites
        if (
            isinstance(requested, bool)
            or not isinstance(requested, int)
            or requested <= 0
        ):
            raise ValueError("max_sprites must be a positive integer")
        if self._ext is not None:
            if requested != self._capacity:
                raise ValueError("UBR capacity cannot change before shutdown()")
            return
        self._max_sprites = requested
        ext = _load_native()
        shader = _resolve_shader_state()

        _bind_dispatch(ext, sampler_loc=shader.sampler_loc)
        try:
            ext.ubr_init(self._max_sprites)
            if not ext.ubr_is_ready():
                raise RuntimeError("ubr_init reported not ready")
        except BaseException:
            with contextlib.suppress(Exception):
                ext.ubr_shutdown()
            raise
        self._ext = ext
        self._shader = shader
        self._capacity = self._max_sprites
        logger.debug(
            "UBR native ready max_sprites=%s sampler_loc=%s",
            self._max_sprites,
            shader.sampler_loc,
        )

    def shutdown(self) -> None:
        """Release native buffers and clear the module singleton if it is self."""
        global _ubr
        if self._ext is not None:
            with contextlib.suppress(Exception):
                self._ext.ubr_shutdown()
        self._ext = None
        self._shader = None
        self._capacity = 0
        if _ubr is self:
            _ubr = None

    def submit_frame(
        self,
        *,
        pos_xy: FrameArray,
        size_wh: FrameArray,
        origin_xy: FrameArray,
        rotation_deg: FrameArray,
        rgba: FrameArray,
        uv_rect: FrameArray,
        run_starts: FrameArray,
        run_counts: FrameArray,
        run_tex_ids: FrameArray,
        n_sprites: int,
        n_runs: int,
    ) -> None:
        """Submit one frame of sprite data to the native renderer.

        Args:
            pos_xy: Per-sprite positions, shape ``(n_sprites, 2)``.
            size_wh: Per-sprite sizes, shape ``(n_sprites, 2)``.
            origin_xy: Per-sprite rotation origins, shape ``(n_sprites, 2)``.
            rotation_deg: Per-sprite rotations in degrees, shape ``(n_sprites,)``.
            rgba: Per-sprite tint colors, uint8, shape ``(n_sprites, 4)``.
            uv_rect: Per-sprite UV rectangles, shape ``(n_sprites, 4)``.
            run_starts: Start index of each texture run.
            run_counts: Sprite count of each texture run.
            run_tex_ids: Texture id of each texture run.
            n_sprites: Number of sprites to draw.
            n_runs: Number of texture runs.

        Raises:
            RuntimeError: If the batch has not been initialized.
            ValueError: If counts exceed capacity or the supplied arrays.
        """
        if self._ext is None or self._shader is None:
            raise RuntimeError("UBR not initialized — call init() at startup")
        n = int(n_sprites)
        if n < 0 or n > self._capacity:
            raise ValueError("n_sprites must be between zero and the UBR capacity")
        if n == 0:
            return
        nr = int(n_runs)
        if nr <= 0 or nr > n:
            raise ValueError("n_runs must be between one and n_sprites")
        if any(
            array.shape[0] < n
            for array in (pos_xy, size_wh, origin_xy, rotation_deg, rgba, uv_rect)
        ):
            raise ValueError("sprite arrays are shorter than n_sprites")
        if any(array.shape[0] < nr for array in (run_starts, run_counts, run_tex_ids)):
            raise ValueError("texture-run arrays are shorter than n_runs")

        try:
            _prepare_shader(self._shader)
            self._ext.ubr_submit_frame(
                _frame_view(pos_xy, n, np.float32),
                _frame_view(size_wh, n, np.float32),
                _frame_view(origin_xy, n, np.float32),
                _frame_view(rotation_deg, n, np.float32),
                _frame_view(rgba, n, np.uint8),
                _frame_view(uv_rect, n, np.float32),
                _frame_view(run_starts, nr, np.int32),
                _frame_view(run_counts, nr, np.int32),
                _frame_view(run_tex_ids, nr, np.uint32),
                n,
                nr,
            )
        finally:
            rl.rlDisableShader()


_ubr: UnifiedBufferBatch | None = None


def get_unified_buffer_batch(max_sprites: int = MAX_SPRITES) -> UnifiedBufferBatch:
    """Return the module singleton batch, creating it on first use."""
    global _ubr
    if _ubr is None:
        _ubr = UnifiedBufferBatch(max_sprites=max_sprites)
    return _ubr


def reset_unified_buffer_batch() -> None:
    """Drop the singleton batch and shut it down if one exists."""
    global _ubr
    batch = _ubr
    _ubr = None
    if batch is not None:
        batch.shutdown()


__all__ = [
    "NativeBatchModule",
    "UnifiedBufferBatch",
    "get_unified_buffer_batch",
    "reset_unified_buffer_batch",
]
