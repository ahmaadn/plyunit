"""Audio device, SFX, and music stream contracts for the host backend.

This module defines :class:`IAudioBackend` — the protocol every audio
backend must satisfy. Backends implement it and expose it as
``AudioBackend``. Domain code treats it as the stable surface for device
init, sound/music loading, voice playback, and volume/pitch/pan control.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IAudioBackend(Protocol):
    """
    Backend ops for device, sounds, and music streams
    (injected; default = raylib).
    """

    def init_device(self) -> None:
        """Initialize the audio device."""
        ...

    def close_device(self) -> None:
        """Close the audio device and release its resources."""
        ...

    def is_device_ready(self) -> bool:
        """Check whether the audio device is initialized and ready.

        Returns:
            True if the device is ready.
        """
        ...

    def set_master_volume(self, volume: float) -> None:
        """Set the master output volume.

        Args:
            volume: Master volume (0.0..1.0).
        """
        ...

    def load_sound(self, path: str) -> Any:
        """Load a sound effect from an audio file.

        Args:
            path: Sound file path.

        Returns:
            The backend sound handle.
        """
        ...

    def unload_sound(self, raw: Any) -> None:
        """Unload a sound effect and free its memory.

        Args:
            raw: Sound handle to unload.
        """
        ...

    def play_sound(self, raw: Any, volume: float, pitch: float, pan: float) -> Any:
        """Play a sound effect as a new voice.

        Args:
            raw: Sound handle to play.
            volume: Voice volume (0.0..1.0).
            pitch: Pitch multiplier (1.0 = normal).
            pan: Stereo pan (-1.0 left .. 1.0 right).

        Returns:
            The backend voice handle.
        """
        ...

    def stop_voice(self, voice_raw: Any) -> None:
        """Stop a playing voice.

        Args:
            voice_raw: Voice handle to stop.
        """
        ...

    def is_voice_playing(self, voice_raw: Any) -> bool:
        """Check whether a voice is still playing.

        Args:
            voice_raw: Voice handle to check.

        Returns:
            True if the voice is playing.
        """
        ...

    def set_voice_volume(self, voice_raw: Any, volume: float) -> None:
        """Set the volume of a playing voice.

        Args:
            voice_raw: Voice handle to adjust.
            volume: Target volume (0.0..1.0).
        """
        ...

    def set_voice_pitch(self, voice_raw: Any, pitch: float) -> None:
        """Set the pitch of a playing voice.

        Args:
            voice_raw: Voice handle to adjust.
            pitch: Pitch multiplier (1.0 = normal).
        """
        ...

    def set_voice_pan(self, voice_raw: Any, pan: float) -> None:
        """Set the stereo pan of a playing voice.

        Args:
            voice_raw: Voice handle to adjust.
            pan: Stereo pan (-1.0 left .. 1.0 right).
        """
        ...

    def load_music_stream(self, path: str) -> Any:
        """Load a music stream from an audio file.

        Args:
            path: Music file path.

        Returns:
            The backend music stream handle.
        """
        ...

    def unload_music_stream(self, raw: Any) -> None:
        """Unload a music stream and free its resources.

        Args:
            raw: Music stream handle to unload.
        """
        ...

    def play_music_stream(self, raw: Any) -> None:
        """Start playing a music stream.

        Args:
            raw: Music stream handle to play.
        """
        ...

    def stop_music_stream(self, raw: Any) -> None:
        """Stop a playing music stream.

        Args:
            raw: Music stream handle to stop.
        """
        ...

    def pause_music_stream(self, raw: Any) -> None:
        """Pause a playing music stream.

        Args:
            raw: Music stream handle to pause.
        """
        ...

    def resume_music_stream(self, raw: Any) -> None:
        """Resume a paused music stream.

        Args:
            raw: Music stream handle to resume.
        """
        ...

    def update_music_stream(self, raw: Any) -> None:
        """Advance a music stream's internal buffers; call once per frame.

        Args:
            raw: Music stream handle to update.
        """
        ...

    def is_music_stream_playing(self, raw: Any) -> bool:
        """Check whether a music stream is playing.

        Args:
            raw: Music stream handle to check.

        Returns:
            True if the stream is playing.
        """
        ...

    def set_music_volume(self, raw: Any, volume: float) -> None:
        """Set the volume of a music stream.

        Args:
            raw: Music stream handle to adjust.
            volume: Target volume (0.0..1.0).
        """
        ...

    def set_music_looping(self, raw: Any, loop: bool) -> None:
        """Enable or disable looping of a music stream.

        Args:
            raw: Music stream handle to adjust.
            loop: True to loop.
        """
        ...


__all__ = ["IAudioBackend"]
