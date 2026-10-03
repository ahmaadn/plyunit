"""The center canvas area: where map editing happens.

:class:`EditorScreen` owns the doc tab bar and the canvas viewport — the
transparent window that lets raylib's render show through. Everything
here is a reserved seam; the map canvas, tile palette, and layer panel
will be added later.
"""

from __future__ import annotations

from typing import cast

from imgui_bundle import imgui

from scripts.services.file_tree import FileTree
from scripts.ui.layout import DockLayout, Rect
from scripts.ui.menus import MainMenuBar
from scripts.ui.panel import Panel
from scripts.ui.panels.explorer import ExplorerPanel
from scripts.ui.panels.status_bar import StatusBar
from scripts.ui.panels.toolbar import Toolbar


class EditorScreen(Panel):
    """The center canvas area of the editor.

    The shell computes the layout and hands this screen its center
    :class:`~scripts.ui.layout.Rect`; the canvas window itself is drawn
    transparently so the raylib render behind it stays visible. The
    shared app context and event bus are auto-attached by
    :meth:`Panel.__new__`; the layout and sub-panels are built in
    :meth:`__init__`.
    """

    def __init__(self) -> None:
        self.layout = DockLayout()
        self.menus = MainMenuBar(self.layout)
        self.toolbar = Toolbar(self.layout)
        self.explorer = ExplorerPanel()
        self.status = StatusBar()

    def sync(self):

        file_tree = cast(FileTree, self.one("@FileTree"))

        self.explorer.sync_project(file_tree)

    def draw(self) -> None:
        """Draw the center area: document tabs above the canvas.

        Args:
            rect: The full center rect computed by the shell's layout.
        """
        self.menus.draw()
        left, center, right = self.layout.compute()

        self.toolbar.draw()
        if self.layout.show_left:
            self.draw_left_sidebar(left)

        if self.layout.show_tabs:
            self._draw_tab_bar()

        self._draw_canvas(center)
        if self.layout.show_right:
            self.draw_right_sidebar(right)

        # Draw the sidebars' splitters last, above the panels.
        if self.layout.show_left:
            self.layout.draw_splitter("left", left, is_left=True)
        if self.layout.show_right:
            self.layout.draw_splitter("right", right, is_left=False)

        self.status.draw()

    def _draw_tab_bar(self) -> None:
        """Draw the document tab bar above the canvas (reserved seam)."""

    def _draw_canvas(self, rect: Rect) -> None:
        """Draw the transparent canvas viewport over the raylib render."""
        canvas = self.layout.viewport
        if canvas.width <= 0.0 or canvas.height <= 0.0:
            return

        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_bring_to_front_on_focus
            | imgui.WindowFlags_.no_nav_focus
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_background
        )
        imgui.set_next_window_pos(imgui.ImVec2(canvas.x, canvas.y))
        imgui.set_next_window_size(imgui.ImVec2(canvas.width, canvas.height))
        imgui.begin("##canvas", None, int(flags))
        imgui.end()

    def draw_left_sidebar(self, rect: Rect) -> None:
        """Draw the left sidebar: Explorer, Aset, and Setting tabs."""
        if not self.layout.begin_fixed("##sidebar_left", rect):
            imgui.end()
            return

        if imgui.begin_tab_bar("##left_tabs"):
            if imgui.begin_tab_item("Explorer")[0]:
                self.explorer.draw()
                imgui.end_tab_item()
            if imgui.begin_tab_item("Aset")[0]:
                imgui.end_tab_item()
            if imgui.begin_tab_item("Setting")[0]:
                imgui.end_tab_item()
            imgui.end_tab_bar()

        imgui.end()

    def draw_right_sidebar(self, rect: Rect) -> None:
        """Draw the right sidebar (reserved seam)."""
        if not self.layout.begin_fixed("##sidebar_right", rect):
            imgui.end()
            return
        imgui.end()


__all__ = ["EditorScreen"]
