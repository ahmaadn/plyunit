"""Free functions of the raylib audio backend for the :class:`IAudioBackend`
contract."""

from __future__ import annotations

from typing import Any

import pyray as pr

_ready = False
"""Internal state: ``True`` once the audio device has been initialized."""


def init_device() -> None:
    """Initialize the raylib audio device."""
    global _ready
    pr.init_audio_device()
    _ready = pr.is_audio_device_ready()


def close_device() -> None:
    """Close the raylib audio device."""
    global _ready
    pr.close_audio_device()
    _ready = False


def is_device_ready() -> bool:
    """Return ``True`` if the audio device is ready."""
    return _ready


def set_master_volume(volume: float) -> None:
    """Set the global master volume.

    Args:
        volume: Volume value from ``0.0`` to ``1.0``.
    """
    pr.set_master_volume(volume)


def load_sound(path: str) -> Any:
    """Load an SFX from a file path.

    Args:
        path: Path to the sound file.

    Returns:
        A raw sound handle from pyray.
    """
    return pr.load_sound(path)


def unload_sound(raw: Any) -> None:
    """Unload an SFX from memory.

    Args:
        raw: Raw sound handle from :func:`load_sound`.
    """
    if raw is not None:
        pr.unload_sound(raw)


def play_sound(raw: Any, volume: float, pitch: float, pan: float) -> Any:
    """Play an SFX and return the voice handle (alias + pyray handle).

    Args:
        raw: Raw sound handle.
        volume: Sound volume.
        pitch: Sound pitch.
        pan: Sound pan/stereo position.

    Returns:
        A ``("alias", handle)`` tuple for :func:`stop_voice` and other queries.
    """
    voice = pr.load_sound_alias(raw)
    pr.set_sound_volume(voice, volume)
    pr.set_sound_pitch(voice, pitch)
    pr.set_sound_pan(voice, pan)
    pr.play_sound(voice)
    return ("alias", voice)


def stop_voice(voice_raw: Any) -> None:
    """Stop a playing SFX voice.

    Args:
        voice_raw: Voice handle from :func:`play_sound`.
    """
    kind, handle = _unpack(voice_raw)
    if handle is None:
        return
    pr.stop_sound(handle)
    if kind == "alias":
        pr.unload_sound_alias(handle)


def is_voice_playing(voice_raw: Any) -> bool:
    """Return ``True`` if an SFX voice is playing.

    Args:
        voice_raw: Voice handle from :func:`play_sound`.

    Returns:
        ``True`` if the sound is still active.
    """
    _, handle = _unpack(voice_raw)
    if handle is None:
        return False
    return pr.is_sound_playing(handle)


def set_voice_volume(voice_raw: Any, volume: float) -> None:
    """Set the volume of a playing SFX voice.

    Args:
        voice_raw: Voice handle from :func:`play_sound`.
        volume: Target volume value.
    """
    _, handle = _unpack(voice_raw)
    if handle is None:
        return
    pr.set_sound_volume(handle, volume)


def set_voice_pitch(voice_raw: Any, pitch: float) -> None:
    """Set the pitch of a playing SFX voice.

    Args:
        voice_raw: Voice handle from :func:`play_sound`.
        pitch: Target pitch value.
    """
    _, handle = _unpack(voice_raw)
    if handle is None:
        return
    pr.set_sound_pitch(handle, pitch)


def set_voice_pan(voice_raw: Any, pan: float) -> None:
    """Set the pan/stereo of a playing SFX voice.

    Args:
        voice_raw: Voice handle from :func:`play_sound`.
        pan: Target pan value (``-1.0``..``1.0``).
    """
    _, handle = _unpack(voice_raw)
    if handle is None:
        return
    pr.set_sound_pan(handle, pan)


def load_music_stream(path: str) -> Any:
    """Load a music stream (for long music such as BGM).

    Args:
        path: Path to the music file.

    Returns:
        A music stream handle from pyray.
    """
    return pr.load_music_stream(path)


def unload_music_stream(raw: Any) -> None:
    """Unload a music stream from memory.

    Args:
        raw: Music stream handle from :func:`load_music_stream`.
    """
    if raw is not None:
        pr.unload_music_stream(raw)


def play_music_stream(raw: Any) -> None:
    """Start music stream playback.

    Args:
        raw: Music stream handle.
    """
    pr.play_music_stream(raw)


def stop_music_stream(raw: Any) -> None:
    """Stop music stream playback.

    Args:
        raw: Music stream handle.
    """
    pr.stop_music_stream(raw)


def pause_music_stream(raw: Any) -> None:
    """Pause music stream playback.

    Args:
        raw: Music stream handle.
    """
    pr.pause_music_stream(raw)


def resume_music_stream(raw: Any) -> None:
    """Resume paused music stream playback.

    Args:
        raw: Music stream handle.
    """
    pr.resume_music_stream(raw)


def update_music_stream(raw: Any) -> None:
    """Tick the music stream buffer decoder (call every frame).

    Args:
        raw: Music stream handle.
    """
    pr.update_music_stream(raw)


def is_music_stream_playing(raw: Any) -> bool:
    """Return ``True`` if a music stream is playing.

    Args:
        raw: Music stream handle.

    Returns:
        The music stream playback status.
    """
    return pr.is_music_stream_playing(raw)


def set_music_volume(raw: Any, volume: float) -> None:
    """Set the music stream volume.

    Args:
        raw: Music stream handle.
        volume: Volume value (``0.0`` to ``1.0``).
    """
    pr.set_music_volume(raw, volume)


def set_music_looping(raw: Any, loop: bool) -> None:
    """Set the looping mode of a music stream.

    Args:
        raw: Music stream handle.
        loop: ``True`` to loop, ``False`` to play once.
    """
    raw.looping = loop


def _unpack(voice_raw: Any) -> tuple[str | None, Any]:
    """Unpack a voice handle tuple from :func:`play_sound`.

    Args:
        voice_raw: The SFX voice handle.

    Returns:
        A ``(kind, handle)`` tuple.

    Raises:
        TypeError: If ``voice_raw`` is not a 2-element tuple from :func:`play_sound`.
    """
    if not isinstance(voice_raw, tuple) or len(voice_raw) != 2:
        raise TypeError("voice handle must be a (kind, handle) tuple from play_sound")
    return str(voice_raw[0]), voice_raw[1]
