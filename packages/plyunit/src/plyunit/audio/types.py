"""Shared data types for the plyunit audio module.

Contains ``VoiceId`` (a newtype for backend voice IDs) and TypedDicts for
JSON sound bank configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NewType, TypedDict

#: NewType for backend audio voice IDs. Wrapped around ``int`` so it can be
#: used as a dict key and compared with ``==`` without overhead.
VoiceId = NewType("VoiceId", int)


@dataclass(slots=True)
class SoundEntry:
    """Internal record for one loaded sound."""

    raw: Any
    path: Path
    default_volume: float = 1.0
    group: str | None = None


@dataclass(slots=True)
class MusicEntry:
    """Internal record for one loaded music stream."""

    raw: Any
    path: Path
    default_volume: float = 1.0
    default_loop: bool = True
    group: str | None = None


@dataclass(slots=True)
class VoiceRecord:
    """Internal record for one active voice."""

    voice_id: VoiceId
    voice_raw: Any
    sound_id: str
    instance_volume: float
    pitch: float
    pan: float
    tracked: bool = False
    x: float = 0.0
    y: float = 0.0


class SoundBankEntry(TypedDict, total=False):
    """A single entry in ``SoundBankConfig.entries``.

    Attributes:
        id: Unique entry ID (e.g. ``"shoot"``, ``"bgm_menu"``).
        path: Path relative to the sound bank's ``base_path``.
        kind: ``"sound"`` for SFX or ``"music"`` for a stream.
        volume: Default entry volume (0.0-1.0+).
        loop: Whether the music stream loops automatically (default ``True``).
        group: Optional logical group for batch volume control.
    """

    id: str
    path: str
    kind: Literal["sound", "music"]
    volume: float
    loop: bool
    group: str


class SoundBankConfig(TypedDict, total=False):
    """JSON sound bank schema loaded by ``Audio.load_bank``.

    Attributes:
        id: Bank ID; if absent, the file name is used.
        base_path: Relative base path for all entries in the bank.
        entries: List of sound/music entries to load.
    """

    id: str
    base_path: str
    entries: list[SoundBankEntry]
