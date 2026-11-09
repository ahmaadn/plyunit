"""Node-attached audio playback through the backend-independent audio port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from plyunit.backends.ports.audio import IAudio
from plyunit.core.components.component import Component

if TYPE_CHECKING:
    from plyunit.services.audio._types import VoiceId


class AudioSource(Component):
    """Play a sound or music stream attached to a node.

    Discover the registered service structurally through ``IAudio``. Playback
    tokens belong to the exact service that issued them, even if the registry
    later contains a replacement service.
    """

    updates = True

    def __init__(
        self,
        asset_id: str,
        *,
        auto_play: bool = False,
        loop: bool = False,
        spatial: bool = False,
        volume: float = 1.0,
        pitch: float = 1.0,
        kind: Literal["sound", "music"] = "sound",
    ) -> None:
        """Initialize a node-attached audio source.

        Args:
            asset_id: Loaded sound or music ID in the audio service.
            auto_play: Start playback automatically in ``on_start``.
            loop: Restart completed sounds or enable music-stream looping.
            spatial: Track the node's 2D world position for sounds.
            volume: Per-play volume.
            pitch: Sound pitch multiplier; ignored for music.
            kind: Asset kind, either ``"sound"`` or ``"music"``.

        Raises:
            ValueError: If music is spatial or the asset kind is unknown.
        """
        super().__init__("AudioSource")
        if kind == "music" and spatial:
            raise ValueError("AudioSource music cannot be spatial")
        if kind not in ("sound", "music"):
            raise ValueError(f"Unknown AudioSource kind: {kind!r}")
        self.asset_id = asset_id
        self.auto_play = auto_play
        self.loop = loop
        self.spatial = spatial
        self.volume = volume
        self.pitch = pitch
        self.kind = kind
        self._voice_id: VoiceId | None = None
        self._music_generation: int | None = None
        self._music_id: str | None = None
        self._playback_audio: IAudio | None = None

    def _audio(self) -> IAudio:
        """Find the single registered service implementing the audio port.

        Returns:
            The audio service, regardless of its concrete class or name.

        Raises:
            RuntimeError: If the source is unattached, audio is missing, or
                multiple audio services are registered.
        """
        if self.unit is None:
            raise RuntimeError("AudioSource must be attached to a node before playback")
        # Registry type queries use exact classes, so protocols need a structural
        # scan of the registry's service owners rather than a class/name query.
        services = self.unit.global_units._service_order.values()
        matches = [service for service in services if isinstance(service, IAudio)]
        if not matches:
            raise RuntimeError(
                "AudioSource requires a registered IAudio service "
                "(enable AppConfig.audio or construct an audio service)"
            )
        if len(matches) != 1:
            raise RuntimeError(
                "AudioSource requires exactly one registered IAudio service"
            )
        return matches[0]

    def on_start(self) -> None:
        """Start playback when automatic playback is enabled."""
        if self.auto_play:
            self.play()

    def update(self, dt: float) -> None:
        """Move live spatial sounds and restart completed looping sounds.

        Args:
            dt: Fixed-step delta time in seconds.
        """
        if not self.enabled or self.kind != "sound" or self._voice_id is None:
            return
        audio = self._playback_audio
        if audio is None or not audio.active:
            self._voice_id = None
            self._playback_audio = None
            return
        if not audio.is_voice_playing(self._voice_id):
            self._voice_id = None
            self._playback_audio = None
            if self.loop:
                self.play()
            return
        if self.spatial:
            pos = self.unit.transform.world.position
            audio.set_voice_position(self._voice_id, pos[0], pos[1])

    def on_destroy(self) -> None:
        """Stop owned playback and finish component teardown."""
        try:
            self.stop()
        finally:
            super().on_destroy()

    def play(self) -> None:
        """Replace this source's playback with a new sound or music stream.

        Raises:
            RuntimeError: If no unambiguous audio service is registered or its
                device is inactive.
            KeyError: If the asset is not loaded by the audio service.
        """
        audio = self._audio()
        self.stop()
        if self.kind == "music":
            generation = audio.play_music(
                self.asset_id, loop=self.loop, volume=self.volume
            )
            self._music_generation = generation
            self._music_id = self.asset_id
        elif self.spatial:
            pos = self.unit.transform.world.position
            self._voice_id = audio.play_sound_at(
                self.asset_id,
                pos[0],
                pos[1],
                volume=self.volume,
                pitch=self.pitch,
                track=True,
            )
        else:
            self._voice_id = audio.play_sound(
                self.asset_id, volume=self.volume, pitch=self.pitch
            )
        self._playback_audio = audio

    def stop(self) -> None:
        """Stop only playback owned by this source and clear its tokens."""
        audio = self._playback_audio
        try:
            if audio is None:
                return
            if self._voice_id is not None:
                audio.stop_voice(self._voice_id)
            if self._music_generation is not None and audio.owns_music(
                self._music_generation, self._music_id
            ):
                audio.stop_music()
        finally:
            self._voice_id = None
            self._music_generation = None
            self._music_id = None
            self._playback_audio = None

    def pause(self) -> None:
        """Pause owned music without affecting other sources or sounds."""
        audio = self._playback_audio
        if (
            self.kind == "music"
            and audio is not None
            and self._music_generation is not None
            and audio.owns_music(self._music_generation, self._music_id)
        ):
            audio.pause_music()

    def resume(self) -> None:
        """Resume owned music without affecting other sources or sounds."""
        audio = self._playback_audio
        if (
            self.kind == "music"
            and audio is not None
            and self._music_generation is not None
            and audio.owns_music(self._music_generation, self._music_id)
        ):
            audio.resume_music()
