"""Scan result model: the dataclasses returned by a project folder walk.

These are pure data; the actual disk traversal lives in
:mod:`scripts.services.scan`. :class:`ScanEntry` describes one
file, and :class:`ScanResult` collects every file the walk found,
grouped by :func:`~scripts.services.scan.classify_json` kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scripts import constants as const

JSONKind = str
"""Return type of :func:`classify_json`: one of the kind names below."""

JSON_KIND_MAP = "map"
JSON_KIND_ANIMATION = "animation"
JSON_KIND_IMAGE_CONFIG = "image_config"
JSON_KIND_OTHER = "other"


@dataclass(slots=True)
class ScanEntry:
    """One file found by a scan.

    Attributes:
        path: Absolute file path.
        relative: Path relative to the scan root, posix separators.
        suffix: Lowercase extension including the dot.
    """

    path: Path
    relative: str
    suffix: str

    @property
    def is_image(self) -> bool:
        """True when the file is an image."""
        return self.suffix in const.IMAGE_EXTENSIONS

    @property
    def is_json(self) -> bool:
        """True when the file is a JSON candidate (map or sidecar)."""
        return self.suffix == const.MAP_SUFFIX

    @property
    def is_font(self) -> bool:
        """True when the file is a font."""
        return self.suffix in const.FONT_EXTENSIONS

    @property
    def is_audio(self) -> bool:
        """True when the file is audio."""
        return self.suffix in const.AUDIO_EXTENSIONS


@dataclass(slots=True)
class ScanResult:
    """Result of one project scan.

    Attributes:
        audio: Audio files found.
        animations: Animation config files found.
        fonts: Font files found.
        images: Image files found.
        image_configs: JSON files that look like image/sidecar configs.
        json_files: All ``.json`` files (map and asset candidates).
        maps: ``.json`` files whose structure resembles a map.
        other: Other files that passed the excludes; used by the
            "show all" tree mode.
        directories: Folders actually walked (relative, posix).
        pruned: Folders skipped because they were excluded.
        cancelled: True when the scan stopped before finishing.
    """

    audio: list[ScanEntry] = field(default_factory=list)
    animations: list[ScanEntry] = field(default_factory=list)
    fonts: list[ScanEntry] = field(default_factory=list)
    images: list[ScanEntry] = field(default_factory=list)
    image_configs: list[ScanEntry] = field(default_factory=list)
    json_files: list[ScanEntry] = field(default_factory=list)
    maps: list[ScanEntry] = field(default_factory=list)
    other: list[ScanEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def file_count(self) -> int:
        """Total number of files found."""
        # json_files already covers maps, animations, image_configs.
        return (
            len(self.images)
            + len(self.json_files)
            + len(self.other)
            + len(self.fonts)
            + len(self.audio)
        )


__all__ = [
    "JSON_KIND_ANIMATION",
    "JSON_KIND_IMAGE_CONFIG",
    "JSON_KIND_MAP",
    "JSON_KIND_OTHER",
    "JSONKind",
    "ScanEntry",
    "ScanResult",
]
