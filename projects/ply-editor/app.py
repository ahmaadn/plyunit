from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pyray as pr

import plyunit
from scripts import constants as const
from scripts.app import events
from scripts.app.context import Context
from scripts.app.keymap import poll_shortcuts
from scripts.core.exclude import resolve_excludes
from scripts.services.dialogs import ask_project_folder
from scripts.services.file_tree import FileTree
from scripts.services.scan_worker import ScanWorker
from scripts.state.ui import StatusType
from scripts.ui.shell import EditorShell

if TYPE_CHECKING:
    from imgui_bundle import imgui

logger = logging.getLogger(__name__)


class ProjectError(RuntimeError):
    """Failure while opening or preparing a project."""


class EditorApp(plyunit.App):
    """Root application unit owning the editor's services and wiring.

    Attributes:
        default_font: The main ImGui font, installed after boot.
        bus: The editor event bus (the intent dispatcher).
        shell: The ImGui chrome layer.
        project: The currently opened project.
        scanner: The background scan coordinator.
    """

    default_font: imgui.ImFont

    def on_load(self) -> None:
        """Build state, services, and UI wiring; restore last project."""
        self.ctx = Context()
        self.ctx.load_global_config()
        self.ctx.global_.prune_missing()
        self.ctx.save_global_config()

        self.setup_logging("debug", "./logs/editor.log")

        # 1. Shared state, complete at construction.
        self.bus = plyunit.EventBus()
        # 2. Engine pieces.
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

        # 3. Services; must exist before the UI layer builds panels.
        self.file_tree = FileTree()
        self.scanner = ScanWorker()

        # Event sub
        self.bus.subscribe(events.APP_OPEN_FOLDER_PROJECT, self.on_open_project_folder)
        self.bus.subscribe(
            events.APP_OPEN_PROJECT_BY_PATH, self.on_open_project_by_path
        )
        self.bus.subscribe(events.APP_NEW_MAP, self.on_new_map)
        self.bus.subscribe(events.APP_OPEN_MAP, self.on_open_map)
        self.bus.subscribe(events.APP_SAVE, self.on_save)
        self.bus.subscribe(events.APP_SAVE_AS, self.on_save_as)
        self.bus.subscribe(events.APP_REFRESH_ASSETS, self.on_refresh_assets)

        # 5. UI layer: attaches the draw callback and builds panels.
        self.shell = EditorShell()

        # Hotkeys.
        self.input.map(
            "ctrl", pr.KeyboardKey.KEY_LEFT_CONTROL, pr.KeyboardKey.KEY_RIGHT_CONTROL
        )
        self.input.map(events.APP_SAVE, pr.KeyboardKey.KEY_S)

        # 6. Session restore.
        self.open_last_project()

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

        # Main-thread editor work: apply finished background scans
        # before the UI draws, so this frame already sees fresh state.
        self.scanner.poll()

        poll_shortcuts(self.bus, ui=self.ui, input_service=self.input)

        self.shell.update(dt)
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

    def open_last_project(self) -> None:
        """Reopen the project recorded as most recently used.

        Does nothing when no last project is recorded. When the recorded
        folder no longer exists, it is cleared and pruned from the
        recent list instead of being opened.
        """
        if self.ctx.global_.last_project is None:
            return

        self.ctx.workspace.scanning = True
        path_last_project = Path(self.ctx.global_.last_project)
        if not path_last_project.exists():
            logger.debug(f"Cannot open last project : {self.ctx.global_.last_project}")
            self.ctx.global_.last_project = None
            self.ctx.global_.prune_missing()
            self.ctx.workspace.scanning = False
            return

        self.on_open_project_by_path(str(path_last_project))
        logger.info(f"Open last project : {self.ctx.global_.last_project}")

    def on_unload(self):
        """Stop the background scan and persist everything on shutdown."""
        self.scanner.cancel()
        self.ctx.save_global_config()
        if self.ctx.project_active:
            self.ctx.save()

    def on_open_project_folder(self) -> None:
        """Ask for a folder, open it as the project, and start scanning."""
        path = ask_project_folder()
        if not path:
            return

        self.open_project(Path(path))
        self.ctx.ui.set_status(
            f"Project '{self.ctx.project.name}' dibuka; memindai aset..."
            + (" (scaffold .ply-editor dibuat)" if self.ctx.project_created_at else "")
        )

    def on_open_project_by_path(self, path: str) -> None:
        """Open a known folder as the project and start scanning."""
        self.open_project(Path(path))
        self.ctx.ui.set_status("Open last project")

    def on_save(self) -> None:
        """Persist the global config and the open project."""
        if not self.ctx.project_active:
            return
        self.ctx.save()
        self.ctx.ui.set_status("Berhasil disimpan")

    def on_save_as(self) -> None:
        """Save-as is not implemented yet."""
        self.ctx.ui.set_status("Simpan Sebagai belum tersedia", StatusType.WARNING)

    def on_new_map(self) -> None:
        """Map creation is not implemented yet."""
        self.ctx.ui.set_status("Map Baru belum tersedia", StatusType.WARNING)

    def on_open_map(self) -> None:
        """Opening a map document is not implemented yet."""
        self.ctx.ui.set_status("Buka Map belum tersedia", StatusType.WARNING)

    def on_refresh_assets(self) -> None:
        """Rescan the current project's assets."""
        if not self.ctx.project_active:
            return
        self.scanner.start(self.ctx.project_root, self.ctx.excludes, reason="refresh")

    def open_project(self, path: Path) -> None:
        """Open ``path`` as the project and start the background scan."""
        self.scanner.cancel()
        # self.project.open(path, global_excludes=self.ctx.global_.exclude_folders)
        root = Path(path).expanduser()
        try:
            root = root.resolve()
        except OSError as exc:
            raise ProjectError(f"Project path is unreadable: {path}") from exc

        if not root.exists():
            raise ProjectError(f"Project folder does not exist: {root}")
        if not root.is_dir():
            raise ProjectError(f"Project path is not a folder: {root}")

        last_root = self.ctx.project_root
        try:
            # config, editor, created = load_project_scaffold(root, self.ctx)
            if not root.is_dir():
                raise NotADirectoryError(f"Not a directory: {root}")

            self.ctx.set_project_root(root)

            project_dir = root / const.PROJECT_DIR_NAME
            created = not project_dir.is_dir()
            project_dir.mkdir(parents=True, exist_ok=True)

            config_path = project_dir / const.PROJECT_CONFIG_NAME
            self.ctx.load_project_config(config_path, fallback_name=root.name)

            editor_path = project_dir / const.EDITOR_CONFIG_NAME
            self.ctx.load_editor_config(editor_path)

            if created:
                self.ctx.save_project_config()
                self.ctx.save_editor_config()
                logger.info("Scaffold project dibuat di %s", project_dir)

        except OSError as exc:
            self.ctx.project_root = last_root
            raise ProjectError(
                f"Failed to prepare {const.PROJECT_DIR_NAME}/ in {root}: {exc}"
            ) from exc

        if not self.ctx.project.name:
            self.ctx.project.name = root.name
            self.ctx.save_project_config()

        excludes = resolve_excludes(
            self.ctx.global_.exclude_folders or [],
            self.ctx.project.exclude_folders,
            override=self.ctx.project.exclude_override,
        )

        self.ctx.excludes = excludes
        self.ctx.project_active = True

        assets = self.one("@Assets")
        assets.clear_all()
        assets.set_assets_path(root)

        # A different project's tree is invalid from this moment on.
        file_tree = self.one("@FileTree")
        if file_tree.root_path != root:
            file_tree.reset()

        logger.info(f"Project dibuka: {root}")

        self.ctx.global_.touch_project(self.ctx.project_root, self.ctx.project.name)
        self.scanner.start(self.ctx.project_root, self.ctx.excludes)
