from __future__ import annotations

from typing import Literal

from plyunit.core.components.component import Component


class AudioSource(Component):
    """Play a sound or music stream attached to a ``NodeUnit``.

    Resolves ``Audio`` by name only (core must not import engine).
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
        """Initializes the AudioSource.

        Args:
            asset_id: Sound asset ID in ``Audio``.
            auto_play: Play automatically on ``on_start``.
            loop: Loop the sound/music.
            spatial: Play with 3D/2D positioning (sound only).
            volume: Initial volume (``0.0`` - ``1.0``).
            pitch: Pitch multiplier.
            kind: ``"sound"`` or ``"music"``.

        Raises:
            ValueError: If ``kind == "music"`` and ``spatial=True``, or
                ``kind`` is not a valid value.
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
        self._voice_id = None
        self._music_generation: int | None = None
        self._music_id: str | None = None

    def _audio(self):
        """Internal hook: gets the ``Audio`` service.

        Returns:
            The ``Audio`` instance.

        Raises:
            RuntimeError: If ``Audio`` is not registered.
        """
        try:
            return self.unit.one("Audio")
        except Exception as exc:
            raise RuntimeError(
                "AudioSource requires Audio (enable AppConfig.audio "
                "or construct Audio while App is active)"
            ) from exc

    def on_start(self) -> None:
        """Lifecycle hook: auto-``play()`` if ``auto_play=True``."""
        if self.auto_play:
            self.play()

    def update(self, dt: float) -> None:
        """Updates the spatial voice position and restarts the loop sound if the
        voice finished.

        Args:
            dt: Fixed-step delta time in seconds.
        """
        if not self.enabled:
            return
        audio = None
        if self.spatial and self._voice_id is not None:
            audio = self._audio()
            if audio.is_voice_playing(self._voice_id):
                pos = self.unit.transform.world.position
                audio.set_voice_position(self._voice_id, pos[0], pos[1])
            else:
                self._voice_id = None

        if self.kind == "sound" and self.loop and self._voice_id is not None:
            if audio is None:
                audio = self._audio()
            if not audio.is_voice_playing(self._voice_id):
                self._voice_id = None
                self.play()

    def on_destroy(self) -> None:
        """Lifecycle hook: stops playback, then calls ``super().on_destroy()``."""
        self.stop()
        super().on_destroy()

    def play(self) -> None:
        """Starts playing the asset (sound or music)."""
        audio = self._audio()
        if self.kind == "music":
            gen = audio.play_music(self.asset_id, loop=self.loop, volume=self.volume)
            self._music_generation = gen
            self._music_id = self.asset_id
            self._voice_id = None
            return

        if self._voice_id is not None:
            audio.stop_voice(self._voice_id)
            self._voice_id = None

        if self.spatial:
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
                self.asset_id,
                volume=self.volume,
                pitch=self.pitch,
            )

    def stop(self) -> None:
        """Stops the active sound/music playback."""
        audio = self.unit.one_or_none("Audio")
        if audio is None:
            self._voice_id = None
            self._music_generation = None
            self._music_id = None
            return

        if self._voice_id is not None:
            audio.stop_voice(self._voice_id)
            self._voice_id = None

        if (
            self._music_generation is not None and self._music_id is not None
        ) and audio.owns_music(self._music_generation, self._music_id):
            audio.stop_music()
        self._music_generation = None
        self._music_id = None

    def pause(self) -> None:
        """Pauses the music (no-op for ``kind="sound"``)."""
        if self.kind != "music":
            return
        audio = self._audio()
        if self._music_generation is not None and audio.owns_music(
            self._music_generation, self._music_id
        ):
            audio.pause_music()

    def resume(self) -> None:
        """Resumes paused music (no-op for ``kind="sound"``)."""
        if self.kind != "music":
            return
        audio = self._audio()
        if self._music_generation is not None and audio.owns_music(
            self._music_generation, self._music_id
        ):
            audio.resume_music()
