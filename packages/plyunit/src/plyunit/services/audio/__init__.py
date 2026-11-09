"""Portable audio schemas, playback identifiers, and 2D spatial math.

Device and native resource ownership are implemented by audio integrations.
Audio is resolved lazily through the public facade; importing this package
never imports or selects a backend.
"""

from typing import TYPE_CHECKING

from ._types import SoundBankConfig, SoundBankEntry, VoiceId
from .spatial import compute_spatial

if TYPE_CHECKING:
    from plyunit.backends.integrations import Audio as Audio

__all__ = ["Audio", "SoundBankConfig", "SoundBankEntry", "VoiceId", "compute_spatial"]


def __getattr__(name: str):
    if name != "Audio":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends.integrations import Audio

    globals()[name] = Audio
    return Audio
