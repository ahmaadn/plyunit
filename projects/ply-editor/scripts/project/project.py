"""The currently opened project.

A *project* is any folder opened via ``File -> Open Project``. Opening
creates the ``.ply-editor/`` scaffold folder when missing, loads
``project.json`` and ``.ply-editor/editor.json``, and resolves the
effective exclude rules (global merged or overridden per project).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import plyunit
from scripts import constants as const
from scripts.exclude import ExcludeRules, resolve_excludes
from scripts.project.configs import EditorConfig, ProjectConfig
from scripts.project.scan import ScanResult

if TYPE_CHECKING:
    from app import EditorApp

    from scripts.context import AppContext

logger = logging.getLogger(__name__)


class ProjectError(RuntimeError):
    """Failure while opening or preparing a project."""


class Project(plyunit.ServiceUnit):
    """The project currently open in the editor.

    Attributes:
        root: Absolute project root folder.
        config: Contents of ``project.json``.
        editor: Contents of ``editor.json`` (UI state).
        excludes: Effective exclude rules (global + project override).
        scan_result: Last scan result; ``None`` before the first scan.
        created: True when the scaffold was newly created on open.
        active: True while a project is open.
    """

    def __init__(self) -> None:
        super().__init__("Project", tags={"project", "service"})
        self._root: Path = Path("")
        self._config: ProjectConfig = ProjectConfig("No Project")
        self._editor: EditorConfig = EditorConfig()
        self._excludes: ExcludeRules = ExcludeRules()
        self._scan_result: ScanResult | None = None
        self._created = False
        self.active = False

    def on_attach(self, app: EditorApp) -> None:
        """Capture the shared app context."""
        self.ctx: AppContext = app.context

    @property
    def root(self) -> Path:
        """Absolute project root folder."""
        return self._root

    @property
    def config(self) -> ProjectConfig:
        """Contents of ``project.json``."""
        return self._config

    @property
    def editor(self) -> EditorConfig:
        """Contents of ``editor.json`` (UI state)."""
        return self._editor

    @property
    def excludes(self) -> ExcludeRules:
        """Effective exclude rules."""
        return self._excludes

    @property
    def scan_result(self) -> ScanResult | None:
        """Last scan result, or ``None`` before the first scan."""
        return self._scan_result

    @property
    def project_name(self) -> str:
        """Project display name (from ``project.json``)."""
        return self._config.name

    @property
    def created(self) -> bool:
        """True when the ``.ply-editor/`` scaffold was just created."""
        return self._created

    def open_project(
        self,
        path: str | Path,
        *,
        global_excludes: list[str] | None = None,
        scan: bool = True,
    ) -> None:
        """Open a folder as the editor project.

        Creates ``.ply-editor/`` when missing, loads the configuration,
        and resets the asset index to the project root. Asset scanning
        can be deferred via ``scan=False`` so the caller can run it in
        a worker thread — startup must never block on folder traversal.

        Args:
            path: Project folder.
            global_excludes: Exclude patterns from the global config.
            scan: Run the asset scan synchronously.

        Raises:
            ProjectError: When the folder does not exist, is not a
                directory, or the scaffold cannot be created.
        """
        root = Path(path).expanduser()
        try:
            root = root.resolve()
        except OSError as exc:
            raise ProjectError(f"Project path is unreadable: {path}") from exc

        if not root.exists():
            raise ProjectError(f"Project folder does not exist: {root}")
        if not root.is_dir():
            raise ProjectError(f"Project path is not a folder: {root}")

        last_root = self._root
        self._root = root
        try:
            config, editor, created = self.load_project_scaffold()
        except OSError as exc:
            self._root = last_root
            raise ProjectError(
                f"Failed to prepare {const.PROJECT_DIR_NAME}/ in {root}: {exc}"
            ) from exc

        if not config.name:
            config.name = root.name
            config.save_config(self.project_dir / const.PROJECT_CONFIG_NAME)

        excludes = resolve_excludes(
            global_excludes or [],
            config.exclude_folders,
            override=config.exclude_override,
        )

        self._config = config
        self._editor = editor
        self._created = created
        self._excludes = excludes
        self.active = True

        assets = self.one("@Assets")
        assets.clear_all()
        assets.set_assets_path(root)

        logger.info(f"Project dibuka: {root}")

    def load_project_scaffold(
        self,
    ) -> tuple[ProjectConfig, EditorConfig, bool]:
        """Ensure the ``.ply-editor/`` folder and its default files exist.

        Called every time a folder is opened as a project. When the
        scaffold folder is missing it is created together with
        ``project.json``, ``editor.json``, and ``autotiles/``.

        Returns:
            Tuple ``(project_config, editor_config, created)`` where
            ``created`` is True when the scaffold was just created.

        Raises:
            NotADirectoryError: When the root is not a directory.
            OSError: When the folder cannot be created (e.g. read-only).
        """
        if not self.root.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.root}")

        project_dir = self.project_dir
        created = not project_dir.is_dir()
        project_dir.mkdir(parents=True, exist_ok=True)

        config_path = project_dir / const.PROJECT_CONFIG_NAME
        if config_path.exists():
            pcfg = ProjectConfig.load_config(config_path)
        else:
            pcfg = ProjectConfig.from_dict({"name": self.root.name})
            pcfg.save_config(config_path)

        editor_path = project_dir / const.EDITOR_CONFIG_NAME
        if editor_path.exists():
            ecfg = EditorConfig.load_config(editor_path)
        else:
            ecfg = EditorConfig.from_dict({})
            ecfg.save_config(editor_path)

        if created:
            logger.info("Scaffold project dibuat di %s", project_dir)
        return pcfg, ecfg, created

    @property
    def project_dir(self) -> Path:
        """Path of the ``.ply-editor/`` folder inside the project."""
        return self.root / const.PROJECT_DIR_NAME

    def save(self) -> None:
        """Save the project config and the editor config."""
        project_dir = self.project_dir
        self.config.save_config(project_dir / const.PROJECT_CONFIG_NAME)
        self.editor.save_config(project_dir / const.EDITOR_CONFIG_NAME)
        logger.info(f"Project save done in : {project_dir}")
