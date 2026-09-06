"""Audio module — engine-level service + lazy backend dispatch.

Engine-level names (``Audio``, ``IAudioBackend``, ``VoiceId``, ``SoundBank*``,
``compute_spatial``) are imported directly because they do not depend on any
particular backend. Backend-specific names (``RaylibAudioBackend``,
``build_audio_service``) are resolved via ``__getattr__`` from the active backend.

Examples:
    >>> from plyunit.audio import Audio, IAudioBackend     # engine-level
    >>> from plyunit.audio import RaylibAudioBackend              # backend-specific
"""

from __future__ import annotations

from plyunit.audio.service import Audio
from plyunit.audio.spatial import compute_spatial
from plyunit.audio.types import SoundBankConfig, SoundBankEntry, VoiceId
from plyunit.backends.integrations import AudioBackend, audio_backend, get_audio_backend
from plyunit.backends.interfaces import IAudioBackend

__all__ = [
    "Audio",
    "AudioBackend",
    "IAudioBackend",
    "SoundBankConfig",
    "SoundBankEntry",
    "VoiceId",
    "audio_backend",
    "compute_spatial",
    "get_audio_backend",
]
