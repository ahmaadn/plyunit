"""The center canvas area: where map editing happens.

:class:`EditorScreen` owns the doc tab bar and the canvas viewport — a
bare raylib area with no ImGui window covering it, so the render shows
through and mouse hit-testing does not capture input. Everything here is
a reserved seam; the map canvas, tile palette, and layer panel will be
added later.
"""

from __future__ import annotations

from imgui_bundle import imgui

from scripts.app import events
from scripts.ui import icons
from scripts.ui.layout import TAB_BAR_HEIGHT, DockLayout, Rect
from scripts.ui.menus import MainMenuBar
from scripts.ui.panel import Panel
from scripts.ui.panels.explorer import ExplorerPanel
from scripts.ui.panels.status_bar import StatusBar
from scripts.ui.panels.tabs import TabBar
from scripts.ui.panels.toolbar import Toolbar
from scripts.ui.text_utils import set_tooltip


class EditorScreen(Panel):
    """The center canvas area of the editor.

    The shell computes the layout and hands this screen its center
    :class:`~scripts.ui.layout.Rect`; the canvas area is left free of
    ImGui windows so the raylib render behind it stays visible and does
    not capture mouse input. The shared app context and event bus are
    auto-attached by :meth:`Panel.__new__`; the layout and sub-panels
    are built in :meth:`__init__`.
    """

    def __init__(self) -> None:
        """Build the dock layout and the chrome panels it hosts."""
        self.layout = DockLayout()
        self.menus = MainMenuBar(self.layout)
        self.toolbar = Toolbar(self.layout)
        self.explorer = ExplorerPanel()
        self.status = StatusBar()
        self.tab_bar = TabBar()

    def sync(self):
        """Rebind sub-panels to current engine services.

        Must be called after a project scan produces a file tree so the
        explorer panel picks it up.
        """
        self.explorer.sync_project(self.one("@FileTree"))

    def draw(self) -> None:
        """Draw the whole screen: menus, sidebars, tab bar, and status bar."""
        self.menus.draw()
        left, center, right = self.layout.compute()

        self.toolbar.draw()
        if self.layout.show_left:
            self.draw_left_sidebar(left)

        if self.layout.show_tabs:
            self._draw_tab_bar(center)

        if self.layout.show_right:
            self.draw_right_sidebar(right)

        # Draw the sidebars' splitters last, above the panels.
        if self.layout.show_left:
            self.layout.draw_splitter("left", left, is_left=True)
        if self.layout.show_right:
            self.layout.draw_splitter("right", right, is_left=False)

        self.status.draw()

    def _draw_tab_bar(self, rect) -> None:
        """Draw the document tab bar above the canvas (reserved seam).

        Args:
            rect: The center rect computed by the shell's layout.
        """

        strip = Rect(rect.x, rect.y, rect.width, min(TAB_BAR_HEIGHT, rect.height))
        if not self.layout.begin_fixed(
            "##center", strip, transparent=True, padding=False
        ):
            imgui.end()
            return

        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(6, 4))
        actions = []
        if self.tab_bar is not None:
            actions = self.tab_bar.draw()
        imgui.pop_style_var()

        imgui.end()

        # Apply actions after the window is closed so tab-list mutations do not
        # happen mid-draw of the tab bar.
        if actions:
            self.bus.publish(events.TAB_ACTION_REQUEST, actions)
            # self._handle_tab_actions(actions)

    def draw_left_sidebar(self, rect: Rect) -> None:
        """Draw the left sidebar: Explorer, Assets, and Settings tabs.

        Args:
            rect: The left sidebar rect computed by the shell's layout.
        """
        if not self.layout.begin_fixed("##sidebar_left", rect):
            imgui.end()
            return

        if imgui.begin_tab_bar("##left_tabs"):
            opened, _ = imgui.begin_tab_item(icons.FOLDER_EXPLORER)
            set_tooltip("Explorer")
            if opened:
                self.explorer.draw()
                imgui.end_tab_item()

            opened, _ = imgui.begin_tab_item(icons.IMAGE)
            set_tooltip("Assets")
            if opened:
                imgui.end_tab_item()

            opened, _ = imgui.begin_tab_item(icons.SETTINGS)
            set_tooltip("Settings")
            if opened:
                imgui.end_tab_item()
            imgui.end_tab_bar()

        imgui.end()

    def draw_right_sidebar(self, rect: Rect) -> None:
        """Draw the right sidebar (reserved seam).

        Args:
            rect: The right sidebar rect computed by the shell's layout.
        """
        if not self.layout.begin_fixed("##sidebar_right", rect):
            imgui.end()
            return
        imgui.end()


__all__ = ["EditorScreen"]
