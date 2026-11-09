"""ImGui port."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

type DrawCallback = Callable[[], None]
"""Type of argument-less callables that draw one ImGui panel."""


@runtime_checkable
class ImGuiPort(Protocol):
    """Immediate-mode UI port.

    Panels are plain callables registered via :meth:`add_draw` or
    :meth:`set_draw`; each :meth:`frame` call runs them between NewFrame
    and Render.
    """

    @property
    def active(self) -> bool:
        """``True`` while the UI is attached and able to draw."""
        ...

    def add_draw(self, callback: DrawCallback) -> None:
        """Register an additional panel callback (ignored if already added)."""
        ...

    def remove_draw(self, callback: DrawCallback) -> None:
        """Remove a registered panel callback (silent no-op if absent)."""
        ...

    def set_draw(self, callback: DrawCallback | None) -> None:
        """Replace all panel callbacks with one callback, or clear with ``None``."""
        ...

    def clear_draw(self) -> None:
        """Remove all panel callbacks."""
        ...

    def want_capture_mouse(self) -> bool:
        """Return ``True`` if the UI wants exclusive use of mouse input."""
        ...

    def want_capture_keyboard(self) -> bool:
        """Return ``True`` if the UI wants exclusive use of keyboard input."""
        ...

    def frame(self, dt: float | None = None) -> None:
        """Run one UI frame: NewFrame → draw callbacks → Render.

        Args:
            dt: Frame delta time in seconds. ``None`` lets the adapter
                pick a default.
        """
        ...


__all__ = ["DrawCallback", "ImGuiPort"]
