from __future__ import annotations

from typing import TYPE_CHECKING

from imgui_bundle import imgui

if TYPE_CHECKING:
    from scripts.ui.layout import DockLayout


class Toolbar:
    """Draws the (currently empty) toolbar strip below the menu bar.

    Args:
        layout: The dock layout that computes the toolbar rect.
    """

    def __init__(self, layout: DockLayout) -> None:
        self._layout = layout

    def draw(self) -> None:
        """Draw the toolbar strip."""
        rect = self._layout.toolbar_rect()
        if not self._layout.begin_fixed("##toolbar", rect):
            imgui.end()
            return
        imgui.end()


__all__ = ["Toolbar"]
