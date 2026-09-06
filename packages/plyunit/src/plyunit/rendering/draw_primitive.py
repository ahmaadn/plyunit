"""Backend-agnostic primitive dispatcher + primitive item.

Lives in the engine so ``Renderer`` does not need to import integration
modules at load time. Raylib-specific batching stays in
``integrations/raylib/batching``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .enum import PrimitiveKind

if TYPE_CHECKING:
    from .queue import PrimitiveItem


def draw_primitive(canvas: Any, item: PrimitiveItem) -> None:
    """Draws a single ``PrimitiveItem`` onto ``canvas``.

    Args:
        canvas: Backend canvas providing the ``draw_*`` methods.
        item: The item to draw; its payload is unpacked as kwargs.
    """
    payload = item.payload
    match item.kind:
        case PrimitiveKind.PIXEL:
            canvas.draw_pixel(**payload)
        case PrimitiveKind.LINE:
            canvas.draw_line(**payload)
        case PrimitiveKind.CIRCLE:
            canvas.draw_circle(**payload)
        case PrimitiveKind.ELLIPSE:
            canvas.draw_ellipse(**payload)
        case PrimitiveKind.RING:
            canvas.draw_ring(**payload)
        case PrimitiveKind.RECTANGLE:
            canvas.draw_rectangle(**payload)
        case PrimitiveKind.TRIANGLE:
            canvas.draw_triangle(**payload)
        case PrimitiveKind.POLY:
            canvas.draw_poly(**payload)
        case PrimitiveKind.RECTANGLES:
            canvas.draw_rectangle_batch(**payload)
        case PrimitiveKind.CIRCLES:
            canvas.draw_circle_batch(**payload)
        case PrimitiveKind.LINES:
            canvas.draw_line_batch(**payload)
        case PrimitiveKind.TRIANGLES:
            canvas.draw_triangle_batch(**payload)


__all__ = ("draw_primitive",)
