"""Application-wide constants for the editor."""

from pathlib import Path
from typing import Final

# Application
# ---------------------------------------------

APP_NAME: Final = "ply-editor"

PROJECT_DIR_NAME: Final = ".ply-editor"
"""Editor scaffold folder created inside every opened project."""

PROJECT_CONFIG_NAME: Final = "project.json"
EDITOR_CONFIG_NAME: Final = "editor.json"
AUTOTILE_DIR_NAME: Final = "autotiles"

MAX_RECENT_PROJECTS: Final = 20

# Config schema versions
PROJECT_CONFIG_VERSION: Final = 1
EDITOR_CONFIG_VERSION: Final = 1
GLOBAL_CONFIG_VERSION: Final = 1

# Window / camera
# ---------------------------------------------

WINDOW_WIDTH: Final = 1280
WINDOW_HEIGHT: Final = 800

CAMERA_VIRTUAL_WIDTH: Final = 640
CAMERA_VIRTUAL_HEIGHT: Final = 400

FPS: Final = 60

# Editor canvas
# ---------------------------------------------

GRID_HIDE_ZOOM: Final = 0.55
"""Zoom level below which the tile grid is hidden (zoomed out too far)."""

CHUNK_GRID_HIDE_ZOOM: Final = 0.35
"""Zoom level below which the chunk grid is hidden."""

PAN_SPEED: Final = 600.0
"""Camera pan speed (pixels per second) when driven by the keyboard."""

# Font
# ---------------------------------------------

DATA_PATH: Final = Path(__file__).parent.parent / "data"
FONT_PATH: Final = DATA_PATH / "fonts" / "Roboto-Regular.ttf"
FONT_ICON_PATH: Final = DATA_PATH / "fonts" / "fa-solid-900.ttf"
FONT_SIZE: Final = 18

# Folder scanning
# ---------------------------------------------

ALWAYS_EXCLUDED: Final[tuple[str, ...]] = (PROJECT_DIR_NAME, ".git")
"""Patterns that are always active and cannot be disabled by the user."""

DEFAULT_EXCLUDES: Final[tuple[str, ...]] = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    ".env",
    "node_modules",
    "__pycache__",
    ".dist",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "*.egg-info",
    ".idea",
    ".vscode",
)

IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (".png", ".jpg", ".jpeg")
"""Image file extensions indexed by the asset scan."""

FONT_EXTENSIONS: Final[tuple[str, ...]] = (".ttf", ".otf")
"""Font file extensions indexed by the asset scan."""

AUDIO_EXTENSIONS: Final[tuple[str, ...]] = (".wav", ".ogg", ".mp3", ".flac")
"""Audio file extensions indexed by the asset scan."""

# Map config
# ---------------------------------------------

MAP_SUFFIX: Final = ".json"
"""File extension of map candidates (and asset sidecars)."""

MAP_PROBE_BYTES: Final = 4096
"""Number of leading bytes read from a JSON file to guess its kind."""

JOIN_TIMEOUT: Final = 5.0
"""Seconds to wait for the scan thread when shutting down mid-scan."""

# Default map settings
DEFAULT_TILE_SIZE: Final = 16
DEFAULT_CHUNK_SIZE: Final = 16
DEFAULT_ENCODING: Final = "base64_zlib"
DEFAULT_MAP_TYPE: Final = "orthogonal"
MAP_VERSION: Final = "2.0"

LAYER_BASE: Final = "1"
"""The base layer that is always present on every map."""


# Batas zoom kamera editor
ZOOM_MIN: Final[float] = 0.25
ZOOM_MAX: Final[float] = 8.0
ZOOM_STEP: Final[float] = 0.1


COLOR_BG: Final[tuple[int, int, int, int]] = (30, 30, 34, 255)
# High alpha so the grid is visible against the dark background
COLOR_GRID: Final[tuple[int, int, int, int]] = (90, 95, 110, 180)
COLOR_GRID_CHUNK: Final[tuple[int, int, int, int]] = (150, 155, 175, 220)
COLOR_GRID_ORIGIN: Final[tuple[int, int, int, int]] = (255, 100, 100, 230)
COLOR_CURSOR: Final[tuple[int, int, int, int]] = (100, 200, 255, 200)
COLOR_CURSOR_ERASE: Final[tuple[int, int, int, int]] = (255, 100, 100, 200)
COLOR_SELECTION: Final[tuple[int, int, int, int]] = (255, 220, 80, 180)
COLOR_PREVIEW: Final[tuple[int, int, int, int]] = (255, 255, 255, 140)
COLOR_ORIGIN_AXIS: Final[tuple[int, int, int, int]] = (255, 80, 80, 255)

COLOR_PANEL: Final[tuple[int, int, int, int]] = (24, 24, 28, 235)
COLOR_PANEL_HEADER: Final[tuple[int, int, int, int]] = (40, 40, 48, 255)
COLOR_TEXT: Final[tuple[int, int, int, int]] = (220, 220, 225, 255)
COLOR_TEXT_DIM: Final[tuple[int, int, int, int]] = (150, 150, 160, 255)
COLOR_ACCENT: Final[tuple[int, int, int, int]] = (100, 185, 255, 255)
COLOR_ACCENT_DIM: Final[tuple[int, int, int, int]] = (100, 185, 255, 80)
COLOR_DANGER: Final[tuple[int, int, int, int]] = (255, 90, 90, 255)
COLOR_SUCCESS: Final[tuple[int, int, int, int]] = (90, 220, 120, 255)
COLOR_WARNING: Final[tuple[int, int, int, int]] = (255, 190, 80, 255)

# Overlay collision & object marker
COLOR_COLLISION: Final[tuple[int, int, int, int]] = (255, 120, 60, 150)
COLOR_COLLIDER: Final[tuple[int, int, int, int]] = (255, 120, 60, 190)
COLOR_OBJECT_DEFAULT: Final[tuple[int, int, int, int]] = (200, 200, 210, 220)
COLOR_OBJECT_MARKER: Final[tuple[int, int, int, int]] = (120, 220, 160, 230)
COLOR_OBJECT_SELECTED: Final[tuple[int, int, int, int]] = (255, 220, 80, 255)
COLOR_ORIGIN_AXIS_Y: Final[tuple[int, int, int, int]] = (80, 255, 120, 255)

COLOR_REGION: tuple[int, int, int, int] = (120, 220, 160, 200)
COLOR_BACKDROP: tuple[int, int, int, int] = (18, 18, 22, 255)
COLOR_REGION_NAME_BG: tuple[int, int, int, int] = (18, 18, 22, 200)
COLOR_REGION_NAME: tuple[int, int, int, int] = (255, 255, 255, 230)


REGION_NAME_FONT_SIZE: int = 8
"""Font size for region names in image pixels; shrinks when zooming out."""

REGION_NAME_PADDING: float = 1.0
"""Padding between the region name and the edge of its box."""
