"""Stateful pyray test double that enforces native audio resource ownership."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass(eq=False)
class FakeSound:
    """Model a source sound or an independently playable alias.

    Attributes:
        source: Sample owner for aliases, or ``None`` for a source sound.
        valid: Whether loading succeeded.
        unloaded: Whether its buffer has been released.
        playing: Whether this buffer is currently playing.
        volume: Native per-buffer gain, before the device master bus.
        pitch: Pitch multiplier.
        pan: Native stereo pan value.
    """

    source: FakeSound | None = None
    valid: bool = True
    unloaded: bool = False
    playing: bool = False
    volume: float = 1.0
    pitch: float = 1.0
    pan: float = 0.0


@dataclass(eq=False)
class FakeMusic:
    """Model a native music decoder and its playback state.

    Attributes:
        valid: Whether decoding succeeded.
        unloaded: Whether the decoder and stream were released.
        playing: Whether playback is active.
        looping: Whether the stream loops.
        volume: Native stream gain before the device master bus.
    """

    valid: bool = True
    unloaded: bool = False
    playing: bool = False
    looping: bool = True
    volume: float = 1.0


class FakeRaylib:
    """Implement pyray audio calls with strict use-after-release checks.

    Tests patch the integration's ``pr`` module with this object. It is not an
    injected engine backend and deliberately exposes only native call names.
    """

    def __init__(self) -> None:
        """Initialize an unopened device and empty resource/call registries."""
        self.RAYLIB_VERSION_MAJOR = 6
        self.ready = False
        self.master = 1.0
        self.sounds: dict[str, FakeSound] = {}
        self.music: dict[str, FakeMusic] = {}
        self.aliases: list[FakeSound] = []
        self.calls: list[tuple[Any, ...]] = []
        self.updated: list[FakeMusic] = []
        self.failures: dict[str, Exception] = {}
        self.invalid_sound = False
        self.invalid_music = False
        self.invalid_alias = False
        self.init_succeeds = True
        self.finish_music_on_update = False
        self.init_calls = 0
        self.close_calls = 0

    def _call(self, name: str, *args: Any) -> None:
        """Record a native operation and apply configured failures.

        Args:
            name: Native call name.
            *args: Arguments passed to the native operation.

        Raises:
            AssertionError: If an operation needs an unopened device.
            Exception: The failure configured by a test for this call.
        """
        self.calls.append((name, *args))
        if name not in ("init_audio_device", "close_audio_device"):
            assert self.ready, f"{name} called with no live audio device"
        if name in self.failures:
            raise self.failures[name]

    def _sound(self, raw: FakeSound) -> None:
        """Validate that a sound or alias still has a live sample owner.

        Args:
            raw: Sound to validate.
        """
        assert self.ready
        assert not raw.unloaded, "sound/alias used after unload"
        if raw.source is not None:
            assert not raw.source.unloaded, "alias used after its samples were unloaded"

    def _music(self, raw: FakeMusic) -> None:
        """Validate that a music stream has not been released.

        Args:
            raw: Music stream to validate.
        """
        assert self.ready
        assert not raw.unloaded, "music stream used after unload"

    def init_audio_device(self) -> None:
        """Open the fake device unless initialization is configured to fail."""
        self._call("init_audio_device")
        self.init_calls += 1
        self.ready = self.init_succeeds

    def close_audio_device(self) -> None:
        """Close the fake device."""
        self._call("close_audio_device")
        self.close_calls += 1
        self.ready = False

    def is_audio_device_ready(self) -> bool:
        """Return the current native device state."""
        return self.ready

    def set_master_volume(self, volume: float) -> None:
        """Set native device gain.

        Args:
            volume: Master gain.
        """
        self._call("set_master_volume", volume)
        self.master = volume

    def load_sound(self, path: str) -> FakeSound:
        """Create a source sample buffer.

        Args:
            path: Sound asset path.

        Returns:
            The loaded fake source sound.
        """
        self._call("load_sound", path)
        raw = FakeSound(valid=not self.invalid_sound)
        self.sounds[path] = raw
        return raw

    def is_sound_valid(self, raw: FakeSound) -> bool:
        """Check whether a source or alias loaded successfully.

        Args:
            raw: Sound or alias to inspect.

        Returns:
            Whether the native handle is valid.
        """
        return raw.valid and not raw.unloaded

    def unload_sound(self, raw: FakeSound) -> None:
        """Release source samples only after every alias is released.

        Args:
            raw: Source sound owning the samples.
        """
        self._sound(raw)
        assert raw.source is None, "alias must use unload_sound_alias"
        assert not any(
            alias.source is raw and not alias.unloaded for alias in self.aliases
        )
        self._call("unload_sound", raw)
        raw.unloaded = True

    def load_sound_alias(self, raw: FakeSound) -> FakeSound:
        """Create independent playback sharing a live source's samples.

        Args:
            raw: Source sound.

        Returns:
            A new alias buffer.
        """
        self._sound(raw)
        self._call("load_sound_alias", raw)
        alias = FakeSound(source=raw, valid=not self.invalid_alias)
        self.aliases.append(alias)
        return alias

    def unload_sound_alias(self, raw: FakeSound) -> None:
        """Release an alias without freeing its source's samples.

        Args:
            raw: Alias buffer to release.
        """
        self._sound(raw)
        assert raw.source is not None
        self._call("unload_sound_alias", raw)
        raw.unloaded = True
        raw.playing = False

    def play_sound(self, raw: FakeSound) -> None:
        """Start one alias.

        Args:
            raw: Alias buffer.
        """
        self._sound(raw)
        assert raw.source is not None, "one-shots must play an alias"
        self._call("play_sound", raw)
        raw.playing = True

    def stop_sound(self, raw: FakeSound) -> None:
        """Stop one alias without releasing it.

        Args:
            raw: Alias buffer.
        """
        self._sound(raw)
        self._call("stop_sound", raw)
        raw.playing = False

    def is_sound_playing(self, raw: FakeSound) -> bool:
        """Inspect one live alias's playback state.

        Args:
            raw: Alias buffer.

        Returns:
            Whether it is playing.
        """
        self._sound(raw)
        self._call("is_sound_playing", raw)
        return raw.playing

    def set_sound_volume(self, raw: FakeSound, volume: float) -> None:
        """Set per-alias gain.

        Args:
            raw: Alias buffer.
            volume: Per-buffer gain.
        """
        self._sound(raw)
        self._call("set_sound_volume", raw, volume)
        raw.volume = volume

    def set_sound_pitch(self, raw: FakeSound, pitch: float) -> None:
        """Set per-alias pitch.

        Args:
            raw: Alias buffer.
            pitch: Pitch multiplier.
        """
        self._sound(raw)
        self._call("set_sound_pitch", raw, pitch)
        raw.pitch = pitch

    def set_sound_pan(self, raw: FakeSound, pan: float) -> None:
        """Set native stereo pan.

        Args:
            raw: Alias buffer.
            pan: Native raylib pan value.
        """
        self._sound(raw)
        self._call("set_sound_pan", raw, pan)
        raw.pan = pan

    def load_music_stream(self, path: str) -> FakeMusic:
        """Create a music decoder and stream.

        Args:
            path: Music asset path.

        Returns:
            The fake music handle.
        """
        self._call("load_music_stream", path)
        raw = FakeMusic(valid=not self.invalid_music)
        self.music[path] = raw
        return raw

    def is_music_valid(self, raw: FakeMusic) -> bool:
        """Check whether a decoder loaded successfully.

        Args:
            raw: Music stream.

        Returns:
            Whether it is valid.
        """
        return raw.valid and not raw.unloaded

    def set_music_volume(self, raw: FakeMusic, volume: float) -> None:
        """Set native stream gain.

        Args:
            raw: Music stream.
            volume: Per-stream gain before the master bus.
        """
        self._music(raw)
        self._call("set_music_volume", raw, volume)
        raw.volume = volume

    def unload_music_stream(self, raw: FakeMusic) -> None:
        """Release a music stream and decoder.

        Args:
            raw: Stream to release.
        """
        self._music(raw)
        self._call("unload_music_stream", raw)
        raw.unloaded = True
        raw.playing = False

    def play_music_stream(self, raw: FakeMusic) -> None:
        """Start music playback.

        Args:
            raw: Music stream.
        """
        self._music(raw)
        self._call("play_music_stream", raw)
        raw.playing = True

    def stop_music_stream(self, raw: FakeMusic) -> None:
        """Stop music playback.

        Args:
            raw: Music stream.
        """
        self._music(raw)
        self._call("stop_music_stream", raw)
        raw.playing = False

    def pause_music_stream(self, raw: FakeMusic) -> None:
        """Pause music playback.

        Args:
            raw: Music stream.
        """
        self._music(raw)
        self._call("pause_music_stream", raw)
        raw.playing = False

    def resume_music_stream(self, raw: FakeMusic) -> None:
        """Resume paused music.

        Args:
            raw: Music stream.
        """
        self._music(raw)
        self._call("resume_music_stream", raw)
        raw.playing = True

    def update_music_stream(self, raw: FakeMusic) -> None:
        """Pump a music stream and optionally simulate natural completion.

        Args:
            raw: Music stream.
        """
        self._music(raw)
        self._call("update_music_stream", raw)
        self.updated.append(raw)
        if self.finish_music_on_update:
            raw.playing = False

    def is_music_stream_playing(self, raw: FakeMusic) -> bool:
        """Inspect music playback state.

        Args:
            raw: Music stream.

        Returns:
            Whether the stream is playing.
        """
        self._music(raw)
        self._call("is_music_stream_playing", raw)
        return raw.playing


def make_listener(x: float, y: float) -> SimpleNamespace:
    """Create a mutable node-shaped listener without backend imports.

    Args:
        x: World X coordinate.
        y: World Y coordinate.

    Returns:
        An object exposing ``transform.world.position``.
    """
    return SimpleNamespace(
        transform=SimpleNamespace(world=SimpleNamespace(position=(x, y)))
    )
