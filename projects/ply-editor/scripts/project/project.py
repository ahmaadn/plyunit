from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import plyunit
from plyunit.tilemap.encoding import ENCODER_REGISTRY
from scripts import constants as const
from scripts.exclude import ExcludeRules, normalize_patterns, resolve_excludes
from scripts.project.scan import ScanResult
from scripts.utils import known_keys_stripped, read_json_safe, write_json_atomic

if TYPE_CHECKING:
    from main import EditorApp

    from scripts.context import AppContext


logger = logging.getLogger(__name__)


class ProjectError(RuntimeError):
    """Kegagalan saat membuka atau menyiapkan project."""


@dataclass
class MapDefaults:
    tile_size: tuple[int, int] = (const.DEFAULT_TILE_SIZE, const.DEFAULT_TILE_SIZE)
    chunk_size: int = const.DEFAULT_CHUNK_SIZE
    encoding: str = const.DEFAULT_ENCODING
    background_color: tuple[int, int, int, int] = (20, 20, 30, 255)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_size": list(self.tile_size),
            "chunk_size": self.chunk_size,
            "encoding": self.encoding,
            "background_color": list(self.background_color),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        out = cls()
        ts = data.get("tile_size")
        if isinstance(ts, (list, tuple)) and len(ts) >= 2:
            with contextlib.suppress(TypeError, ValueError):
                out.tile_size = (max(1, int(ts[0])), max(1, int(ts[1])))

        with contextlib.suppress(TypeError, ValueError):
            out.chunk_size = max(1, int(data.get("chunk_size", out.chunk_size)))
        enc = data.get("encoding")

        if isinstance(enc, str):
            out.encoding = enc if enc in ENCODER_REGISTRY else "array"

        bg = data.get("background_color")
        if isinstance(bg, (list, tuple)) and len(bg) == 4:
            with contextlib.suppress(TypeError, ValueError):
                out.background_color = (
                    int(bg[0]),
                    int(bg[1]),
                    int(bg[2]),
                    int(bg[3]),
                )
        return out


_PROJECT_KNOWN = frozenset({
    "name",
    "version",
    "assets_root",
    "defaults",
    "exclude_folders",
    "exclude_override",
})


@dataclass(slots=True)
class ProjectConfig:
    name: str
    version: int = const.PROJECT_CONFIG_VERSION
    assets_root: str = "/data"
    defaults: MapDefaults = field(default_factory=MapDefaults)
    exclude_folders: list[str] = field(default_factory=list)
    exclude_override: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.extra)
        out.update({
            "version": const.PROJECT_CONFIG_VERSION,
            "name": self.name,
            "assets_root": self.assets_root,
            "defaults": self.defaults.to_dict(),
            "exclude_folders": list(self.exclude_folders),
            "exclude_override": self.exclude_override,
        })
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, fallback_name: str = "") -> Self:
        out = cls(name=fallback_name)
        with contextlib.suppress(TypeError, ValueError):
            out.version = int(data.get("version", const.PROJECT_CONFIG_VERSION))

        name = data.get("name")
        if isinstance(name, str) and name.strip():
            out.name = name.strip()

        assets_root = data.get("assets_root")
        if isinstance(assets_root, str) and assets_root.strip():
            out.assets_root = assets_root.strip()

        raw_defaults = data.get("defaults")
        if isinstance(raw_defaults, dict):
            out.defaults = MapDefaults.from_dict(raw_defaults)
        raw_excludes = data.get("exclude_folders")

        if isinstance(raw_excludes, list):
            out.exclude_folders = list(normalize_patterns(raw_excludes))

        if "exclude_override" in data:
            out.exclude_override = bool(data.get("exclude_override"))
        out.extra = known_keys_stripped(data, _PROJECT_KNOWN)

        return out

    @classmethod
    def load_config(cls, path: Path) -> Self:
        """Muat ``project.json``; default bila hilang / rusak."""
        raw = read_json_safe(path)
        fallback = path.parent.name or str(path)
        if raw is None:
            return cls(name=fallback)
        return cls.from_dict(raw, fallback_name=fallback)

    def save_config(self, path: Path):
        """Tulis ``project.json`` secara atomik."""
        return write_json_atomic(path, self.to_dict())


@dataclass(slots=True)
class CameraState:
    """Posisi & zoom kamera editor yang dipulihkan per project."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "zoom": self.zoom}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        out = cls()
        with contextlib.suppress(TypeError, ValueError):
            out.x = float(data.get("x", out.x))
            out.y = float(data.get("y", out.y))
            out.zoom = float(data.get("zoom", out.zoom))
        if not (0.01 <= out.zoom <= 64.0):
            out.zoom = 2.0
        return out


@dataclass(slots=True)
class GridToggles:
    """Status toggle overlay canvas."""

    tile: bool = True
    chunk: bool = True
    origin: bool = True
    collision: bool = False
    objects: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile": self.tile,
            "chunk": self.chunk,
            "origin": self.origin,
            "collision": self.collision,
            "objects": self.objects,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        out = cls()
        for attr in ("tile", "chunk", "origin", "collision", "objects"):
            if attr in data:
                setattr(out, attr, bool(data[attr]))
        return out


_EDITOR_KNOWN = frozenset({
    "version",
    "last_open",
    "open_list",
    "camera",
    "grid",
    "active_layer",
    "explorer_relevant_only",
    "panels",
    "sidebar",
})


@dataclass(slots=True)
class EditorConfig:
    """Isi ``.ryeditor/editor.json`` — state UI per project.

    Attributes:
        version: Versi skema.
        last_open: Path map terakhir dibuka, relatif terhadap root project.
        open_list: Map yang terbuka sebagai tab, relatif terhadap root project.
        camera: Posisi & zoom kamera.
        grid: Toggle overlay.
        active_layer: Layer aktif terakhir.
        panels: Status buka/tutup panel (nama panel -> bool).
        sidebar: Lebar sidebar kiri/kanan dalam pixel.
        browser: State browser sidebar kiri.
        extra: Key tak dikenal yang dipertahankan.
    """

    version: int = const.EDITOR_CONFIG_VERSION
    last_open: str | None = None
    open_list: list[str] = field(default_factory=list)
    camera: CameraState = field(default_factory=CameraState)
    grid: GridToggles = field(default_factory=GridToggles)
    active_layer: str = const.LAYER_BASE
    explorer_relevant_only: bool = True
    panels: dict[str, bool] = field(default_factory=dict)
    sidebar: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.extra)
        out.update({
            "version": const.EDITOR_CONFIG_VERSION,
            "last_open": self.last_open,
            "open_list": list(self.open_list),
            "camera": self.camera.to_dict(),
            "grid": self.grid.to_dict(),
            "active_layer": self.active_layer,
            "explorer_relevant_only": self.explorer_relevant_only,
            "panels": dict(self.panels),
            "sidebar": dict(self.sidebar),
        })
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        out = cls()
        with contextlib.suppress(TypeError, ValueError):
            out.version = int(data.get("version", const.EDITOR_CONFIG_VERSION))
        last_open = data.get("last_open")
        out.last_open = (
            last_open if isinstance(last_open, str) and last_open.strip() else None
        )
        raw_open = data.get("open_list")
        if isinstance(raw_open, list):
            out.open_list = [
                item.strip()
                for item in raw_open
                if isinstance(item, str) and item.strip()
            ]
        raw_camera = data.get("camera")
        if isinstance(raw_camera, dict):
            out.camera = CameraState.from_dict(raw_camera)
        raw_grid = data.get("grid")
        if isinstance(raw_grid, dict):
            out.grid = GridToggles.from_dict(raw_grid)
        layer = data.get("active_layer")
        if isinstance(layer, str) and layer.strip():
            out.active_layer = layer.strip()
        if "explorer_relevant_only" in data:
            out.explorer_relevant_only = bool(data["explorer_relevant_only"])
        raw_panels = data.get("panels")
        if isinstance(raw_panels, dict):
            out.panels = {
                k: bool(v) for k, v in raw_panels.items() if isinstance(k, str)
            }
        raw_sidebar = data.get("sidebar")
        if isinstance(raw_sidebar, dict):
            for key in ("left", "right"):
                with contextlib.suppress(TypeError, ValueError):
                    if key in raw_sidebar:
                        out.sidebar[key] = float(raw_sidebar[key])
        out.extra = known_keys_stripped(data, _EDITOR_KNOWN)
        return out

    @classmethod
    def load_config(cls, path: Path) -> Self:
        """Muat ``editor.json``; default bila hilang / rusak."""
        raw = read_json_safe(path)
        if raw is None:
            return cls()
        return cls.from_dict(raw)

    def save_config(self, path: Path) -> bool:
        """Tulis ``editor.json`` secara atomik."""
        return write_json_atomic(path, self.to_dict())


class Project(plyunit.ServiceUnit):
    """Project yang sedang terbuka.

    Attributes:
        root: Root folder project (absolut).
        config: Isi ``project.json``.
        editor: Isi ``editor.json`` (state UI).
        assets: Indeks aset.
        autotiles: Pustaka autotile set.
        created: True bila scaffold baru dibuat pada pembukaan ini.
        excludes: Aturan exclude efektif (global + override project).
        scan: Hasil pemindaian terakhir; ``None`` bila belum pernah dipindai.
    """

    def __init__(self):
        super().__init__("Project", tags={"project", "service"})

        self._path_root: Path = Path("")
        self._config: ProjectConfig = ProjectConfig("No Project")
        self._editor: EditorConfig = EditorConfig()
        self._excludes: ExcludeRules = ExcludeRules()
        self._scan_result: ScanResult | None = None
        self._created = False
        self.active = False

    def on_attach(self, app: EditorApp):
        self.ctx: AppContext = app.context

    @property
    def root(self):
        return self._path_root

    @property
    def config(self):
        return self._config

    @property
    def editor(self):
        return self._editor

    @property
    def excludes(self):
        return self._excludes

    @property
    def scan_result(self):
        return self._scan_result

    @property
    def project_name(self) -> str:
        """Nama tampilan project (dari ``project.json``)."""
        return self._config.name

    @property
    def created(self) -> bool:
        """True bila scaffold ``.ply-editor/`` dibuat pada pembukaan terakhir."""
        return self._created

    def open_project(
        self,
        path: str | Path,
        *,
        global_excludes: list[str] | None = None,
        scan: bool = True,
    ):
        """Buka sebuah folder sebagai project editor.

        Membuat ``.ryeditor/`` bila belum ada, memuat konfigurasi, dan memuat
        autotile set. Pemindaian aset dapat ditunda lewat ``scan=False`` agar
        pemanggil menjalankannya di thread pekerja — startup tidak boleh diblokir
        oleh traversal folder.

        Args:
            path: Folder project.
            global_excludes: Pola exclude dari config global.
            scan: Jalankan pemindaian aset secara sinkron.

        Returns:
            :class:`Project` yang siap dipakai.

        Raises:
            ProjectError: Bila folder tidak ada, bukan direktori, atau scaffold
                tidak dapat dibuat.
        """
        # Clean
        # self.clean()

        root = Path(path).expanduser()
        try:
            root = root.resolve()
        except OSError as exc:
            raise ProjectError(f"Path project tidak dapat dibaca: {path}") from exc

        if not root.exists():
            raise ProjectError(f"Folder project tidak ada: {root}")
        if not root.is_dir():
            raise ProjectError(f"Path project bukan folder: {root}")

        last_root = self._path_root
        self._path_root = root
        try:
            config, editor, created = self.load_project_scaffold()
        except OSError as exc:
            self._path_root = last_root
            raise ProjectError(f"Gagal menyiapkan .ryeditor/ di {root}: {exc}") from exc

        if not config.name:
            config.name = root.name
            config.save_config(self.get_project_dir() / const.PROJECT_CONFIG_NAME)

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

    def load_project_scaffold(self):
        """Pastikan ``.ryeditor/`` beserta file default-nya ada.

        Dipanggil setiap kali sebuah folder dibuka sebagai project. Bila folder
        ``.ryeditor/`` belum ada, ia dibuat bersama ``project.json``,
        ``editor.json``, dan ``autotiles/``.

        Args:
            root: Root folder project.

        Returns:
            Tuple ``(project_config, editor_config, created)`` di mana ``created``
            True bila scaffold baru saja dibuat.

        Raises:
            NotADirectoryError: Bila ``root`` bukan direktori.
            OSError: Bila folder tidak dapat dibuat (mis. read-only).
        """
        if not self.root.is_dir():
            raise NotADirectoryError(f"Bukan direktori: {self.root}")

        project_dir = self.get_project_dir()
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

    def get_project_dir(self):
        """Path folder ``.ryeditor/`` di dalam project."""
        return self.root / const.PROJECT_DIR_NAME

    def save(self):
        """Save the project config and editor config"""
        project_dir = self.get_project_dir()
        self.config.save_config(project_dir / const.PROJECT_CONFIG_NAME)
        self.editor.save_config(project_dir / const.EDITOR_CONFIG_NAME)
        logger.info(f"Project save done in : {project_dir}")
