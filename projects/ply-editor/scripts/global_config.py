"""Editor-wide (cross-project) configuration.

Stored in ``data/settings.json`` inside the editor project (local,
never published). It holds the recently opened projects, the last
active project, window geometry, and global scan excludes.

This config **never** fails startup: a missing or corrupt file always
falls back to defaults, with the old file backed up as ``.bak``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from scripts import constants as const
from scripts.exclude import normalize_patterns
from scripts.json_io import read_json_safe, write_json_atomic

logger = logging.getLogger(__name__)

SETTINGS_FILENAME: Final = "settings.json"
GLOBAL_CONFIG_DIR: Final = Path(__file__).parent.parent / "data"
GLOBAL_CONFIG_PATH: Final = GLOBAL_CONFIG_DIR / SETTINGS_FILENAME


@dataclass(slots=True)
class RecentProject:
    """One previously opened project entry.

    Attributes:
        path: Absolute path of the project folder.
        name: Project display name.
        opened_at: Unix timestamp (seconds) of the last open.
    """

    path: str
    name: str
    opened_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {"path": self.path, "name": self.name, "opened_at": self.opened_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentProject | None:
        """Build from a dict; ``None`` when the entry is unusable."""
        raw_path = data.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        path = raw_path.strip()
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = Path(path).name or path
        opened_at = data.get("opened_at", 0.0)
        try:
            opened_at = float(opened_at)
        except (TypeError, ValueError):
            opened_at = 0.0
        return cls(path=path, name=name, opened_at=opened_at)

    @property
    def exists(self) -> bool:
        """True when the project folder still exists on disk."""
        try:
            return Path(self.path).is_dir()
        except OSError:
            return False


@dataclass(slots=True)
class GlobalConfig:
    """Editor-wide configuration.

    Attributes:
        version: Schema version of the file.
        recent_projects: Recently opened projects (newest first).
        last_project: Path of the project opened last time.
        window_width: Saved window width.
        window_height: Saved window height.
        window_maximized: Whether the window was maximized.
        exclude_folders: Folder patterns skipped when scanning a
            project. Applies to all projects unless overridden per
            project.
    """

    version: int = const.GLOBAL_CONFIG_VERSION
    recent_projects: list[RecentProject] = field(default_factory=list)
    last_project: str | None = None
    window_width: int = 1280
    window_height: int = 800
    window_maximized: bool = False
    exclude_folders: list[str] = field(
        default_factory=lambda: list(const.DEFAULT_EXCLUDES)
    )

    # -----------------------------------------------------------------
    # Recents
    # -----------------------------------------------------------------

    def touch_project(self, path: str | Path, name: str | None = None) -> None:
        """Record a project as just opened.

        Moves the entry to the front, updates its timestamp, and trims
        the list to :data:`~scripts.constants.MAX_RECENT_PROJECTS`.

        Args:
            path: Project folder path.
            name: Display name (default: folder name).
        """
        resolved = str(Path(path).resolve())
        display = name or Path(resolved).name or resolved
        self.recent_projects = [r for r in self.recent_projects if r.path != resolved]
        self.recent_projects.insert(
            0, RecentProject(path=resolved, name=display, opened_at=time.time())
        )
        del self.recent_projects[const.MAX_RECENT_PROJECTS :]
        self.last_project = resolved

    def remove_project(self, path: str | Path) -> None:
        """Remove one project from the recents list."""
        resolved = str(Path(path).resolve())
        self.recent_projects = [r for r in self.recent_projects if r.path != resolved]
        if self.last_project == resolved:
            self.last_project = None

    def prune_missing(self) -> int:
        """Drop recents whose folders no longer exist.

        Returns:
            The number of dropped entries.
        """
        before = len(self.recent_projects)
        self.recent_projects = [r for r in self.recent_projects if r.exists]
        if self.last_project and not Path(self.last_project).is_dir():
            self.last_project = None
        return before - len(self.recent_projects)

    def valid_last_project(self) -> Path | None:
        """Return the last project path when still valid, else ``None``."""
        if not self.last_project:
            return None
        p = Path(self.last_project)
        return p if p.is_dir() else None

    # -----------------------------------------------------------------
    # (De)serialization
    # -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {
            "version": const.GLOBAL_CONFIG_VERSION,
            "recent_projects": [r.to_dict() for r in self.recent_projects],
            "last_project": self.last_project,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "window_maximized": self.window_maximized,
            "exclude_folders": list(self.exclude_folders),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GlobalConfig:
        """Build from a dict, tolerating missing or mistyped fields."""
        out = cls()
        try:
            out.version = int(data.get("version", const.GLOBAL_CONFIG_VERSION))
        except (TypeError, ValueError):
            out.version = const.GLOBAL_CONFIG_VERSION

        raw_recents = data.get("recent_projects", [])
        if isinstance(raw_recents, list):
            for item in raw_recents:
                if not isinstance(item, dict):
                    continue
                entry = RecentProject.from_dict(item)
                if entry is not None:
                    out.recent_projects.append(entry)
            del out.recent_projects[const.MAX_RECENT_PROJECTS :]

        last = data.get("last_project")
        out.last_project = last if isinstance(last, str) and last.strip() else None

        if window_height := data.get("window_height"):
            out.window_height = window_height

        if window_width := data.get("window_width"):
            out.window_width = window_width

        if window_maximized := data.get("window_maximized"):
            out.window_maximized = window_maximized

        # A missing field means an old config: keep the default. An
        # explicit empty list is honored (the user disabled all
        # excludes on purpose).
        if "exclude_folders" in data:
            raw_excludes = data.get("exclude_folders")
            if isinstance(raw_excludes, list):
                out.exclude_folders = list(normalize_patterns(raw_excludes))
        return out

    @classmethod
    def load(cls, path: Path | None = None) -> GlobalConfig:
        """Load the global config from disk.

        Never raises: a missing / corrupt / unreadable file yields a
        default config (the corrupt file is backed up first).

        Args:
            path: Optional path override (default:
                :data:`GLOBAL_CONFIG_PATH`).

        Returns:
            A ready-to-use :class:`GlobalConfig`.
        """
        p = path or GLOBAL_CONFIG_PATH
        result = read_json_safe(p)
        if result is None:
            return cls()
        return cls.from_dict(result)

    def save(self, path: Path | None = None) -> bool:
        """Write the global config atomically.

        Args:
            path: Optional path override.

        Returns:
            True when the write succeeded.
        """
        p = path or GLOBAL_CONFIG_PATH
        return write_json_atomic(p, self.to_dict())


__all__ = ["GLOBAL_CONFIG_DIR", "GLOBAL_CONFIG_PATH", "GlobalConfig", "RecentProject"]
