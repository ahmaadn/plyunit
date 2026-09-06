"""Raylib core integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .camera2d import Camera2D
from .window import Window

if TYPE_CHECKING:
    from plyunit.backends.interfaces.i_renderer import IWindow


def get_window() -> IWindow:
    """Build the active window service."""
    return Window()


__all__ = ("Camera2D", "Window", "get_window")
