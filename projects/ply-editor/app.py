"""The editor application: engine lifecycle, input, and actions."""

from __future__ import annotations

from pathlib import Path

import pyray as pr
from imgui_bundle import imgui

import plyunit
from scripts import constants as const, events
from scripts.context import AppContext
from scripts.dialogs import ask_project_folder
from scripts.global_config import GlobalConfig
from scripts.project.file_tree import FileTree
from scripts.project.project import Project
from scripts.project.scan_worker import ScanWorker
from scripts.ui.layer import ImGuiLayer


class EditorApp(plyunit.App):
    """Root application unit owning the editor's services and wiring.

    Attributes:
        default_font: The main ImGui font, installed after boot.
        bus: The editor event bus.
        context: The shared state hub.
        layer: The ImGui chrome layer.
        project: The currently opened project.
        scan_worker: The background scan coordinator.
    """

    default_font: imgui.ImFont

    def on_load(self) -> None:
        """Build services, wire events and hotkeys."""
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

        # Event wiring.
        self.bus.subscribe(events.APP_OPEN_PROJECT, self.on_action_open_project)
        self.bus.subscribe(events.APP_SAVE, self.on_action_save)

        # Hotkeys.
        self.input.map(
            "ctrl", pr.KeyboardKey.KEY_LEFT_CONTROL, pr.KeyboardKey.KEY_RIGHT_CONTROL
        )
        self.input.map(events.APP_SAVE, pr.KeyboardKey.KEY_S)

    def fixed_update(self, dt: float, step: int) -> None:
        """Advance the scene at a fixed rate."""
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        """Run the frame render pipeline (fully user-owned)."""
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((255, 255, 255, 255))

        # Main-thread editor work.
        self.scan_worker.poll()

        if (
            not self.ui.want_capture_keyboard()
            and self.project.active
            and self.input.is_down("ctrl")
            and self.input.is_pressed(events.APP_SAVE)
        ):
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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_action_open_project(self) -> None:
        """Ask for a folder, open it as the project, and start scanning."""
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

    def on_action_save(self) -> None:
        """Persist the global config and the open project."""
        self.global_config.save()
        self.project.save()
        self.context.set_status("Berhasil disimpan")
