"""Portable voice identifiers and JSON sound-bank schemas.

Native sound, music, and alias ownership belongs to the audio integration,
not to these backend-independent service types.
"""

from __future__ import annotations

from typing import Literal, NewType, TypedDict

VoiceId = NewType("VoiceId", int)
"""Opaque playback identifier, unique within one audio service's lifetime."""


class SoundBankEntry(TypedDict, total=False):
    """A single entry in ``SoundBankConfig.entries``.

    Attributes:
        id: Unique entry ID (e.g. ``"shoot"``, ``"bgm_menu"``).
        path: Path relative to the sound bank's ``base_path``.
        kind: ``"sound"`` for SFX or ``"music"`` for a stream.
        volume: Default entry volume (0.0-1.0+).
        loop: Whether the music stream loops automatically (default ``True``).
        group: Optional metadata label; it does not define a separate volume bus.
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
