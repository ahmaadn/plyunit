"""Rendering subpackage: queue, passes, renderer, and draw-call types.

Contains the rendering pipeline, render state, draw queue, batch system,
and the renderer facades (debug, particles, tilemap, UI) for the raylib
based 2D engine.
"""

from .draw_scope import DrawScope
from .enum import BlendMode, Layer, PrimitiveKind, RenderKind
from .frame_buffer import MAX_SPRITES, FrameBuffer
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
    "MAX_SPRITES",
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
