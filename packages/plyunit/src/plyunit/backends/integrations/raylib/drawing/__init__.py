"""raylib drawing backend subpackage (Canvas + stencil + streaming-texture).

Re-exports the :class:`Canvas` class, color/vector utilities, the stencil
system, and streaming-texture support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import canvas
from .canvas import color, rgb, rgba, to_color, to_rect, to_vec2

if TYPE_CHECKING:
    from plyunit.backends.interfaces.i_renderer import ICanvas2D, IUnifiedBufferBatch


from .stencil import (
    begin_stencil_mask,
    end_stencil_mask,
    end_stencil_mask_inverse,
    end_stencil_mode,
    init_stencil,
    is_stencil_active,
    is_stencil_available,
    reset_stencil,
)
from .streaming_texture import (
    StreamingTexture,
    create_streaming_texture,
    destroy_streaming_texture,
    init_streaming,
    is_streaming_available,
    reset_streaming,
    update_streaming_texture,
)
from .ubr import (
    UnifiedBufferBatch,
    get_unified_buffer_batch,
    reset_unified_buffer_batch,
)


def Canvas() -> ICanvas2D:
    """Return the active :class:`Canvas` host instance as :class:`ICanvas2D`."""
    return canvas


def get_canvas() -> ICanvas2D:
    """Factory: the active :class:`Canvas` host instance (:class:`ICanvas2D`).

    Uses :meth:`Canvas.get_instance` so the host singleton stays consistent
    (the ``Canvas`` class has a ``__call__`` that returns itself).
    """
    return canvas


def BatchingBackend() -> IUnifiedBufferBatch:
    """Return the active unified buffer batch as :class:`IUnifiedBufferBatch`."""
    return get_unified_buffer_batch()


def get_batching_backend() -> IUnifiedBufferBatch:
    """Return the active unified buffer batch as :class:`IUnifiedBufferBatch`."""
    return get_unified_buffer_batch()


__all__ = [
    "BatchingBackend",
    "Canvas",
    "StreamingTexture",
    "UnifiedBufferBatch",
    "begin_stencil_mask",
    "color",
    "create_streaming_texture",
    "destroy_streaming_texture",
    "end_stencil_mask",
    "end_stencil_mask_inverse",
    "end_stencil_mode",
    "get_batching_backend",
    "get_canvas",
    "get_unified_buffer_batch",
    "init_stencil",
    "init_streaming",
    "is_stencil_active",
    "is_stencil_available",
    "is_streaming_available",
    "reset_stencil",
    "reset_streaming",
    "reset_unified_buffer_batch",
    "rgb",
    "rgba",
    "to_color",
    "to_rect",
    "to_vec2",
    "update_streaming_texture",
]
