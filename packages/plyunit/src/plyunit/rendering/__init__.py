"""Backend-neutral rendering pipeline, frame buffers, and render-state types.

Canvas and native batch adapters are injected through ports. Resource handles
remain opaque throughout submission, sorting, and pass dispatch.
"""

from .draw_scope import DrawScope
from .enum import BlendMode, Layer, PrimitiveKind, RenderKind
from .frame_buffer import FrameBuffer
from .render_context import RenderContext
from .render_state import (
    DEFAULT_RENDER_STATE,
    RenderPass,
    RenderState,
    RenderStateCache,
)
from .renderer import Renderer

__all__ = [
    "DEFAULT_RENDER_STATE",
    "BlendMode",
    "DrawScope",
    "FrameBuffer",
    "Layer",
    "PrimitiveKind",
    "RenderContext",
    "RenderKind",
    "RenderPass",
    "RenderState",
    "RenderStateCache",
    "Renderer",
]
