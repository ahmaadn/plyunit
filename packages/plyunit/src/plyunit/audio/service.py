"""``Audio`` — optional host audio: SFX, music streams, buses, and 2D spatial voices.

Supports:
- Loading/unloading sounds and music streams
- Voice tracking with a ``max_voices`` limit
- Listener node follow (auto-follow transform)
- Spatial attenuation + pan via ``compute_spatial``
- Buses for master / SFX / music
- Loading JSON sound banks
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plyunit.audio.spatial import compute_spatial
from plyunit.backends.integrations import get_audio_backend
from plyunit.backends.interfaces import IAudioBackend
from plyunit.core.schema_config import AudioConfig
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils.io import read_json

from .types import MusicEntry, SoundEntry, VoiceId, VoiceRecord

if TYPE_CHECKING:
    from plyunit.core.app import App

logger = logging.getLogger(__name__)


class Audio(ServiceUnit):
    """Optional host audio service for SFX, music streams, buses, and 2D spatial voices.

    This service attaches itself to the active ``App`` automatically. Once
    active, it manages loading/unloading sounds and music, plays voices (with a
    ``max_voices`` limit), and performs 2D spatial audio (attenuation + pan)
    for ``tracked`` voices. The listener can be pinned to fixed coordinates or
    follow a ``NodeUnit`` (auto-follow).

    Attributes:
        assets_path: Base directory for loaded sound/music paths.
        master_volume: Master bus volume (0.0-1.0).
        sfx_volume: SFX bus volume (0.0-1.0).
        music_volume: Music bus volume (0.0-1.0).
        max_voices: Maximum number of simultaneous voices.
        spatial_min_distance: Distance below which a voice is at full volume.
        spatial_max_distance: Distance beyond which a voice is silent.
        spatial_rolloff: Spatial falloff exponent.
    """

    def __init__(
        self,
        backend: IAudioBackend,
        *,
        assets_path: str | Path = "./data/audio",
        master_volume: float = 1.0,
        sfx_volume: float = 1.0,
        music_volume: float = 1.0,
        max_voices: int = 32,
        spatial_min_distance: float = 50.0,
        spatial_max_distance: float = 800.0,
        spatial_rolloff: float = 1.0,
    ) -> None:
        """Initialize the Audio service.

        Args:
            backend: An instantiated audio backend.
            assets_path: Base path for loading sounds/music.
            master_volume: Master bus volume (0.0-1.0).
            sfx_volume: SFX bus volume (0.0-1.0).
            music_volume: Music bus volume (0.0-1.0).
            max_voices: Maximum simultaneous voices (steals the oldest when full).
            spatial_min_distance: Minimum attenuation distance.
            spatial_max_distance: Maximum attenuation distance.
            spatial_rolloff: Spatial falloff exponent.
        """
        super().__init__(name="Audio", tags={"service", "audio"})
        self._backend = backend
        self._asset_base_path = Path(assets_path)
        self._master_volume = master_volume
        self._sfx_volume = sfx_volume
        self._music_volume = music_volume
        self._max_voices = max_voices
        self._spatial_min = spatial_min_distance
        self._spatial_max = spatial_max_distance
        self._spatial_rolloff = spatial_rolloff

        self._sounds: dict[str, SoundEntry] = {}
        self._music: dict[str, MusicEntry] = {}
        self._voices: dict[VoiceId, VoiceRecord] = {}
        self._voice_order: list[VoiceId] = []
        self._next_voice_id = 1

        self._listener: tuple[float, float] = (0.0, 0.0)
        self._listener_node: Any | None = None
        self._active_music_id: str | None = None
        self._active_music_instance_volume: float = 1.0
        self._music_generation: int = 0

        self._app: App | None = None
        self._active = False

    @classmethod
    def from_config(self, cfg: AudioConfig):
        """Create an ``Audio`` service from an :class:`AudioConfig`.

        Args:
            cfg: Audio configuration holding volumes and spatial parameters.

        Returns:
            A new ``Audio`` instance using the current audio backend.
        """
        return Audio(
            get_audio_backend(),
            assets_path=cfg.assets_path,
            master_volume=cfg.master_volume,
            sfx_volume=cfg.sfx_volume,
            music_volume=cfg.music_volume,
            max_voices=cfg.max_voices,
            spatial_min_distance=cfg.spatial_min_distance,
            spatial_max_distance=cfg.spatial_max_distance,
            spatial_rolloff=cfg.spatial_rolloff,
        )

    @property
    def active(self) -> bool:
        """True if the backend audio device is ready (``init_device`` succeeded)."""
        return self._active

    @property
    def backend(self) -> IAudioBackend:
        """The audio backend used by this service."""
        return self._backend

    # --- lifecycle ---------------------------------------------------------

    def on_attach(self, app: App) -> None:
        """Lifecycle hook: initialize the audio device when the service is attached.

        Args:
            app: The App this service is attached to.
        """
        self._app = app
        try:
            self._backend.init_device()
            self._active = self._backend.is_device_ready()
        except Exception:
            logger.exception("Audio device init failed")
            self._active = False
            return
        self._backend.set_master_volume(self._master_volume)
        app.on_start_frame.connect(self._on_start_frame)

    def on_detach(self, app: App) -> None:
        """Lifecycle hook: stop all voices, unload assets, close the device.

        Args:
            app: The App this service is detached from.
        """
        with contextlib.suppress(Exception):
            app.on_start_frame.disconnect(self._on_start_frame)
        self._listener_node = None
        self.stop_all_sounds()
        self.stop_music()
        self.clear_all()
        if self._active or self._backend.is_device_ready():
            try:
                self._backend.close_device()
            except Exception:
                logger.exception("Audio device close failed")
        self._active = False
        self._app = None

    def _on_start_frame(self) -> None:
        """Per-frame hook: update the music stream, refresh voices, prune
        finished ones."""
        if not self._active:
            return
        if self._active_music_id is not None:
            entry = self._music.get(self._active_music_id)
            if entry is not None:
                self._backend.update_music_stream(entry.raw)
        self._refresh_tracked_voices()
        self._prune_finished_voices()

    def _require_active(self) -> None:
        """Guard: ensure the audio device is alive before playback operations.

        Raises:
            RuntimeError: If the device is not ready.
        """
        if not self._active:
            raise RuntimeError("Audio is not active (device not ready)")

    # --- paths -------------------------------------------------------------

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base path for subsequent sound/music loads.

        Args:
            path: The new base directory path.
        """
        self._asset_base_path = Path(path)

    def _resolve_under_base(self, path: str | Path) -> Path:
        """Resolve a path relative to the base path; forbid path traversal.

        Args:
            path: The relative or absolute path to resolve.

        Returns:
            The absolute path under ``_asset_base_path``.

        Raises:
            ValueError: If the resolved path escapes the base path.
        """
        base = self._asset_base_path.resolve()
        candidate = (base / path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Audio path escapes base path: {path}") from exc
        return candidate

    # --- volume buses ------------------------------------------------------

    @property
    def master_volume(self) -> float:
        """Master bus volume (0.0-1.0)."""
        return self._master_volume

    @property
    def sfx_volume(self) -> float:
        """SFX bus volume (0.0-1.0)."""
        return self._sfx_volume

    @property
    def music_volume(self) -> float:
        """Music bus volume (0.0-1.0)."""
        return self._music_volume

    def set_master_volume(self, volume: float) -> None:
        """Set the master volume (clamped to 0.0-1.0) and re-apply it to voices/music.

        Args:
            volume: The new volume; clamped to ``[0.0, 1.0]``.
        """
        self._master_volume = max(0.0, min(1.0, volume))
        if self._active:
            self._backend.set_master_volume(self._master_volume)
            self._reapply_music_volume()
            self._refresh_tracked_voices()

    def set_sfx_volume(self, volume: float) -> None:
        """Set the SFX bus volume and re-apply it to all voices.

        Args:
            volume: The new volume; clamped to ``[0.0, 1.0]``.
        """
        self._sfx_volume = max(0.0, min(1.0, volume))
        self._refresh_tracked_voices()
        for rec in self._voices.values():
            if not rec.tracked:
                self._backend.set_voice_volume(
                    rec.voice_raw, self._sfx_gain(rec.instance_volume)
                )

    def set_music_volume(self, volume: float) -> None:
        """Set the music bus volume and re-apply it to the active music stream.

        Args:
            volume: The new volume; clamped to ``[0.0, 1.0]``.
        """
        self._music_volume = max(0.0, min(1.0, volume))
        self._reapply_music_volume()

    def _sfx_gain(self, instance: float, attenuation: float = 1.0) -> float:
        """Compute the final SFX gain = master * sfx * instance * attenuation.

        Args:
            instance: Instance volume (per-play gain).
            attenuation: Spatial attenuation factor (default 1.0).

        Returns:
            The final gain, clamped to ``[0.0, 1.0]``.
        """
        return max(
            0.0,
            min(1.0, self._master_volume * self._sfx_volume * instance * attenuation),
        )

    def _music_gain(self, instance: float) -> float:
        """Compute the final music gain = master * music * instance.

        Args:
            instance: Music instance volume.

        Returns:
            The final gain, clamped to ``[0.0, 1.0]``.
        """
        return max(0.0, min(1.0, self._master_volume * self._music_volume * instance))

    def _reapply_music_volume(self) -> None:
        """Re-apply the music volume to the backend for the active music stream."""
        if not self._active or self._active_music_id is None:
            return
        entry = self._music.get(self._active_music_id)
        if entry is not None:
            self._backend.set_music_volume(
                entry.raw, self._music_gain(self._active_music_instance_volume)
            )

    # --- spatial / listener ------------------------------------------------

    def set_listener(self, x: float | Any, y: float | None = None) -> None:
        """Set the global listener position (fixed coordinates or a follow node).

        Two modes:
            - ``set_listener(x, y)`` — fixed coordinates. Clears node following.
            - ``set_listener(node)`` — auto-follows ``node.transform.world.position``
              every frame (no need to call it again).

        Args:
            x: X coordinate, or a node (when ``y`` is ``None``).
            y: Y coordinate, or ``None`` if ``x`` is a node.

        Raises:
            TypeError: If ``x`` is an object without a ``.transform`` attribute.
        """
        if y is None:
            node = x
            if not hasattr(node, "transform"):
                raise TypeError(
                    "set_listener(node) expects a node with .transform; "
                    "use set_listener(x, y) for fixed coordinates"
                )
            self._listener_node = node
            self._refresh_tracked_voices()
            return

        self._listener_node = None
        # pyrefly: ignore [unnecessary-type-conversion]
        self._listener = (float(x), float(y))
        self._refresh_tracked_voices()

    def clear_listener_follow(self) -> None:
        """Stop following the listener node; keep the last listener position."""
        self._listener = self.listener
        self._listener_node = None

    @property
    def listener(self) -> tuple[float, float]:
        """The current world-space listener position.

        Follows the bound follow node if one is set; otherwise the last fixed
        ``(x, y)`` position.
        """
        if self._listener_node is not None:
            try:
                pos = self._listener_node.transform.world.position
                return (float(pos[0]), float(pos[1]))
            except Exception:
                logger.debug("Listener node invalid; clearing follow", exc_info=True)
                self._listener_node = None
        return self._listener

    @property
    def listener_node(self) -> Any | None:
        """The node currently followed as the listener, or ``None``."""
        return self._listener_node

    def set_spatial_params(
        self,
        min_distance: float,
        max_distance: float,
        rolloff: float = 1.0,
    ) -> None:
        """Set global spatial audio parameters.

        Args:
            min_distance: Distance below which a voice is at full volume.
            max_distance: Distance beyond which a voice is silent.
            rolloff: Falloff exponent (default 1.0 = linear).

        Raises:
            ValueError: If a parameter is outside the valid range.
        """
        if min_distance < 0:
            raise ValueError("spatial_min_distance must be >= 0")
        if max_distance <= min_distance:
            raise ValueError("spatial_max_distance must be > spatial_min_distance")
        if rolloff <= 0:
            raise ValueError("spatial_rolloff must be > 0")
        self._spatial_min = min_distance
        self._spatial_max = max_distance
        self._spatial_rolloff = rolloff
        self._refresh_tracked_voices()

    def _refresh_tracked_voices(self) -> None:
        """Re-apply spatial attenuation + pan for all ``tracked`` voices."""
        if not self._active:
            return
        listener = self.listener
        for rec in self._voices.values():
            if not rec.tracked:
                continue
            att, pan = compute_spatial(
                listener,
                (rec.x, rec.y),
                self._spatial_min,
                self._spatial_max,
                self._spatial_rolloff,
            )
            rec.pan = pan
            self._backend.set_voice_volume(
                rec.voice_raw, self._sfx_gain(rec.instance_volume, att)
            )
            self._backend.set_voice_pan(rec.voice_raw, pan)

    # --- load / unload -----------------------------------------------------

    def load_sound(
        self,
        path: str | Path,
        *,
        sound_id: str | None = None,
        default_volume: float = 1.0,
        group: str | None = None,
    ) -> str:
        """Load a sound from a file and register it with the service.

        Args:
            path: Path relative to ``assets_path`` (or absolute).
            sound_id: Custom ID; defaults to ``path.stem``.
            default_volume: Default sound volume (0.0-1.0+).
            group: Optional logical group.

        Returns:
            The sound ID used (``sound_id`` or ``path.stem``).

        Raises:
            RuntimeError: If the audio device is not ready.
            FileNotFoundError: If the sound file does not exist.
        """
        self._require_active()
        resolved = self._resolve_under_base(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"Sound file not found: {resolved}")
        sid = sound_id or resolved.stem
        if sid in self._sounds:
            self.unload_sound(sid)
        raw = self._backend.load_sound(str(resolved))
        self._sounds[sid] = SoundEntry(
            raw=raw,
            path=resolved,
            default_volume=default_volume,
            group=group,
        )
        return sid

    def load_music(
        self,
        path: str | Path,
        *,
        music_id: str | None = None,
        default_volume: float = 1.0,
        default_loop: bool = True,
        group: str | None = None,
    ) -> str:
        """Load a music stream from a file and register it with the service.

        Args:
            path: Path relative to ``assets_path``.
            music_id: Custom ID; defaults to ``path.stem``.
            default_volume: Default music volume (0.0-1.0+).
            default_loop: Whether the stream loops by default.
            group: Optional logical group.

        Returns:
            The music ID used.

        Raises:
            RuntimeError: If the audio device is not ready.
            FileNotFoundError: If the music file does not exist.
        """
        self._require_active()
        resolved = self._resolve_under_base(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"Music file not found: {resolved}")
        mid = music_id or resolved.stem
        if mid in self._music:
            self.unload_music(mid)
        raw = self._backend.load_music_stream(str(resolved))
        self._music[mid] = MusicEntry(
            raw=raw,
            path=resolved,
            default_volume=default_volume,
            default_loop=default_loop,
            group=group,
        )
        return mid

    def unload_sound(self, sound_id: str) -> None:
        """Stop all voices for a sound, then unload it from the backend.

        Args:
            sound_id: The sound ID to unload.
        """
        entry = self._sounds.pop(sound_id, None)
        if entry is None:
            return
        to_stop = [vid for vid, rec in self._voices.items() if rec.sound_id == sound_id]
        for vid in to_stop:
            self.stop_voice(vid)
        try:
            self._backend.unload_sound(entry.raw)
        except Exception:
            logger.warning("Failed to unload sound %s", sound_id, exc_info=True)

    def unload_music(self, music_id: str) -> None:
        """Stop the active music stream if the ID matches, then unload it.

        Args:
            music_id: The music ID to unload.
        """
        if self._active_music_id == music_id:
            self.stop_music()
        entry = self._music.pop(music_id, None)
        if entry is None:
            return
        try:
            self._backend.unload_music_stream(entry.raw)
        except Exception:
            logger.warning("Failed to unload music %s", music_id, exc_info=True)

    def clear_all(self) -> None:
        """Unload all sounds and music from the service."""
        for sid in list(self._sounds):
            self.unload_sound(sid)
        for mid in list(self._music):
            self.unload_music(mid)

    def load_bank(self, path: str | Path) -> str:
        """Eagerly load a JSON sound bank. Returns the bank ID (or file stem).

        Args:
            path: Path to the sound bank JSON file.

        Returns:
            The bank ID (from the JSON ``id`` field, or the file stem if absent).

        Raises:
            RuntimeError: If the audio device is not ready.
            FileNotFoundError: If the bank file is not found.
            ValueError: If a bank entry is invalid.
        """
        self._require_active()
        bank_path = self._resolve_under_base(path)
        if not bank_path.is_file():
            raise FileNotFoundError(f"Sound bank not found: {bank_path}")
        data = read_json(str(bank_path))
        bank_id = str(data.get("id") or bank_path.stem)
        base_rel = str(data.get("base_path") or ".")
        entries = data.get("entries") or []
        for item in entries:
            eid = item.get("id")
            epath = item.get("path")
            if not eid or not epath:
                raise ValueError(f"Bank entry missing id/path in {bank_path}")
            kind = item.get("kind", "sound")
            vol = float(item.get("volume", 1.0))
            group = item.get("group")
            rel = Path(base_rel) / epath
            if kind == "music":
                self.load_music(
                    rel,
                    music_id=str(eid),
                    default_volume=vol,
                    default_loop=bool(item.get("loop", True)),
                    group=group,
                )
            elif kind == "sound":
                self.load_sound(
                    rel,
                    sound_id=str(eid),
                    default_volume=vol,
                    group=group,
                )
            else:
                raise ValueError(f"Unknown bank entry kind {kind!r} for {eid}")
        return bank_id

    # --- playback SFX ------------------------------------------------------

    def play_sound(
        self,
        sound_id: str,
        *,
        volume: float | None = None,
        pitch: float = 1.0,
        pan: float = 0.5,
    ) -> VoiceId:
        """Play a one-shot SFX sound (without spatial tracking).

        Args:
            sound_id: The ID of a loaded sound.
            volume: Instance volume (overrides the default).
            pitch: Pitch (1.0 = normal).
            pan: Stereo pan ``0.0`` (left) - ``0.5`` (center) - ``1.0`` (right).

        Returns:
            VoiceId: The ID of the newly started voice.

        Raises:
            RuntimeError: If the audio device is not ready.
            KeyError: If ``sound_id`` is not found.
        """
        self._require_active()
        entry = self._sounds.get(sound_id)
        if entry is None:
            raise KeyError(f"Unknown sound id: {sound_id}")
        inst = entry.default_volume if volume is None else volume
        gain = self._sfx_gain(inst)
        self._ensure_voice_slot()
        voice_raw = self._backend.play_sound(entry.raw, gain, pitch, pan)
        return self._register_voice(
            voice_raw,
            sound_id=sound_id,
            instance_volume=inst,
            pitch=pitch,
            pan=pan,
            tracked=False,
        )

    def play_sound_at(
        self,
        sound_id: str,
        x: float,
        y: float,
        *,
        volume: float | None = None,
        pitch: float = 1.0,
        track: bool = False,
    ) -> VoiceId:
        """Play a sound at a world position (2D spatial).

        Args:
            sound_id: The ID of a loaded sound.
            x: Source X position.
            y: Source Y position.
            volume: Instance volume (overrides the default).
            pitch: Pitch (1.0 = normal).
            track: If ``True``, the voice position updates automatically as
                the listener/node moves.

        Returns:
            VoiceId: The ID of the newly started voice.

        Raises:
            RuntimeError: If the audio device is not ready.
            KeyError: If ``sound_id`` is not found.
        """
        self._require_active()
        entry = self._sounds.get(sound_id)
        if entry is None:
            raise KeyError(f"Unknown sound id: {sound_id}")
        inst = entry.default_volume if volume is None else volume
        att, pan = compute_spatial(
            self.listener,
            # pyrefly: ignore [unnecessary-type-conversion]
            (float(x), float(y)),
            self._spatial_min,
            self._spatial_max,
            self._spatial_rolloff,
        )
        gain = self._sfx_gain(inst, att)
        self._ensure_voice_slot()
        voice_raw = self._backend.play_sound(entry.raw, gain, pitch, pan)
        return self._register_voice(
            voice_raw,
            sound_id=sound_id,
            instance_volume=inst,
            pitch=pitch,
            pan=pan,
            tracked=track,
            x=x,
            y=y,
        )

    def stop_voice(self, voice_id: VoiceId) -> None:
        """Stop an individual voice.

        Args:
            voice_id: The voice ID to stop.
        """
        rec = self._voices.pop(voice_id, None)
        if rec is None:
            return
        with contextlib.suppress(ValueError):
            self._voice_order.remove(voice_id)
        try:
            self._backend.stop_voice(rec.voice_raw)
        except Exception:
            logger.debug("stop_voice failed for %s", voice_id, exc_info=True)

    def stop_all_sounds(self) -> None:
        """Stop all active (SFX) voices."""
        for vid in list(self._voices):
            self.stop_voice(vid)

    def is_voice_playing(self, voice_id: VoiceId) -> bool:
        """Check whether a specific voice is currently active.

        Args:
            voice_id: The voice ID to check.

        Returns:
            True if the voice exists and the backend reports it as playing.
        """
        rec = self._voices.get(voice_id)
        if rec is None:
            return False
        return self._backend.is_voice_playing(rec.voice_raw)

    def set_voice_position(self, voice_id: VoiceId, x: float, y: float) -> None:
        """Update the world position of a ``tracked`` voice (re-applies spatial).

        Args:
            voice_id: The tracked voice ID.
            x: New X position.
            y: New Y position.
        """
        rec = self._voices.get(voice_id)
        if rec is None or not rec.tracked:
            return
        rec.x = x
        rec.y = y
        if self._active:
            att, pan = compute_spatial(
                self.listener,
                (rec.x, rec.y),
                self._spatial_min,
                self._spatial_max,
                self._spatial_rolloff,
            )
            rec.pan = pan
            self._backend.set_voice_volume(
                rec.voice_raw, self._sfx_gain(rec.instance_volume, att)
            )
            self._backend.set_voice_pan(rec.voice_raw, pan)

    def _register_voice(
        self,
        voice_raw: Any,
        *,
        sound_id: str,
        instance_volume: float,
        pitch: float,
        pan: float,
        tracked: bool,
        x: float = 0.0,
        y: float = 0.0,
    ) -> VoiceId:
        """Register a new voice in ``_voices`` and ``_voice_order``."""
        vid = VoiceId(self._next_voice_id)
        self._next_voice_id += 1
        self._voices[vid] = VoiceRecord(
            voice_id=vid,
            voice_raw=voice_raw,
            sound_id=sound_id,
            instance_volume=instance_volume,
            pitch=pitch,
            pan=pan,
            tracked=tracked,
            x=x,
            y=y,
        )
        self._voice_order.append(vid)
        return vid

    def _ensure_voice_slot(self) -> None:
        """Ensure a voice slot is available; steals the oldest voice when full."""
        self._prune_finished_voices()
        while len(self._voices) >= self._max_voices and self._voice_order:
            oldest = self._voice_order[0]
            self.stop_voice(oldest)

    def _prune_finished_voices(self) -> None:
        """Remove finished voices from tracking (as reported by the backend)."""
        finished = [
            vid
            for vid, rec in self._voices.items()
            if not self._backend.is_voice_playing(rec.voice_raw)
        ]
        for vid in finished:
            self._voices.pop(vid, None)
            with contextlib.suppress(ValueError):
                self._voice_order.remove(vid)

    # --- music -------------------------------------------------------------

    def play_music(
        self,
        music_id: str,
        *,
        loop: bool | None = None,
        volume: float | None = None,
    ) -> int:
        """Start a music stream.

        Args:
            music_id: The ID of a loaded music stream.
            loop: Overrides the default loop flag; ``None`` = use the entry default.
            volume: Instance volume (overrides the default).

        Returns:
            int: Generation token for ``owns_music`` (incremented on every stop/play).

        Raises:
            RuntimeError: If the audio device is not ready.
            KeyError: If ``music_id`` is not found.
        """
        self._require_active()
        entry = self._music.get(music_id)
        if entry is None:
            raise KeyError(f"Unknown music id: {music_id}")
        if self._active_music_id is not None:
            self.stop_music()
        loop_flag = entry.default_loop if loop is None else loop
        inst = entry.default_volume if volume is None else volume
        self._backend.set_music_looping(entry.raw, loop_flag)
        self._backend.set_music_volume(entry.raw, self._music_gain(inst))
        self._backend.play_music_stream(entry.raw)
        self._active_music_id = music_id
        self._active_music_instance_volume = inst
        self._music_generation += 1
        return self._music_generation

    def stop_music(self) -> None:
        """Stop the active music stream (no-op if there is none)."""
        if self._active_music_id is None:
            return
        entry = self._music.get(self._active_music_id)
        if entry is not None:
            try:
                self._backend.stop_music_stream(entry.raw)
            except Exception:
                logger.debug("stop_music failed", exc_info=True)
        self._active_music_id = None
        self._music_generation += 1

    def pause_music(self) -> None:
        """Pause the active music stream (no-op if there is none)."""
        if self._active_music_id is None:
            return
        entry = self._music.get(self._active_music_id)
        if entry is not None:
            self._backend.pause_music_stream(entry.raw)

    def resume_music(self) -> None:
        """Resume the active music stream (no-op if there is none)."""
        if self._active_music_id is None:
            return
        entry = self._music.get(self._active_music_id)
        if entry is not None:
            self._backend.resume_music_stream(entry.raw)

    def is_music_playing(self) -> bool:
        """Check whether the active music stream is playing on the backend."""
        if self._active_music_id is None:
            return False
        entry = self._music.get(self._active_music_id)
        if entry is None:
            return False
        return self._backend.is_music_stream_playing(entry.raw)

    @property
    def active_music_id(self) -> str | None:
        """The ID of the currently active music stream, or ``None``."""
        return self._active_music_id

    @property
    def music_generation(self) -> int:
        """Generation token for the current music stream (increments on stop/play)."""
        return self._music_generation

    def owns_music(self, generation: int, music_id: str | None = None) -> bool:
        """Check whether ``generation`` (and optionally ``music_id``) is still active.

        Args:
            generation: Generation token obtained from ``play_music``.
            music_id: Optional music ID for additional validation.

        Returns:
            True if the generation matches, ``music_id`` (if given) matches,
            and some music is currently active.
        """
        if generation != self._music_generation:
            return False
        if music_id is not None and self._active_music_id != music_id:
            return False
        return self._active_music_id is not None
