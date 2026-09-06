"""Raylib adapter: native UBR expand/upload + raw glDrawElements.

Shader/MVP setup cached in Python (cffi Matrix). Draw uses raw GL because
``rlDrawVertexArrayElements`` does not produce pixels for custom VAOs
on raylib-python-cffi (verified).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import numpy as np
import pyray as pr
import raylib as rl

from plyunit.backends.interfaces import IUnifiedBufferBatch
from plyunit.rendering.frame_buffer import MAX_SPRITES

logger = logging.getLogger(__name__)


_GL_TEXTURE0 = 0x84C0
_GL_TEXTURE_2D = 0x0DE1
_GL_ELEMENT_ARRAY_BUFFER = 0x8893
_GL_TRIANGLES = 0x0004
_GL_UNSIGNED_INT = 0x1405


def _load_native() -> Any:
    """Import the native batch C-extension or raise a helpful RuntimeError."""
    try:
        from plyunit import _plyunit_batch as ext  # type: ignore[attr-defined]

        return ext
    except Exception as exc:
        raise RuntimeError(
            "C-extension plyunit._plyunit_batch is required for sprite rendering "
            "(no Python draw path). Reinstall with a C compiler available:\n"
            "  uv sync --reinstall-package plyunit-native\n"
            "  cd packages/plyunit-native && "
            "python setup.py build_ext --inplace --compiler=mingw32\n"
            "See also: ./init.sh and ./verify.sh in the repository root."
        ) from exc


def _gl_addr(rl: Any, ffi: Any, name: str) -> int:
    """Resolve a GL function pointer address via rlGetProcAddress."""
    raw = rl.rlGetProcAddress(name.encode("utf-8"))
    if raw is None or raw == ffi.NULL:
        raise RuntimeError(f"glGetProcAddress failed for {name}")
    return int(ffi.cast("uintptr_t", raw))


def _rl_func(lib, ffi, name):
    """Return the address of an rlgl symbol as an int."""
    fn = getattr(lib, name, None)
    if fn is None:
        raise AttributeError(f"rlgl symbol missing: {name}")
    return int(ffi.cast("uintptr_t", fn))


def _bind_dispatch(ext: Any, *, sampler_loc: int) -> None:
    """Pass rlgl/GL function addresses and constants to the native module."""

    lib = rl.rl
    ffi = rl.ffi

    dispatch = {
        "rl_load_vertex_array": _rl_func(lib, ffi, "rlLoadVertexArray"),
        "rl_enable_vertex_array": _rl_func(lib, ffi, "rlEnableVertexArray"),
        "rl_disable_vertex_array": _rl_func(lib, ffi, "rlDisableVertexArray"),
        "rl_unload_vertex_array": _rl_func(lib, ffi, "rlUnloadVertexArray"),
        "rl_load_vertex_buffer": _rl_func(lib, ffi, "rlLoadVertexBuffer"),
        "rl_load_vertex_buffer_element": _rl_func(
            lib, ffi, "rlLoadVertexBufferElement"
        ),
        "rl_update_vertex_buffer": _rl_func(lib, ffi, "rlUpdateVertexBuffer"),
        "rl_unload_vertex_buffer": _rl_func(lib, ffi, "rlUnloadVertexBuffer"),
        "rl_set_vertex_attribute": _rl_func(lib, ffi, "rlSetVertexAttribute"),
        "rl_enable_vertex_attribute": _rl_func(lib, ffi, "rlEnableVertexAttribute"),
        "gl_bind_vertex_array": _gl_addr(lib, ffi, "glBindVertexArray"),
        "gl_bind_buffer": _gl_addr(lib, ffi, "glBindBuffer"),
        "gl_active_texture": _gl_addr(lib, ffi, "glActiveTexture"),
        "gl_bind_texture": _gl_addr(lib, ffi, "glBindTexture"),
        "gl_draw_elements": _gl_addr(lib, ffi, "glDrawElements"),
        "gl_uniform1i": _gl_addr(lib, ffi, "glUniform1i"),
        "rl_float": int(pr.RL_FLOAT),
        "rl_unsigned_byte": int(pr.RL_UNSIGNED_BYTE),
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


def _ensure_contig(arr: np.ndarray, dtype: np.dtype) -> np.ndarray:
    """Return arr if already C-contiguous matching dtype; else one copy."""
    if arr.dtype == dtype and arr.flags.c_contiguous:
        return arr
    return np.ascontiguousarray(arr, dtype=dtype)


class UnifiedBufferBatch(IUnifiedBufferBatch):
    """Native expand/upload/glDraw; Python prepares raylib default shader."""

    def __init__(self, max_sprites: int = MAX_SPRITES) -> None:
        """Initialize bookkeeping; native resources are created lazily by init().

        Args:
            max_sprites: Maximum sprites per frame (batch capacity).
        """
        self._max_sprites = max_sprites
        self._capacity = 0
        self._ext: Any | None = None
        self._ready = False
        self._sampler_loc = -1
        # Cached prepare (resolved once after GL context exists).
        self._rl: Any | None = None
        self._ffi: Any | None = None
        self._shader_id = 0
        self._loc_mvp = -1
        self._loc_diff = -1
        self._white: Any | None = None
        self._uniform_vec4 = 3
        self._prep_ready = False

    @property
    def capacity(self) -> int:
        """Current sprite batch capacity (0 until init() succeeds)."""
        return self._capacity

    def init(self, max_sprites: int | None = None) -> None:
        """Resolve shader uniforms, bind the native dispatch, and allocate buffers.

        Args:
            max_sprites: Optional new maximum sprite count.

        Raises:
            RuntimeError: If the native module fails to initialize.
        """
        if max_sprites is not None:
            self._max_sprites = int(max_sprites)
        if self._ready:
            return
        ext = _load_native()

        self._rl = rl.rl
        self._ffi = rl.ffi
        self._uniform_vec4 = int(rl.SHADER_UNIFORM_VEC4)

        sh = rl.rlGetShaderIdDefault()
        self._shader_id = int(sh)
        get_loc = rl.rlGetProcAddress(b"glGetUniformLocation")
        use_prog = rl.rlGetProcAddress(b"glUseProgram")
        if get_loc and use_prog:
            glGetUniformLocation = self._ffi.cast(
                "int(*)(unsigned int, const char *)", get_loc
            )
            glUseProgram = self._ffi.cast("void(*)(unsigned int)", use_prog)
            glUseProgram(sh)
            self._sampler_loc = int(glGetUniformLocation(sh, b"texture0"))
            glUseProgram(0)
        else:
            locs = self._ffi.unpack(rl.rlGetShaderLocsDefault(), 32)
            self._sampler_loc = int(locs[int(pr.SHADER_LOC_MAP_ALBEDO)])

        locs = self._ffi.unpack(rl.rlGetShaderLocsDefault(), 32)
        self._loc_mvp = int(locs[int(pr.SHADER_LOC_MATRIX_MVP)])
        self._loc_diff = int(locs[int(pr.SHADER_LOC_COLOR_DIFFUSE)])
        self._white = self._ffi.new("float[4]", [1.0, 1.0, 1.0, 1.0])
        self._prep_ready = True

        _bind_dispatch(ext, sampler_loc=self._sampler_loc)
        ext.ubr_init(self._max_sprites)
        if not ext.ubr_is_ready():
            raise RuntimeError("ubr_init reported not ready")
        self._ext = ext
        self._capacity = self._max_sprites
        self._ready = True
        logger.debug(
            "UBR native ready max_sprites=%s sampler_loc=%s",
            self._max_sprites,
            self._sampler_loc,
        )

    def shutdown(self) -> None:
        """Release native buffers and clear the module singleton if it is self."""
        global _ubr
        if self._ext is not None:
            with contextlib.suppress(Exception):
                self._ext.ubr_shutdown()
        self._ext = None
        self._ready = False
        self._capacity = 0
        self._prep_ready = False
        self._rl = None
        self._ffi = None
        self._white = None
        if _ubr is self:
            _ubr = None

    def _prepare_shader(self) -> Any:
        """Flush raylib batch; bind default shader + MVP (cached locs)."""
        rl = self._rl
        assert rl is not None
        rl.rlDrawRenderBatchActive()
        rl.rlEnableShader(self._shader_id)
        mvp = rl.MatrixMultiply(rl.rlGetMatrixModelview(), rl.rlGetMatrixProjection())
        if self._loc_mvp >= 0:
            rl.rlSetUniformMatrix(self._loc_mvp, mvp)
        if self._loc_diff >= 0 and self._white is not None:
            rl.rlSetUniform(self._loc_diff, self._white, self._uniform_vec4, 1)
        rl.rlDisableBackfaceCulling()
        rl.rlEnableColorBlend()
        return rl

    def submit_frame(
        self,
        *,
        pos_xy: np.ndarray,
        size_wh: np.ndarray,
        origin_xy: np.ndarray,
        rotation_deg: np.ndarray,
        rgba: np.ndarray,
        uv_rect: np.ndarray,
        run_starts: np.ndarray,
        run_counts: np.ndarray,
        run_tex_ids: np.ndarray,
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
        """
        if not self._ready or self._ext is None:
            raise RuntimeError("UBR not initialized — call init() at startup")
        n = int(n_sprites)
        if n <= 0:
            return

        # Prefer zero-copy when caller already passed C-contiguous views.
        pos = _ensure_contig(pos_xy if pos_xy.shape[0] == n else pos_xy[:n], np.float32)
        size = _ensure_contig(
            size_wh if size_wh.shape[0] == n else size_wh[:n], np.float32
        )
        origin = _ensure_contig(
            origin_xy if origin_xy.shape[0] == n else origin_xy[:n], np.float32
        )
        rot = _ensure_contig(
            rotation_deg if rotation_deg.shape[0] == n else rotation_deg[:n],
            np.float32,
        )
        col = _ensure_contig(rgba if rgba.shape[0] == n else rgba[:n], np.uint8)
        uv = _ensure_contig(
            uv_rect if uv_rect.shape[0] == n else uv_rect[:n], np.float32
        )
        nr = int(n_runs)
        if nr > 0:
            starts = _ensure_contig(
                run_starts if run_starts.shape[0] == nr else run_starts[:nr],
                np.int32,
            )
            counts = _ensure_contig(
                run_counts if run_counts.shape[0] == nr else run_counts[:nr],
                np.int32,
            )
            tex = _ensure_contig(
                run_tex_ids if run_tex_ids.shape[0] == nr else run_tex_ids[:nr],
                np.uint32,
            )
        else:
            starts = np.empty(0, dtype=np.int32)
            counts = np.empty(0, dtype=np.int32)
            tex = np.empty(0, dtype=np.uint32)

        rl = self._prepare_shader() if self._prep_ready else _prepare_fallback()
        try:
            self._ext.ubr_submit_frame(
                pos, size, origin, rot, col, uv, starts, counts, tex, n, nr
            )
        finally:
            rl.rlDisableShader()


def _prepare_fallback() -> Any:
    """One-shot prepare if init cache missing (should not happen in prod)."""

    lib = rl.rl
    ffi = rl.ffi

    lib.rlDrawRenderBatchActive()
    shader = lib.rlGetShaderIdDefault()
    locs = ffi.unpack(lib.rlGetShaderLocsDefault(), 32)
    lib.rlEnableShader(shader)
    mvp = lib.MatrixMultiply(lib.rlGetMatrixModelview(), lib.rlGetMatrixProjection())
    loc_mvp = int(locs[int(pr.SHADER_LOC_MATRIX_MVP)])
    loc_diff = int(locs[int(pr.SHADER_LOC_COLOR_DIFFUSE)])
    if loc_mvp >= 0:
        lib.rlSetUniformMatrix(loc_mvp, mvp)
    if loc_diff >= 0:
        white = ffi.new("float[4]", [1.0, 1.0, 1.0, 1.0])
        lib.rlSetUniform(loc_diff, white, int(rl.SHADER_UNIFORM_VEC4), 1)
    lib.rlDisableBackfaceCulling()
    lib.rlEnableColorBlend()
    return rl


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
    "UnifiedBufferBatch",
    "get_unified_buffer_batch",
    "reset_unified_buffer_batch",
]
