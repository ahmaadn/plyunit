from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from plyunit.tilemap.encoding import ENCODER_REGISTRY
from scripts import constants as const
from scripts.core.exclude import normalize_patterns

if TYPE_CHECKING:
    from plyunit.core.types import ColorType

logger = logging.getLogger(__name__)


@dataclass
class MapDefaults:
    """Default settings applied to newly created maps.

    Attributes:
        tile_size: Default tile size ``(width, height)`` in pixels.
        chunk_size: Default chunk size in tiles.
        encoding: Default tile-data encoding name.
        background_color: Default background RGBA color.
    """

    tile_size: tuple[int, int] = (const.DEFAULT_TILE_SIZE, const.DEFAULT_TILE_SIZE)
    chunk_size: int = const.DEFAULT_CHUNK_SIZE
    encoding: str = const.DEFAULT_ENCODING
    background_color: ColorType = (20, 20, 30, 255)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {
            "tile_size": list(self.tile_size),
            "chunk_size": self.chunk_size,
            "encoding": self.encoding,
            "background_color": list(self.background_color),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build from a dict, tolerating missing or mistyped fields."""
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
    """Contents of ``project.json``.

    Attributes:
        name: Project display name.
        version: Schema version of the file.
        assets_root: Root folder of game assets, relative to the
            project root.
        defaults: Default settings for new maps.
        exclude_folders: Per-project scan exclude patterns.
        exclude_override: When True, ``exclude_folders`` replaces the
            global exclude list instead of merging with it.
        extra: Unknown keys, preserved across rewrites.
    """

    name: str
    version: int = const.PROJECT_CONFIG_VERSION
    assets_root: str = "/data"
    defaults: MapDefaults = field(default_factory=MapDefaults)
    exclude_folders: list[str] = field(default_factory=list)
    exclude_override: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation (extras first)."""
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
        """Build from a dict, tolerating missing or mistyped fields."""
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
        out.extra = {k: v for k, v in data.items() if k not in _PROJECT_KNOWN}

        return out


@dataclass(slots=True)
class CameraState:
    """Editor camera position and zoom, restored per project."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {"x": self.x, "y": self.y, "zoom": self.zoom}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build from a dict, tolerating missing or mistyped fields."""
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
    """Canvas overlay toggles.

    Attributes:
        tile: Show the tile grid.
        chunk: Show the chunk grid.
        origin: Show the map origin.
        collision: Show collision overlays.
        objects: Show object gizmos.
    """

    tile: bool = True
    chunk: bool = True
    origin: bool = True
    collision: bool = False
    objects: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {
            "tile": self.tile,
            "chunk": self.chunk,
            "origin": self.origin,
            "collision": self.collision,
            "objects": self.objects,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build from a dict, tolerating missing or mistyped fields."""
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
    """Contents of ``.ply-editor/editor.json`` — per-project UI state.

    Attributes:
        version: Schema version of the file.
        last_open: Path of the last opened map, relative to the
            project root.
        open_list: Maps open as tabs, relative to the project root.
        camera: Camera position and zoom.
        grid: Overlay toggles.
        active_layer: Last active layer name.
        explorer_relevant_only: Last state of the explorer's
            "Editor files only" toggle.
        panels: Panel open/close state (panel name -> bool).
        sidebar: Left/right sidebar widths in pixels.
        extra: Unknown keys, preserved across rewrites.
    """

    version: int = const.EDITOR_CONFIG_VERSION
    last_open: str | None = None
    open_list: list[str] = field(default_factory=list)
    camera: CameraState = field(default_factory=CameraState)
    grid: GridToggles = field(default_factory=GridToggles)
    active_layer: str = const.LAYER_BASE
    explorer_relevant_only: bool = False
    panels: dict[str, bool] = field(default_factory=dict)
    sidebar: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation (extras first)."""
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
        """Build from a dict, tolerating missing or mistyped fields."""
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
        out.extra = {k: v for k, v in data.items() if k not in _EDITOR_KNOWN}
        return out


__all__ = [
    "CameraState",
    "EditorConfig",
    "GridToggles",
    "MapDefaults",
    "ProjectConfig",
]
