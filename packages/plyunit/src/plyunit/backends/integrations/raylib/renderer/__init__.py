"""Raylib drawing-canvas factory and native sprite-batch implementation."""

from typing import cast

from plyunit.backends.ports.renderer import ICanvas2D

from . import canvas
from .ubr import UnifiedBufferBatch


def Canvas2D() -> ICanvas2D:
    """Return the module-backed raylib canvas implementing the drawing port.

    Returns:
        The raylib immediate-mode drawing surface. Resource arguments to this
        implementation are concrete handles from ``raylib.handler``.
    """
    return cast(ICanvas2D, canvas)


__all__ = ("Canvas2D", "UnifiedBufferBatch")
