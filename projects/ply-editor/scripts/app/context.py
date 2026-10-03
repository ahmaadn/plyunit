from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import plyunit
from scripts import constants as const
from scripts.core.exclude import ExcludeRules
from scripts.services.json_io import read_json_safe, write_json_atomic
from scripts.state.project import EditorConfig, ProjectConfig
from scripts.state.settings import GlobalConfig
from scripts.state.ui import UIState
from scripts.state.workspace import WorkspaceState

logger = logging.getLogger(__name__)

SETTINGS_FILENAME: Final = "settings.json"
GLOBAL_CONFIG_DIR: Final = Path(__file__).parent.parent.parent / "data"
GLOBAL_CONFIG_PATH: Final = GLOBAL_CONFIG_DIR / SETTINGS_FILENAME


class Context(plyunit.ServiceUnit):
    """Load and save global and per-project editor configs."""

    def __init__(self):
        """Initialize the context with empty state.

        All fields must be populated by the caller before the context
        is used: call :meth:`load_global_config` and
        :meth:`load_project_config` / :meth:`load_editor_config` before
        accessing their corresponding dataclasses.
        """
        super().__init__("Context", tags={"service", "context"})
        # pyrefly: ignore [bad-assignment]
        self.project: ProjectConfig = None
        # pyrefly: ignore [bad-assignment]
        self.editor: EditorConfig = None
        # pyrefly: ignore [bad-assignment]
        self.global_: GlobalConfig = None

        # Project
        self.project_root = Path("")
        self.project_active = False
        self.project_created_at = None
        self.excludes = ExcludeRules()
        self.scan_result = None

        # workspace
        self.workspace = WorkspaceState()

        # ui state
        self.ui = UIState()

    @property
    def project_dir(self):
        return self.project_root / const.PROJECT_CONFIG_NAME

    def set_project_root(self, root: Path) -> None:
        """Set the project root and recompute the project directory.

        Args:
            root: Absolute path of the project folder.
        """
        self.project_root = root

    def load_global_config(self, path: Path | None = None) -> GlobalConfig:
        """Load the global config from disk; defaults when missing/corrupt.

        Args:
            path: Optional path override (default:
                :data:`GLOBAL_CONFIG_PATH`).

        Returns:
            A ready-to-use :class:`GlobalConfig`.
        """
        p = path or GLOBAL_CONFIG_PATH
        result = read_json_safe(p)
        if result is None:
            self.global_ = GlobalConfig()
        else:
            self.global_ = GlobalConfig.from_dict(result)
        return self.global_

    def save_global_config(self, path: Path | None = None) -> bool:
        """Write the global config atomically.

        Args:
            path: Optional path override.

        Returns:
            True when the write succeeded.
        """
        p = path or GLOBAL_CONFIG_PATH
        return write_json_atomic(p, self.global_.to_dict())

    def load_project_config(
        self, path: Path, *, fallback_name: str = ""
    ) -> ProjectConfig:
        """Load ``project.json``; defaults when missing or corrupt.

        Args:
            path: Config file path.
            fallback_name: Name to use when the file lacks one.

        Returns:
            A ready-to-use :class:`ProjectConfig`.
        """
        raw = read_json_safe(path)
        fallback = fallback_name or (path.parent.name or str(path))
        if raw is None:
            self.project = ProjectConfig(name=fallback)
        else:
            self.project = ProjectConfig.from_dict(raw, fallback_name=fallback)
        return self.project

    def save_project_config(self) -> bool:
        """Write ``project.json`` atomically.

        Returns:
            True when the write succeeded.
        """
        return write_json_atomic(
            self.project_dir / const.PROJECT_CONFIG_NAME, self.project.to_dict()
        )

    def load_editor_config(self, path: Path) -> EditorConfig:
        """Load ``editor.json``; defaults when missing or corrupt.

        Args:
            path: Config file path.

        Returns:
            A ready-to-use :class:`EditorConfig`.
        """
        raw = read_json_safe(path)
        if raw is None:
            self.editor = EditorConfig()
        else:
            self.editor = EditorConfig.from_dict(raw)
        return self.editor

    def save_editor_config(self) -> bool:
        """Write ``editor.json`` atomically.

        Returns:
            True when the write succeeded.
        """
        return write_json_atomic(
            self.project_dir / const.EDITOR_CONFIG_NAME, self.editor.to_dict()
        )

    def save(self) -> None:
        """Save the project config and the editor config.

        Also persists the global config, which records the project as
        the most recently used one.
        """
        self.save_global_config()
        self.save_project_config()
        self.save_editor_config()
        logger.info(f"Project save done in : {self.project_dir}")


__all__ = ["GLOBAL_CONFIG_DIR", "GLOBAL_CONFIG_PATH", "Context"]
