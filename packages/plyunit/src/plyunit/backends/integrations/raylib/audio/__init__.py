"""Raylib audio backend — module of free functions + thin class wrapper.

The module-level functions implement ``IAudioBackend`` for the new Protocol
contract. ``RaylibAudioBackend`` is a class wrapper that exposes the same
functions as methods (legacy test API surface).
"""

from __future__ import annotations

from plyunit.backends.interfaces import IAudioBackend

from . import backend


def AudioBackend() -> IAudioBackend:
    """Factory: return the active audio backend module (per :class:`IAudioBackend`)."""
    return backend


def get_audio_backend() -> IAudioBackend:
    """Alias factory for the active audio backend module."""
    return backend


audio_backend: IAudioBackend = backend


__all__ = ["AudioBackend", "audio_backend", "backend", "get_audio_backend"]
