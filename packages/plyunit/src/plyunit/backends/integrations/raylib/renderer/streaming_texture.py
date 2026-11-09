"""Upload pixel frames with double-buffered OpenGL pixel-unpack buffers.

Use these functions only while the raylib window's graphics context is alive.
The concrete resource handle lives in the backend's ``handler`` module.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import pyray as pr
import raylib as rl

from plyunit.backends.ports.handler import PixelBuffer

from ..handler import Image, StreamingTexture, Texture2D
from .gl_ffi import (
    NULL_POINTER,
    copy_to_native,
    flush_render_batch,
    get_gl_func,
    get_gl_integer,
    is_null,
    new_uint_buffer,
    reset_gl_funcs,
    to_int,
)

logger = logging.getLogger(__name__)

GL_PIXEL_UNPACK_BUFFER = 0x88EC
GL_PIXEL_UNPACK_BUFFER_BINDING = 0x88EF
GL_STREAM_DRAW = 0x88E0
GL_WRITE_ONLY = 0x88B9
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_BINDING_2D = 0x8069
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_RGBA = 0x1908
GL_RGB = 0x1907
GL_UNSIGNED_BYTE = 0x1401

_PBO_COUNT = 2
_CHANNELS_RGB = 3
_CHANNELS_RGBA = 4
_VALID_CHANNELS = (_CHANNELS_RGB, _CHANNELS_RGBA)

_SIG_GEN_BUFFERS = "void(*)(int, unsigned int*)"
_SIG_DELETE_BUFFERS = "void(*)(int, const unsigned int*)"
_SIG_BIND_BUFFER = "void(*)(unsigned int, unsigned int)"
_SIG_BUFFER_DATA = "void(*)(unsigned int, long long, const void*, unsigned int)"
_SIG_MAP_BUFFER = "void*(*)(unsigned int, unsigned int)"
_SIG_UNMAP_BUFFER = "unsigned char(*)(unsigned int)"
_SIG_BIND_TEXTURE = "void(*)(unsigned int, unsigned int)"
_SIG_PIXEL_STORE = "void(*)(unsigned int, int)"
_SIG_GET_INTEGER = "void(*)(unsigned int, int*)"
_SIG_TEX_SUB_IMAGE_2D = (
    "void(*)(unsigned int, int, int, int, int, int, "
    "unsigned int, unsigned int, const void*)"
)

_initialized = False


def init_streaming() -> bool:
    """Resolve the OpenGL functions required for pixel streaming.

    Returns:
        Whether all required entry points are available.
    """
    global _initialized
    if _initialized:
        return True
    try:
        get_gl_func("glGenBuffers", _SIG_GEN_BUFFERS)
        get_gl_func("glDeleteBuffers", _SIG_DELETE_BUFFERS)
        get_gl_func("glBindBuffer", _SIG_BIND_BUFFER)
        get_gl_func("glBufferData", _SIG_BUFFER_DATA)
        get_gl_func("glMapBuffer", _SIG_MAP_BUFFER)
        get_gl_func("glUnmapBuffer", _SIG_UNMAP_BUFFER)
        get_gl_func("glBindTexture", _SIG_BIND_TEXTURE)
        get_gl_func("glTexSubImage2D", _SIG_TEX_SUB_IMAGE_2D)
        get_gl_func("glPixelStorei", _SIG_PIXEL_STORE)
        get_gl_func("glGetIntegerv", _SIG_GET_INTEGER)
    except RuntimeError as exc:
        logger.warning("PBO streaming init failed: %s", exc)
        _initialized = False
        return False
    _initialized = True
    return True


def reset_streaming() -> None:
    """Clear cached entry points before using a recreated graphics context.

    Destroy all live handles before closing their original context. Resetting
    availability alone does not prevent cleanup while that context is alive.
    """
    global _initialized
    _initialized = False
    reset_gl_funcs()


def is_streaming_available() -> bool:
    """Return whether pixel-streaming entry points have been initialized."""
    return _initialized


def _validate_stream_args(width: int, height: int, channels: int) -> None:
    """Reject unsupported pixel formats and nonpositive sizes."""
    if channels not in _VALID_CHANNELS:
        raise ValueError("channels must be 3 (RGB) or 4 (RGBA)")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be > 0")


def _load_blank_texture(width: int, height: int, channels: int) -> Texture2D | None:
    """Upload blank pixels in the requested format and release the CPU image."""
    pixel_format = (
        rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8A8
        if channels == _CHANNELS_RGBA
        else rl.PIXELFORMAT_UNCOMPRESSED_R8G8B8
    )
    image = Image(pr.gen_image_color(width, height, pr.BLANK))
    try:
        pr.image_format(image.raw_image, pixel_format)
        raw = pr.load_texture_from_image(image.raw_image)
    finally:
        pr.unload_image(image.raw_image)
    if int(raw.id) == 0:
        logger.error("Failed to create streaming texture")
        return None
    return Texture2D.from_raw(raw)


def create_streaming_texture(
    width: int,
    height: int,
    *,
    channels: int = 4,
) -> StreamingTexture | None:
    """Allocate a texture and two pixel-unpack buffers in the current context.

    Args:
        width: Texture width in pixels.
        height: Texture height in pixels.
        channels: Channels per pixel, either three or four.

    Returns:
        A concrete backend handle, or ``None`` if allocation fails.

    Raises:
        ValueError: If the channel count or dimensions are unsupported.
    """
    _validate_stream_args(width, height, channels)
    if not _initialized and not init_streaming():
        return None

    flush_render_batch()
    texture = _load_blank_texture(width, height, channels)
    if texture is None:
        return None

    pbo_names = None
    previous_buffer = None
    gl_bind_buffer = None
    try:
        gl_bind_buffer = get_gl_func("glBindBuffer", _SIG_BIND_BUFFER)
        previous_buffer = get_gl_integer(GL_PIXEL_UNPACK_BUFFER_BINDING)
        gl_gen_buffers = get_gl_func("glGenBuffers", _SIG_GEN_BUFFERS)
        gl_buffer_data = get_gl_func("glBufferData", _SIG_BUFFER_DATA)
        pbo_names = new_uint_buffer(_PBO_COUNT)
        gl_gen_buffers(_PBO_COUNT, pbo_names)
        pbo_ids = [int(pbo_names[i]) for i in range(_PBO_COUNT)]
        if any(name == 0 for name in pbo_ids):
            raise RuntimeError("OpenGL did not allocate both pixel-unpack buffers")
        for name in pbo_ids:
            gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, name)
            gl_buffer_data(
                GL_PIXEL_UNPACK_BUFFER,
                width * height * channels,
                NULL_POINTER,
                GL_STREAM_DRAW,
            )
    except Exception:
        logger.warning("Failed to allocate streaming buffers", exc_info=True)
        try:
            if pbo_names is not None:
                allocated = [
                    int(pbo_names[i]) for i in range(_PBO_COUNT) if pbo_names[i]
                ]
                if allocated:
                    get_gl_func("glDeleteBuffers", _SIG_DELETE_BUFFERS)(
                        len(allocated), new_uint_buffer(len(allocated), allocated)
                    )
        finally:
            pr.unload_texture(texture.raw_texture)
        return None
    finally:
        if gl_bind_buffer is not None and previous_buffer is not None:
            gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, previous_buffer)

    # The stream owns this texture; its exposed attachment must not be adopted
    # by Assets and unloaded independently of the stream.
    texture = replace(texture, _owns_texture=False)
    return StreamingTexture(texture, width, height, channels, pbo_ids)


def _queue_texture_upload(streaming: StreamingTexture, pbo: int) -> None:
    """Copy a filled buffer into the texture without changing unpack alignment."""
    gl_bind_buffer = get_gl_func("glBindBuffer", _SIG_BIND_BUFFER)
    gl_bind_texture = get_gl_func("glBindTexture", _SIG_BIND_TEXTURE)
    gl_pixel_store = get_gl_func("glPixelStorei", _SIG_PIXEL_STORE)
    gl_tex_sub_image_2d = get_gl_func("glTexSubImage2D", _SIG_TEX_SUB_IMAGE_2D)
    gl_format = GL_RGBA if streaming.channels == _CHANNELS_RGBA else GL_RGB
    previous_alignment = get_gl_integer(GL_UNPACK_ALIGNMENT)

    gl_bind_texture(GL_TEXTURE_2D, streaming.texture_id)
    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, pbo)
    gl_pixel_store(GL_UNPACK_ALIGNMENT, 1)
    try:
        gl_tex_sub_image_2d(
            GL_TEXTURE_2D,
            0,
            0,
            0,
            streaming.width,
            streaming.height,
            gl_format,
            GL_UNSIGNED_BYTE,
            NULL_POINTER,
        )
    finally:
        gl_pixel_store(GL_UNPACK_ALIGNMENT, previous_alignment)


def _fill_pbo(streaming: StreamingTexture, pbo: int, data: PixelBuffer) -> bool:
    """Orphan and fill a buffer, rejecting failed mapping or corrupted unmapping."""
    gl_bind_buffer = get_gl_func("glBindBuffer", _SIG_BIND_BUFFER)
    gl_buffer_data = get_gl_func("glBufferData", _SIG_BUFFER_DATA)
    gl_map_buffer = get_gl_func("glMapBuffer", _SIG_MAP_BUFFER)
    gl_unmap_buffer = get_gl_func("glUnmapBuffer", _SIG_UNMAP_BUFFER)

    gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, pbo)
    try:
        gl_buffer_data(
            GL_PIXEL_UNPACK_BUFFER, streaming.buffer_size, NULL_POINTER, GL_STREAM_DRAW
        )
        pointer = gl_map_buffer(GL_PIXEL_UNPACK_BUFFER, GL_WRITE_ONLY)
        if is_null(pointer):
            logger.warning("Failed to map a streaming pixel-unpack buffer")
            return False
        try:
            copy_to_native(pointer, data, streaming.buffer_size)
        finally:
            unmapped = to_int(gl_unmap_buffer(GL_PIXEL_UNPACK_BUFFER))
        if not unmapped:
            logger.warning("Streaming pixel-unpack buffer data was corrupted")
            return False
        return True
    finally:
        gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, 0)


def update_streaming_texture(streaming: StreamingTexture, pixels: PixelBuffer) -> bool:
    """Upload the first frame immediately, then use one-frame PBO pipelining.

    Args:
        streaming: Live handle created by this backend.
        pixels: A complete RGB or RGBA frame.

    Returns:
        Whether the buffer was filled and queued successfully.
    """
    if not _initialized or not streaming.alive:
        return False
    received = memoryview(pixels).nbytes
    if received != streaming.buffer_size:
        logger.warning(
            "Streaming pixel size mismatch: expected %s, got %s",
            streaming.buffer_size,
            received,
        )
        return False

    flush_render_batch()
    gl_bind_buffer = get_gl_func("glBindBuffer", _SIG_BIND_BUFFER)
    gl_bind_texture = get_gl_func("glBindTexture", _SIG_BIND_TEXTURE)
    previous_buffer = get_gl_integer(GL_PIXEL_UNPACK_BUFFER_BINDING)
    previous_texture = get_gl_integer(GL_TEXTURE_BINDING_2D)
    next_pbo = 1 - streaming.current_pbo
    try:
        if streaming._primed:
            _queue_texture_upload(streaming, streaming.pbo_ids[next_pbo])
        if not _fill_pbo(streaming, streaming.pbo_ids[streaming.current_pbo], pixels):
            return False
        if not streaming._primed:
            _queue_texture_upload(streaming, streaming.pbo_ids[streaming.current_pbo])
            streaming._primed = True
        streaming.current_pbo = next_pbo
        return True
    except Exception:
        logger.warning("Failed to update streaming pixels", exc_info=True)
        return False
    finally:
        gl_bind_buffer(GL_PIXEL_UNPACK_BUFFER, previous_buffer)
        gl_bind_texture(GL_TEXTURE_2D, previous_texture)


def destroy_streaming_texture(streaming: StreamingTexture | None) -> None:
    """Release both resource types once, even after streaming availability resets.

    Args:
        streaming: Handle to release while its original context is still alive.
    """
    if streaming is None or not streaming.alive:
        return

    flush_render_batch()
    try:
        if streaming.pbo_ids:
            get_gl_func("glDeleteBuffers", _SIG_DELETE_BUFFERS)(
                len(streaming.pbo_ids),
                new_uint_buffer(len(streaming.pbo_ids), streaming.pbo_ids),
            )
    finally:
        try:
            if streaming.texture_id != 0:
                pr.unload_texture(streaming.texture.raw_texture)
        finally:
            streaming.alive = False
            streaming.pbo_ids = []
            streaming._primed = False


__all__ = [
    "create_streaming_texture",
    "destroy_streaming_texture",
    "init_streaming",
    "is_streaming_available",
    "reset_streaming",
    "update_streaming_texture",
]
