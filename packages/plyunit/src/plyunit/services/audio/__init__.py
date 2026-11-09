"""Portable audio schemas, playback identifiers, and 2D spatial math.

Device and native resource ownership are implemented by audio integrations.
This package does not import or select a backend.
"""

from ._types import SoundBankConfig, SoundBankEntry, VoiceId
from .spatial import compute_spatial

__all__ = ["SoundBankConfig", "SoundBankEntry", "VoiceId", "compute_spatial"]
