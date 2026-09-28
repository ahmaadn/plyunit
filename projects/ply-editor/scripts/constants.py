from pathlib import Path
from typing import Final

# Project
# ---------------------------------------------
APP_NAME: Final = "ply-editor"

PROJECT_DIR_NAME: Final = ".ply-editor"
PROJECT_CONFIG_NAME: Final = "project.json"
EDITOR_CONFIG_NAME: Final = "editor.json"
AUTOTILE_DIR_NAME: Final = "autotiles"

MAX_RECENT_PROJECTS = 20

# VERSION
# ---------------------------------------------
PROJECT_CONFIG_VERSION: Final = 1
EDITOR_CONFIG_VERSION: Final = 1
GLOBAL_CONFIG_VERSION: Final = 1


# Windows
# ---------------------------------------------
CAMERA_VIRTUAL_WIDTH: Final = 640
CAMERA_VIRTUAL_HEIGHT: Final = 400

WINDOW_WIDTH: Final = 1280
WINDOW_HEIGHT: Final = 800

FPS: Final = 60

# EDITOR
# ---------------------------------------------
# Di bawah ini grid tile disembunyikan (zoom-out terlalu jauh)
GRID_HIDE_ZOOM: Final = 0.55
# Chunk grid disembunyikan di zoom lebih rendah
CHUNK_GRID_HIDE_ZOOM: Final = 0.35

# Kecepatan pan kamera (pixel / detik) saat memakai keyboard
PAN_SPEED: Final = 600.0

# FONT
# ---------------------------------------------
DATA_PATH = Path(__file__).parent.parent / "data"
FONT_PATH = DATA_PATH / "fonts" / "Roboto-Regular.ttf"
FONT_SIZE = 18

# FOLDER SCAN
# ---------------------------------------------
ALWAYS_EXCLUDED: tuple[str, ...] = (PROJECT_DIR_NAME, ".git")
"""Pola yang selalu aktif dan tidak dapat dimatikan pengguna."""

DEFAULT_EXCLUDES: tuple[str, ...] = (
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

IMAGE_EXTENSIONS: Final = (".png", ".jpg", ".jpeg")
"""Ekstensi gambar yang dipindai asset index."""
FONT_EXTENSIONS: Final = (".tff", ".otf")
"""Ekstensi font yang dipindai sebagai font"""
AUDIO_EXTENSIONS: Final = (".wav", ",.ogg", ".mp3", ".flac")
"""Eksrensi audio yang dipindai sebagai audio"""

# MAP CONFIG
# ---------------------------------------------
MAP_SUFFIX = ".json"
"""Ekstensi file kandidat map (dan sidecar aset)."""

MAP_PROBE_BYTES = 4096
"""Jumlah byte awal file JSON yang dibaca untuk menebak apakah ia map."""

JOIN_TIMEOUT = 5.0
"""Batas tunggu saat menutup aplikasi di tengah pemindaian (detik)."""

# Default map settings
DEFAULT_TILE_SIZE: Final = 16
DEFAULT_CHUNK_SIZE: Final = 16
DEFAULT_ENCODING: Final = "base64_zlib"
DEFAULT_MAP_TYPE: Final = "orthogonal"
MAP_VERSION: Final = "2.0"

# Kosong: chunk tile kosong panjang chunk_size * chunk_size
# Layer default yang selalu tersedia
LAYER_BASE: Final = "1"


__all__ = (
    "CAMERA_VIRTUAL_HEIGHT",
    "CAMERA_VIRTUAL_WIDTH",
    "WINDOW_HEIGHT",
    "WINDOW_WIDTH",
)
