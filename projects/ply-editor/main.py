"""ply-editor - entrypoint.

Run from the monorepo root:

    uv run python projects/ply-editor/main.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pyray as pr
from imgui_bundle import hello_imgui, icons_fontawesome_6 as icons_fa, imgui

import plyunit
from scripts import constants as const, events
from scripts.context import AppContext, StatusType
from scripts.dialogs import ask_project_folder
from scripts.global_config import GlobalConfig
from scripts.layout import DockLayout
from scripts.panels.explorer import ExplorerPanel
from scripts.project.file_tree import FileTree
from scripts.project.project import Project
from scripts.project.scan import ScanWorker
from scripts.services.assets import Assets

if TYPE_CHECKING:
    import plyunit

DrawCallback = Callable[[], None]
"""Argument-less callable drawing one ImGui frame."""


class ImGuiLayer(plyunit.ServiceUnit):
    """Facade over the engine ``@ImGui`` service.

    Args:
        app: The bootstrapped app (``pu.init`` must already have run).

    Raises:
        RuntimeError: If the ImGui service is not registered — i.e.
            ``AppConfig.imgui.enabled`` was not set to ``True``.
    """

    def __init__(self, app: EditorApp) -> None:
        super().__init__("ImGuiLayer")
        """Resolve the service and prepare callback bookkeeping."""
        self._ui = app.ui
        self.ctx = app.context
        self.layout = DockLayout()
        self._ui.add_draw(self.draw)
        self.explorer = ExplorerPanel()

    def on_attach(self, app):
        self.mouse = cast(plyunit.Mouse, app.one("@Mouse"))
        self.bus = cast(plyunit.EventBus, app.one("@EventBus"))

    @property
    def ui(self) -> plyunit.ImGui:
        """The engine ``ImGui`` service (draw callbacks, capture queries)."""
        return self._ui

    def update(self, dt: float):

        outside_viewport = not self.layout.viewport.contains(
            float(self.mouse.x), float(self.mouse.y)
        )
        wants_mouse = self.ui.want_capture_mouse() or outside_viewport
        wants_keyboard = self.ui.want_capture_keyboard()

    def draw(self):

        self.draw_menu_bar()
        left, center, right = self.layout.compute()

        # Draw Content
        self.draw_toolbar_strip()
        if self.layout.show_left:
            self.draw_left_sidebar(left)
        self.draw_center(center)
        if self.layout.show_right:
            self.draw_right_sidebar(right)

        # Draw Arena sidear kiri, kanan dan canvas
        if self.layout.show_left:
            self.layout.draw_splitter("left", left, is_left=True)
        if self.layout.show_right:
            self.layout.draw_splitter("right", right, is_left=False)

        self.draw_status_bar()

    def draw_toolbar_strip(self) -> None:
        """Strip tool di bawah menu bar, membentang selebar jendela."""

        rect = self.layout.toolbar_rect()
        if not self.layout.begin_fixed("##toolbar", rect):
            imgui.end()
            return
        imgui.end()

    def draw_menu_bar(self):
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
            if self.layout is not None:
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

        # Draw Title
        title = title = f"Project: {self.ctx.project_name or '(tanpa project)'}"
        title_size = imgui.calc_text_size(title)
        imgui.same_line((imgui.get_window_width() - title_size.x) * 0.5)
        imgui.text_disabled(title)

        imgui.end_main_menu_bar()

    def draw_center(self, center): ...

    def draw_left_sidebar(self, rect):
        from imgui_bundle import imgui

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

    def draw_right_sidebar(self, rect):
        if not self.layout.begin_fixed("##sidebar_right", rect):
            imgui.end()
            return
        imgui.end()

    def draw_status_bar(self) -> None:
        viewport = imgui.get_main_viewport()
        height = 26.0
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
        elif self.ctx.status_msg == StatusType.WARNING:
            text = f"{icons_fa.ICON_FA_TRIANGLE_EXCLAMATION} {self.ctx.status_msg}"
            imgui.text(text)
        else:
            imgui.text(self.ctx.status_msg)

        imgui.end()


class EditorApp(plyunit.App):
    default_font: imgui.ImFont

    def on_load(self) -> None:
        """Push the preview scene and build the editor."""
        self.global_config = GlobalConfig.load()
        self.global_config.prune_missing()
        self.global_config.save()

        self.setup_logging("debug", "./logs/editor.log")

        self.bus = plyunit.EventBus()
        self.context = AppContext(self)
        self.mouse = plyunit.Mouse()
        self.input = plyunit.Input(gamepad=False)
        # pyrefly: ignore [bad-override-mutable-attribute]
        self.camera: plyunit.Camera2D = plyunit.Camera2D(
            (
                const.CAMERA_VIRTUAL_WIDTH,
                const.CAMERA_VIRTUAL_HEIGHT,
            ),
            position=(0.0, 0.0),
            zoom=2.0,
        )
        self.camera.setup(self.config.window_width, self.config.window_height)
        ui = self.one_or_none("@ImGui", scope="global")
        if ui is None:
            raise RuntimeError("Install ImGui")
        self._ui = ui

        self.layer = ImGuiLayer(self)
        self.project = Project()
        self.file_tree = FileTree()
        self.scan_worker = ScanWorker()

        # Events
        self.bus.subscribe(events.APP_OPEN_PROJECT, self.on_action_open_project)
        self.bus.subscribe(events.APP_SAVE, self.on_action_save)

        # actions
        self.input.map(
            "ctrl", pr.KeyboardKey.KEY_LEFT_CONTROL, pr.KeyboardKey.KEY_RIGHT_CONTROL
        )
        self.input.map(events.APP_SAVE, pr.KeyboardKey.KEY_S)

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        """Run the frame render pipeline (fully user-owned)."""
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((255, 255, 255, 255))

        # Main-thread editor work
        self.scan_worker.pool()

        if not self.ui.want_capture_keyboard() and self.project.active:
            if self.input.is_down("ctrl"):
                if self.input.is_pressed(events.APP_SAVE):
                    self.bus.publish(events.APP_SAVE)

        self.layer.update(dt)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.ui.frame(dt)
        self.window.end_drawing()
        self.mouse.update(dt)
        self.input.update(dt)

    @property
    def ui(self) -> plyunit.ImGui:
        """The engine ``ImGui`` service (draw callbacks, capture queries)."""
        return self._ui

    def on_action_open_project(self):
        path = ask_project_folder()
        if not path:
            return

        self.scan_worker.cancel()
        self.project.open_project(
            Path(path), global_excludes=self.global_config.exclude_folders
        )
        self.scan_worker.start(self.project.root, self.project.excludes)
        self.context.set_status(
            f"Project '{self.project.project_name}' dibuka; memindai aset..."
            + (" (scaffold .ply-editor dibuat)" if self.project.created else "")
        )

    def on_action_save(self):
        self.global_config.save()
        self.project.save()
        self.context.set_status("Berhasil disimpan")


def load_font():
    """Load Roboto as the main font and merge Font Awesome into the same ImGui
    font atlas."""

    # Main font
    return hello_imgui.load_font_ttf_with_font_awesome_icons(
        str(const.FONT_PATH),
        const.FONT_SIZE,
    )


def main() -> None:
    """Bootstrap and run the editor."""
    app = plyunit.init(
        EditorApp(),
        plyunit.AppConfig(
            title=const.APP_NAME,
            window_width=const.WINDOW_WIDTH,
            window_height=const.WINDOW_HEIGHT,
            target_fps=const.FPS,
            fixed_update_hz=60,
            imgui=plyunit.ImGuiConfig(
                enabled=True,
                dark_style=True,
                no_ini=True,
            ),
        ),
        asset=Assets,
    )
    app.default_font = load_font()
    app.run()


if __name__ == "__main__":
    main()
