"""Streaming texture via OpenGL PBO double-buffering (shared raylib context).

Typical usage (once the GL window/context exists)::

    Canvas.init_streaming()
    stream = Canvas.create_streaming_texture(640, 360, channels=4)
    stream.update(frame_bytes)
    canvas.draw_texture(texture=stream.texture, pos=(0, 0))
    Canvas.destroy_streaming_texture(stream)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pyray as pr
import raylib as rl

from .gl_ffi import flush_render_batch, get_gl_func, reset_gl_funcs

logger = logging.getLogger(__name__)

# OpenGL constants
GL_PIXEL_UNPACK_BUFFER = 0x88EC
GL_STREAM_DRAW = 0x88E0
GL_WRITE_ONLY = 0x88B9
GL_TEXTURE_2D = 0x0DE1
GL_RGBA = 0x1908
GL_RGB = 0x1907
GL_UNSIGNED_BYTE = 0x1401

_initialized = False


@dataclass
class StreamingTexture:
    """Texture backed by double-buffered PBOs for async pixel uploads."""

    texture: Any
    width: int
    height: int
    channels: int  # 3 = RGB, 4 = RGBA
    _pbo_ids: list[int] = field(default_factory=list)
    _current_pbo: int = 0
    _buffer_size: int = 0
    _alive: bool = True

    def __post_init__(self) -> None:
        """Derive the byte buffer size from width, height, and channels."""
        self._buffer_size = int(self.width) * int(self.height) * int(self.channels)

    @property
    def texture_id(self) -> int:
        """The underlying raylib GPU texture id."""
        return int(self.texture.id)

    def update(self, pixels: bytes | bytearray | memoryview) -> bool:
        """Upload a full frame. Returns False on size mismatch or GL failure.

        Note: double-buffering means new pixels typically appear one frame later.
        """
        return update_streaming_texture(self, pixels)

    def destroy(self) -> None:
        """Release the PBOs and the underlying texture."""
        destroy_streaming_texture(self)


def init_streaming() -> bool:
    """Load GL PBO entry points. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return True
    try:
        get_gl_func("glGenBuffers", "void(*)(int, unsigned int*)")
        get_gl_func("glDeleteBuffers", "void(*)(int, const unsigned int*)")
        get_gl_func("glBindBuffer", "void(*)(unsigned int, unsigned int)")
        get_gl_func(
            "glBufferData",
            "void(*)(unsigned int, long long, const void*, unsigned int)",
        )
        get_gl_func("glMapBuffer", "void*(*)(unsigned int, unsigned int)")
        get_gl_func("glUnmapBuffer", "unsigned char(*)(unsigned int)")
        get_gl_func("glBindTexture", "void(*)(unsigned int, unsigned int)")
        get_gl_func(
            "glTexSubImage2D",
            "void(*)(unsigned int, int, int, int, int, int, unsigned int, unsigned int, const void*)",  # noqa: E501
        )
        _initialized = True
        return True
    except RuntimeError as exc:
        logger.warning("PBO streaming init failed: %s", exc)
        reset_gl_funcs()
        _initialized = False
        return False


def reset_streaming() -> None:
    """Reset module state (tests / window recreate)."""
    global _initialized
    _initialized = False


def is_streaming_available() -> bool:
    """Return ``True`` if PBO entry points have been initialized."""
    return _initialized


def create_streaming_texture(
    width: int,
    height: int,
    *,
    channels: int = 4,
) -> StreamingTexture | None:
    """Create an empty GPU texture + two PBOs for streaming updates."""
    if channels not in (3, 4):
        raise ValueError("channels must be 3 (RGB) or 4 (RGBA)")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be > 0")
    if not _initialized and not init_streaming():
        return None

    flush_render_batch()

    gl_gen_buffers = get_gl_func("glGenBuffers", "void(*)(int, unsigned int*)")
    gl_bind_buffer = get_gl_func("glBindBuffer", "void(*)(unsigned int, unsigned int)")
    gl_buffer_data = get_gl_func(
        "glBufferData",
        "void(*)(unsigned int, long long, const void*, unsigned int)",
    )

    pixel_format = (
        rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8
        if channels == 4
        else rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8
    )
    image = pr.gen_image_color(width, height, pr.BLANK)
    if hasattr(image, "format"):
        image.format = pixel_format
    texture = pr.load_texture_from_image(image)
    pr.unload_image(image)
    if int(texture.id) == 0:
        logger.error("Failed to create streaming texture")
        return None

    buffer_size = width * height * channels
    pbo_ids = pr.ffi.new("unsigned int[2]")
    gl_gen_buffers(2, pbo_ids)
    for i in range(2):
        gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, pbo_ids[i])
        gl_buffer_data(GL_PIXEL_UNPACK_BUFFER, buffer_size, pr.ffi.NULL, GL_STREAM_DRAW)
    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, 0)

    return StreamingTexture(
        texture=texture,
        width=width,
        height=height,
        channels=channels,
        _pbo_ids=[int(pbo_ids[0]), int(pbo_ids[1])],
        _current_pbo=0,
        _buffer_size=buffer_size,
    )


def update_streaming_texture(
    streaming: StreamingTexture,
    pixels: bytes | bytearray | memoryview,
) -> bool:
    """Async-ish full-frame upload via PBO ping-pong."""
    if not _initialized or streaming is None or not streaming._alive:
        return False

    data = pixels if isinstance(pixels, (bytes, bytearray)) else bytes(pixels)
    if len(data) != streaming._buffer_size:
        logger.warning(
            "Streaming pixel size mismatch: expected %s, got %s",
            streaming._buffer_size,
            len(data),
        )
        return False

    flush_render_batch()

    gl_bind_buffer = get_gl_func("glBindBuffer", "void(*)(unsigned int, unsigned int)")
    gl_buffer_data = get_gl_func(
        "glBufferData",
        "void(*)(unsigned int, long long, const void*, unsigned int)",
    )
    gl_map_buffer = get_gl_func("glMapBuffer", "void*(*)(unsigned int, unsigned int)")
    gl_unmap_buffer = get_gl_func("glUnmapBuffer", "unsigned char(*)(unsigned int)")
    gl_bind_texture = get_gl_func(
        "glBindTexture", "void(*)(unsigned int, unsigned int)"
    )
    gl_tex_sub_image_2d = get_gl_func(
        "glTexSubImage2D",
        "void(*)(unsigned int, int, int, int, int, int, unsigned int, unsigned int, const void*)",  # noqa: E501
    )

    next_pbo = 1 - streaming._current_pbo
    current_pbo = streaming._current_pbo
    gl_format = GL_RGBA if streaming.channels == 4 else GL_RGB

    gl_bind_texture(GL_TEXTURE_2D, streaming.texture_id)

    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, streaming._pbo_ids[next_pbo])
    gl_tex_sub_image_2d(
        GL_TEXTURE_2D,
        0,
        0,
        0,
        streaming.width,
        streaming.height,
        gl_format,
        GL_UNSIGNED_BYTE,
        pr.ffi.NULL,
    )

    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, streaming._pbo_ids[current_pbo])
    gl_buffer_data(
        GL_PIXEL_UNPACK_BUFFER,
        streaming._buffer_size,
        pr.ffi.NULL,
        GL_STREAM_DRAW,
    )
    ptr = gl_map_buffer(GL_PIXEL_UNPACK_BUFFER, GL_WRITE_ONLY)
    if ptr == pr.ffi.NULL:
        gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, 0)
        return False

    pr.ffi.memmove(ptr, data, streaming._buffer_size)
    gl_unmap_buffer(GL_PIXEL_UNPACK_BUFFER)
    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, 0)

    streaming._current_pbo = next_pbo
    return True


def destroy_streaming_texture(streaming: StreamingTexture | None) -> None:
    """Release PBOs and the underlying raylib texture."""
    if not _initialized or streaming is None or not streaming._alive:
        return

    flush_render_batch()
    gl_delete_buffers = get_gl_func(
        "glDeleteBuffers", "void(*)(int, const unsigned int*)"
    )
    pbo_ids = pr.ffi.new("unsigned int[2]", streaming._pbo_ids)
    gl_delete_buffers(2, pbo_ids)
    if streaming.texture is not None and int(streaming.texture.id) != 0:
        pr.unload_texture(streaming.texture)
    streaming._alive = False
    streaming._pbo_ids = []


__all__ = [
    "StreamingTexture",
    "create_streaming_texture",
    "destroy_streaming_texture",
    "init_streaming",
    "is_streaming_available",
    "reset_streaming",
    "update_streaming_texture",
]
