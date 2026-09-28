"""The ImGui bridge layer: menu bar, toolbar, sidebars, status bar.

:class:`ImGuiLayer` is a :class:`plyunit.ServiceUnit` facade over the
engine ``@ImGui`` service. It registers one draw callback that renders
the whole editor chrome — menu bar, toolbar strip, sidebars with
splitters, and the status bar — and exposes the service for input
capture queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from imgui_bundle import icons_fontawesome_6 as icons_fa, imgui

import plyunit
from scripts import events
from scripts.context import StatusType
from scripts.ui.layout import STATUS_BAR_HEIGHT, DockLayout
from scripts.ui.panels.explorer import ExplorerPanel
from scripts.ui.screens.start_screen import StartScreen

if TYPE_CHECKING:
    from app import EditorApp


class ImGuiLayer(plyunit.ServiceUnit):
    """Facade over the engine ``@ImGui`` service.

    Args:
        app: The bootstrapped app (``plyunit.init`` must already have
            run).

    Raises:
        AttributeError: When the app has no ImGui service bound.
    """

    def __init__(self) -> None:
        super().__init__("ImGuiLayer")
        self.layout = DockLayout()
        self.explorer = ExplorerPanel()

    def on_attach(self, app: EditorApp) -> None:
        """Resolve the event bus for menu actions."""
        self.app = app
        self.bus = cast(plyunit.EventBus, app.one("@EventBus"))
        self.project = app.one("@Project")

        self._ui = app.ui
        self._ui.add_draw(self.draw)
        self.ctx = app.context

        self.start_screen = StartScreen(
            app, app._open_project, app.on_action_open_project
        )

    @property
    def ui(self) -> plyunit.ImGui:
        """The engine ``ImGui`` service (draw callbacks, capture queries)."""
        return self._ui

    def update(self, dt: float) -> None:
        """Per-frame update hook.

        Reserved seam: input gating against the layout viewport and
        ImGui capture queries belongs here.
        """

    def draw(self) -> None:
        """Draw one full editor chrome frame."""
        if not self.app.project.active and self.app.global_config.last_project is None:
            if self.start_screen is not None:
                self.start_screen.draw()
            return

        self.draw_menu_bar()
        left, center, right = self.layout.compute()

        self.draw_toolbar_strip()
        if self.layout.show_left:
            self.draw_left_sidebar(left)
        self.draw_center(center)
        if self.layout.show_right:
            self.draw_right_sidebar(right)

        # Draw the sidebars' splitters last, above the panels.
        if self.layout.show_left:
            self.layout.draw_splitter("left", left, is_left=True)
        if self.layout.show_right:
            self.layout.draw_splitter("right", right, is_left=False)

        self.draw_status_bar()

    def draw_toolbar_strip(self) -> None:
        """Draw the empty toolbar strip below the menu bar."""
        rect = self.layout.toolbar_rect()
        if not self.layout.begin_fixed("##toolbar", rect):
            imgui.end()
            return
        imgui.end()

    def draw_menu_bar(self) -> None:
        """Draw the main menu bar and the centered project title."""
        if not imgui.begin_main_menu_bar():
            return

        if imgui.begin_menu("File"):
            if imgui.menu_item("Project Baru / Buka Folder...", "", False)[0]:
                self.bus.publish(events.APP_OPEN_PROJECT)
            imgui.separator()
            if imgui.menu_item("Map Baru", "Ctrl+N", False)[0]:
                self.bus.publish(events.APP_NEW_MAP)
            if imgui.menu_item("Buka Map...", "Ctrl+O", False)[0]:
                self.bus.publish(events.APP_OPEN_MAP)
            if imgui.menu_item("Simpan", "Ctrl+S", False)[0]:
                self.bus.publish(events.APP_SAVE)
            if imgui.menu_item("Simpan Sebagai...", "", False)[0]:
                self.bus.publish(events.APP_SAVE_AS)
            imgui.end_menu()

        if imgui.begin_menu("View"):
            clicked, value = imgui.menu_item(
                "Sidebar Kiri", "Ctrl+B", self.layout.show_left
            )
            if clicked:
                self.layout.show_left = value
            clicked, value = imgui.menu_item(
                "Sidebar Kanan", "Ctrl+J", self.layout.show_right
            )
            if clicked:
                self.layout.show_right = value
            imgui.separator()
            if imgui.menu_item("Reset Lebar Sidebar", "", False)[0]:
                self.layout.reset_widths()
            imgui.end_menu()

        if imgui.begin_menu("Assets"):
            if imgui.menu_item("Pindai Ulang Folder", "F5", False)[0]:
                self.bus.publish(events.APP_REFRESH_ASSETS)
            imgui.end_menu()

        # Project title, centered in the menu bar.
        title = f"Project: {self.ctx.project_name or '(tanpa project)'}"
        title_size = imgui.calc_text_size(title)
        imgui.same_line((imgui.get_window_width() - title_size.x) * 0.5)
        imgui.text_disabled(title)

        imgui.end_main_menu_bar()

    def draw_center(self, center) -> None:
        """Draw the center canvas area (reserved seam)."""

    def draw_left_sidebar(self, rect) -> None:
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

    def draw_right_sidebar(self, rect) -> None:
        """Draw the right sidebar (reserved seam)."""
        if not self.layout.begin_fixed("##sidebar_right", rect):
            imgui.end()
            return
        imgui.end()

    def draw_status_bar(self) -> None:
        """Draw the status message strip at the bottom of the window."""
        viewport = imgui.get_main_viewport()
        height = STATUS_BAR_HEIGHT
        imgui.set_next_window_pos(
            imgui.ImVec2(
                viewport.work_pos.x, viewport.work_pos.y + viewport.work_size.y - height
            )
        )
        imgui.set_next_window_size(imgui.ImVec2(viewport.work_size.x, height))
        flags = int(
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_saved_settings
        )
        imgui.begin("##status", None, flags)

        if self.ctx.status_type == StatusType.ERROR:
            imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(1.0, 0.4, 0.4, 1.0))
            text = f"{icons_fa.ICON_FA_CIRCLE_XMARK} {self.ctx.status_msg}"
            imgui.text(text)
            imgui.pop_style_color()  # imgui.Col_.text
        elif self.ctx.status_type == StatusType.INFO:
            text = f"{icons_fa.ICON_FA_INFO} {self.ctx.status_msg}"
            imgui.text(text)
        elif self.ctx.status_type == StatusType.WARNING:
            text = f"{icons_fa.ICON_FA_TRIANGLE_EXCLAMATION} {self.ctx.status_msg}"
            imgui.text(text)
        else:
            imgui.text(self.ctx.status_msg)

        imgui.end()


__all__ = ["ImGuiLayer"]
