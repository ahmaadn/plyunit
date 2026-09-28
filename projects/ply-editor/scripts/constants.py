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
