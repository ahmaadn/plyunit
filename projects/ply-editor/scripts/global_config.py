"""Konfigurasi global editor (lintas project).

Disimpan di ``scripts/data/settings.json`` (lokal, dapat dikomit-tolak). Berisi
daftar project terakhir dibuka, project aktif terakhir, dan geometri window.

Konfigurasi ini **tidak pernah** menggagalkan startup: file rusak atau hilang
selalu jatuh ke nilai default, dengan file lama dicadangkan sebagai ``.bak``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import scripts.constants as const
from scripts.exclude import normalize_patterns
from scripts.utils import read_json_safe, write_json_atomic

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"
GLOBAL_CONFIG_DIR = Path(__file__).parent.parent / "data"
GLOBAL_CONFIG_PATH = GLOBAL_CONFIG_DIR / SETTINGS_FILENAME


@dataclass(slots=True)
class RecentProject:
    """Satu entri project yang pernah dibuka.

    Attributes:
        path: Path absolut folder project.
        name: Nama tampilan project.
        opened_at: Unix timestamp terakhir dibuka (detik).
    """

    path: str
    name: str
    opened_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "name": self.name, "opened_at": self.opened_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentProject | None:
        """Bangun dari dict; ``None`` bila entri tidak dapat dipakai."""
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
        """True bila folder project masih ada di disk."""
        try:
            return Path(self.path).is_dir()
        except OSError:
            return False


@dataclass(slots=True)
class GlobalConfig:
    """Konfigurasi global editor.

    Attributes:
        version: Versi skema file.
        recent_projects: Daftar project terakhir (terbaru di depan).
        last_project: Path project yang dibuka terakhir kali.
        window: Geometri window tersimpan.
        exclude_folders: Pola folder yang dilewati saat memindai project.
            Berlaku untuk semua project kecuali di-override per project.
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

    # ------------------------------------------------------------------
    # Recents
    # ------------------------------------------------------------------

    def touch_project(self, path: str | Path, name: str | None = None) -> None:
        """Catat project sebagai baru saja dibuka.

        Memindahkan entri ke posisi teratas, memperbarui timestamp, dan
        memangkas daftar ke :data:`MAX_RECENT_PROJECTS`.

        Args:
            path: Path folder project.
            name: Nama tampilan (default: nama folder).
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
        """Hapus satu project dari daftar recents."""
        resolved = str(Path(path).resolve())
        self.recent_projects = [r for r in self.recent_projects if r.path != resolved]
        if self.last_project == resolved:
            self.last_project = None

    def prune_missing(self) -> int:
        """Buang entri recents yang foldernya sudah tidak ada.

        Returns:
            Jumlah entri yang dibuang.
        """
        before = len(self.recent_projects)
        self.recent_projects = [r for r in self.recent_projects if r.exists]
        if self.last_project and not Path(self.last_project).is_dir():
            self.last_project = None
        return before - len(self.recent_projects)

    def valid_last_project(self) -> Path | None:
        """Path project terakhir bila masih valid, selain itu ``None``."""
        if not self.last_project:
            return None
        p = Path(self.last_project)
        return p if p.is_dir() else None

    def to_dict(self) -> dict[str, Any]:
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
        """Bangun dari dict, mentoleransi field hilang / bertipe salah."""
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

        # Field absen berarti config lama: pakai default. List kosong yang
        # eksplisit dihormati (user sengaja mematikan semua exclude).
        if "exclude_folders" in data:
            raw_excludes = data.get("exclude_folders")
            if isinstance(raw_excludes, list):
                out.exclude_folders = list(normalize_patterns(raw_excludes))
        return out

    @classmethod
    def load(cls, path: Path | None = None) -> GlobalConfig:
        """Muat config global dari disk.

        Tidak pernah melempar: file hilang / rusak / tak terbaca menghasilkan
        config default (file rusak dicadangkan lebih dulu).

        Args:
            path: Override path file (default: :func:`global_config_path`).

        Returns:
            :class:`GlobalConfig` yang siap dipakai.
        """
        p = path or GLOBAL_CONFIG_PATH
        result = read_json_safe(p)
        if result is None:
            return cls()
        return cls.from_dict(result)

    def save(self, path: Path | None = None) -> bool:
        """Tulis config global secara atomik.

        Menulis ke file sementara di direktori yang sama lalu ``os.replace``
        agar tidak ada file setengah tertulis bila proses mati.

        Args:
            config: Config yang akan ditulis.
            path: Override path file.

        Returns:
            True bila berhasil ditulis.
        """
        p = path or GLOBAL_CONFIG_PATH
        return write_json_atomic(p, self.to_dict())


__all__ = ["GlobalConfig", "RecentProject"]
