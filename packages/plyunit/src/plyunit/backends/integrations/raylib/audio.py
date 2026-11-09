"""``Audio`` — host audio service: SFX, music streams, buses, and 2D spatial voices."""

from __future__ import annotations

import contextlib
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pyray as pr

from plyunit.backends.ports.audio import IAudio
from plyunit.core.schema_config import AudioConfig
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.services.audio._types import VoiceId
from plyunit.services.audio.spatial import compute_spatial
from plyunit.utils.io import read_json

from .handler import _Music, _Sound, _Voice

if TYPE_CHECKING:
    from plyunit.backends.ports._unit import INodeUnit
    from plyunit.core.app import App

logger = logging.getLogger(__name__)

__all__ = ["Audio"]


def _finite_float(value: float, name: str) -> float:
    """Convert a numeric parameter and reject non-finite native inputs.

    Args:
        value: Numeric value to convert.
        name: Parameter name for validation errors.

    Returns:
        The finite floating-point value.

    Raises:
        ValueError: If the value is infinite or NaN.
    """
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _clamp_volume(volume: float) -> float:
    """Return a finite volume clamped to the public bus range.

    Args:
        volume: Requested volume.

    Returns:
        A value in the range ``[0.0, 1.0]``.

    Raises:
        ValueError: If the volume is not finite.
    """
    return max(0.0, min(1.0, _finite_float(volume, "volume")))


def _native_pan(pan: float) -> float:
    """Translate public left-to-right pan to the installed raylib version.

    Raylib 5.5 uses left-channel gain in ``[0, 1]``. Raylib 6 uses signed
    left-to-right pan in ``[-1, 1]``. Neither accepts the public range directly.

    Args:
        pan: Public stereo position, from zero (left) to one (right).

    Returns:
        The native stereo position for the installed raylib version.
    """
    # The native binding exports this constant but its stub omits it.
    if int(pr.RAYLIB_VERSION_MAJOR) >= 6:  # pyrefly: ignore [missing-attribute]
        return 2.0 * pan - 1.0
    return 1.0 - pan


class Audio(ServiceUnit, IAudio):
    """Host audio service for SFX, music streams, buses, and 2D spatial voices.

    This service attaches itself to the active ``App`` automatically. Once
    active, it manages loading/unloading sounds and music, plays voices (with a
    ``max_voices`` limit), and performs 2D spatial audio (attenuation + pan)
    for ``tracked`` voices. The listener can be pinned to fixed coordinates or
    follow a ``NodeUnit`` (auto-follow).

    Attributes:
        master_volume: Master bus volume (0.0-1.0).
        sfx_volume: SFX bus volume (0.0-1.0).
        music_volume: Music bus volume (0.0-1.0).
    """

    def __init__(
        self,
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
            assets_path: Base path for loading sounds/music.
            master_volume: Master bus volume (0.0-1.0).
            sfx_volume: SFX bus volume (0.0-1.0).
            music_volume: Music bus volume (0.0-1.0).
            max_voices: Maximum simultaneous voices (steals the oldest when full).
            spatial_min_distance: Minimum attenuation distance.
            spatial_max_distance: Maximum attenuation distance.
            spatial_rolloff: Spatial falloff exponent.

        Raises:
            ValueError: If the voice limit is not a positive integer, a volume
                is non-finite, or spatial parameters are invalid.
        """
        self._asset_base_path = Path(assets_path).resolve()
        self._master_volume = _clamp_volume(master_volume)
        self._sfx_volume = _clamp_volume(sfx_volume)
        self._music_volume = _clamp_volume(music_volume)
        if isinstance(max_voices, bool) or not isinstance(max_voices, int):
            raise ValueError("max_voices must be a positive integer")
        if max_voices <= 0:
            raise ValueError("max_voices must be a positive integer")
        self._max_voices = max_voices

        self._sounds: dict[str, _Sound] = {}
        self._music: dict[str, _Music] = {}
        self._pending_resources: list[_Sound | _Music] = []
        self._voices: dict[VoiceId, _Voice] = {}
        self._voice_order: list[VoiceId] = []
        self._next_voice_id = 1

        self._listener: tuple[float, float] = (0.0, 0.0)
        self._listener_node: INodeUnit | None = None
        self._active_music_id: str | None = None
        self._active_music_instance_volume = 1.0
        self._music_generation = 0
        self._music_paused = False

        self._app: App | None = None
        self._active = False
        self._owns_device = False
        self.set_spatial_params(
            spatial_min_distance, spatial_max_distance, spatial_rolloff
        )
        super().__init__(name="Audio", tags={"service", "audio"})

    @classmethod
    def from_config(cls, cfg: AudioConfig) -> Audio:
        """Create an ``Audio`` service from an :class:`AudioConfig`.

        Args:
            cfg: Audio configuration holding volumes and spatial parameters.

        Returns:
            A new ``Audio`` instance.
        """
        cfg.validate()
        return cls(
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
        """Return whether this attached service has a live audio device."""
        if not self._active:
            return False
        if pr.is_audio_device_ready():
            return True
        self._active = False
        self._owns_device = False
        self.clear_all()
        logger.warning("Audio device lost; discarded its resource handles")
        return False

    # --- lifecycle ---------------------------------------------------------

    def on_attach(self, app: App) -> None:
        """Open or borrow the audio device and subscribe to frame updates.

        Args:
            app: App hosting this service.

        Raises:
            RuntimeError: If the service is already attached to another app.
        """
        if self._app is not None and self._app is not app:
            raise RuntimeError("Audio is already attached to another app")
        if self._app is app and self.active:
            return
        self._app = app
        try:
            if not pr.is_audio_device_ready():
                self._owns_device = True
                pr.init_audio_device()
            self._active = bool(pr.is_audio_device_ready())
            if not self._active:
                self._owns_device = False
                logger.warning("Audio device is not ready after initialization")
                return
            pr.set_master_volume(self._master_volume)
            app.on_start_frame.connect(self._on_start_frame)
        except Exception:
            logger.exception("Audio device initialization failed")
            with contextlib.suppress(Exception):
                app.on_start_frame.disconnect(self._on_start_frame)
            if self._owns_device:
                with contextlib.suppress(Exception):
                    if pr.is_audio_device_ready():
                        pr.close_audio_device()
            self._owns_device = False
            self._active = False

    def on_detach(self, app: App) -> None:
        """Release aliases before samples, then close only an owned device.

        Args:
            app: App being detached; other apps cannot tear down this service.
        """
        if self._app is not app:
            return
        with contextlib.suppress(Exception):
            app.on_start_frame.disconnect(self._on_start_frame)
        self.clear_listener_follow()
        try:
            self.clear_all()
        finally:
            if self._owns_device and pr.is_audio_device_ready():
                try:
                    pr.close_audio_device()
                except Exception:
                    logger.exception("Audio device close failed")
            self._active = False
            self._owns_device = False
            if not pr.is_audio_device_ready():
                self.clear_all()
            self._app = None

    def _on_start_frame(self) -> None:
        """Pump music, reclaim finished aliases, and refresh spatial voices."""
        if not self.active:
            return
        entry = self._active_music_entry()
        if entry is not None and not self._music_paused:
            pr.update_music_stream(entry.raw)
            if not pr.is_music_stream_playing(entry.raw):
                self.stop_music()
        self._prune_finished_voices()
        self._refresh_tracked_voices()
        self._release_pending_resources()

    def _require_active(self) -> None:
        """Reject native resource creation or playback without a live device.

        Raises:
            RuntimeError: If the device is not ready.
        """
        if not self.active:
            raise RuntimeError("Audio is not active (device not ready)")

    # --- paths -------------------------------------------------------------

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base path for subsequent sound/music loads.

        Args:
            path: The new base directory path.
        """
        self._asset_base_path = Path(path).resolve()

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
        """Set the native master bus without applying its gain twice.

        Args:
            volume: Finite volume clamped to ``[0.0, 1.0]``.
        """
        self._master_volume = _clamp_volume(volume)
        if self.active:
            pr.set_master_volume(self._master_volume)

    def set_sfx_volume(self, volume: float) -> None:
        """Set the SFX bus volume and re-apply it to all voices.

        Args:
            volume: The new volume; clamped to ``[0.0, 1.0]``.
        """
        self._sfx_volume = _clamp_volume(volume)
        if not self.active:
            return
        self._prune_finished_voices()
        for rec in self._voices.values():
            if rec.tracked:
                self._apply_spatial(rec)
            else:
                pr.set_sound_volume(
                    rec.voice_raw,
                    self._sfx_gain(rec.instance_volume, rec.attenuation),
                )

    def set_music_volume(self, volume: float) -> None:
        """Set the music bus volume and re-apply it to the active music stream.

        Args:
            volume: The new volume; clamped to ``[0.0, 1.0]``.
        """
        self._music_volume = _clamp_volume(volume)
        self._reapply_music_volume()

    def _sfx_gain(self, instance: float, attenuation: float = 1.0) -> float:
        """Compute per-voice SFX gain before the native master bus.

        Args:
            instance: Instance volume (per-play gain).
            attenuation: Spatial attenuation factor (default 1.0).

        Returns:
            SFX bus times instance times attenuation, clamped to ``[0.0, 1.0]``.
        """
        return max(0.0, min(1.0, self._sfx_volume * instance * attenuation))

    def _music_gain(self, instance: float) -> float:
        """Compute music-stream gain before the native master bus.

        Args:
            instance: Music instance volume.

        Returns:
            Music bus times instance volume, clamped to ``[0.0, 1.0]``.
        """
        return max(0.0, min(1.0, self._music_volume * instance))

    def _reapply_music_volume(self) -> None:
        """Re-apply the music volume to raylib for the active music stream."""
        if not self.active or self._active_music_id is None:
            return
        entry = self._music.get(self._active_music_id)
        if entry is not None:
            pr.set_music_volume(
                entry.raw, self._music_gain(self._active_music_instance_volume)
            )

    # --- spatial / listener ------------------------------------------------

    def set_listener(self, x: float | INodeUnit, y: float | None = None) -> None:
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
            node = cast("INodeUnit", x)
            try:
                pos = node.transform.world.position
                position = (
                    _finite_float(pos[0], "listener.x"),
                    _finite_float(pos[1], "listener.y"),
                )
            except (AttributeError, IndexError, TypeError, ValueError) as exc:
                raise TypeError(
                    "set_listener(node) expects .transform.world.position; "
                    "use set_listener(x, y) for fixed coordinates"
                ) from exc
            self._listener = position
            self._listener_node = node
            self._refresh_tracked_voices()
            return

        position = (
            _finite_float(cast("float", x), "listener.x"),
            _finite_float(y, "listener.y"),
        )
        self._listener_node = None
        self._listener = position
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
                self._listener = (
                    _finite_float(pos[0], "listener.x"),
                    _finite_float(pos[1], "listener.y"),
                )
            except Exception:
                logger.debug("Listener node invalid; clearing follow", exc_info=True)
                self._listener_node = None
        return self._listener

    @property
    def listener_node(self) -> INodeUnit | None:
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
        min_distance = _finite_float(min_distance, "spatial_min_distance")
        max_distance = _finite_float(max_distance, "spatial_max_distance")
        rolloff = _finite_float(rolloff, "spatial_rolloff")
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

    def _apply_spatial(self, rec: _Voice) -> None:
        """Recompute and apply spatial volume + pan for one tracked voice.

        Args:
            rec: The tracked voice record to update.
        """
        att, pan = compute_spatial(
            self.listener,
            (rec.x, rec.y),
            self._spatial_min,
            self._spatial_max,
            self._spatial_rolloff,
        )
        rec.attenuation = att
        rec.pan = pan
        pr.set_sound_volume(rec.voice_raw, self._sfx_gain(rec.instance_volume, att))
        pr.set_sound_pan(rec.voice_raw, _native_pan(pan))

    def _refresh_tracked_voices(self) -> None:
        """Re-apply spatial attenuation + pan for all ``tracked`` voices."""
        if not self.active:
            return
        _ = self.listener
        for rec in self._voices.values():
            if rec.tracked:
                self._apply_spatial(rec)

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
        default_volume = _finite_float(default_volume, "default_volume")
        raw = pr.load_sound(str(resolved))
        owner = _Sound(raw, resolved, default_volume, group)
        try:
            if not pr.is_sound_valid(raw):
                raise RuntimeError(f"Failed to load sound: {resolved}")
        except BaseException:
            self._release_or_defer(owner)
            raise
        sid = sound_id or resolved.stem
        if sid in self._sounds:
            self.unload_sound(sid)
            if sid in self._sounds:
                self._release_or_defer(owner)
                raise RuntimeError(f"Failed to release the previous sound: {sid}")
        self._sounds[sid] = owner
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
        default_volume = _finite_float(default_volume, "default_volume")
        raw = pr.load_music_stream(str(resolved))
        owner = _Music(raw, resolved, default_volume, default_loop, group)
        try:
            if not pr.is_music_valid(raw):
                raise RuntimeError(f"Failed to load music: {resolved}")
        except BaseException:
            self._release_or_defer(owner)
            raise
        mid = music_id or resolved.stem
        if mid in self._music:
            self.unload_music(mid)
            if mid in self._music:
                self._release_or_defer(owner)
                raise RuntimeError(f"Failed to release the previous music: {mid}")
        self._music[mid] = owner
        return mid

    def unload_sound(self, sound_id: str) -> None:
        """Stop all voices for a sound, then unload it.

        Args:
            sound_id: The sound ID to unload.
        """
        entry = self._sounds.get(sound_id)
        if entry is None:
            return
        to_stop = [vid for vid, rec in self._voices.items() if rec.sound_id == sound_id]
        for vid in to_stop:
            self.stop_voice(vid)
        if any(rec.sound_id == sound_id for rec in self._voices.values()):
            logger.warning(
                "Retaining sound %s until its aliases are released", sound_id
            )
            return
        if entry.release(device_ready=self.active):
            self._sounds.pop(sound_id, None)

    def unload_music(self, music_id: str) -> None:
        """Stop the active music stream if the ID matches, then unload it.

        Args:
            music_id: The music ID to unload.
        """
        if self._active_music_id == music_id:
            self.stop_music()
        entry = self._music.get(music_id)
        if entry is None:
            return
        if entry.release(device_ready=self.active):
            self._music.pop(music_id, None)

    def clear_all(self) -> None:
        """Release every voice and loaded asset without closing the device."""
        self.stop_all_sounds()
        self.stop_music()
        for sid in list(self._sounds):
            self.unload_sound(sid)
        for mid in list(self._music):
            self.unload_music(mid)
        self._release_pending_resources()

    def _release_or_defer(self, resource: _Sound | _Music) -> None:
        """Retain an uncached allocation if native cleanup needs another attempt."""
        if not resource.release(device_ready=self.active):
            self._pending_resources.append(resource)

    def _release_pending_resources(self) -> None:
        """Retry allocations retained after a failed load or replacement cleanup."""
        self._pending_resources = [
            resource
            for resource in self._pending_resources
            if not resource.release(device_ready=self.active)
        ]

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
        for item in data.get("entries") or []:
            self._load_bank_entry(item, base_rel, bank_path)
        return bank_id

    def _load_bank_entry(
        self, item: dict[str, Any], base_rel: str, bank_path: Path
    ) -> None:
        """Load one sound bank entry.

        Args:
            item: The raw entry dict from the bank JSON.
            base_rel: The bank's relative ``base_path``.
            bank_path: Bank file path (used for error messages).

        Raises:
            ValueError: If the entry has no id/path or an unknown kind.
        """
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
            self.load_sound(rel, sound_id=str(eid), default_volume=vol, group=group)
        else:
            raise ValueError(f"Unknown bank entry kind {kind!r} for {eid}")

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
        entry = self._get_sound(sound_id)
        inst = _finite_float(
            entry.default_volume if volume is None else volume, "volume"
        )
        pitch = _finite_float(pitch, "pitch")
        if pitch <= 0:
            raise ValueError("pitch must be > 0")
        pan = max(0.0, min(1.0, _finite_float(pan, "pan")))
        self._ensure_voice_slot()
        voice_raw = self._start_voice(entry, sound_id, self._sfx_gain(inst), pitch, pan)
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
        entry = self._get_sound(sound_id)
        inst = _finite_float(
            entry.default_volume if volume is None else volume, "volume"
        )
        pitch = _finite_float(pitch, "pitch")
        if pitch <= 0:
            raise ValueError("pitch must be > 0")
        x = _finite_float(x, "source.x")
        y = _finite_float(y, "source.y")
        att, pan = compute_spatial(
            self.listener,
            (x, y),
            self._spatial_min,
            self._spatial_max,
            self._spatial_rolloff,
        )
        self._ensure_voice_slot()
        voice_raw = self._start_voice(
            entry, sound_id, self._sfx_gain(inst, att), pitch, pan
        )
        return self._register_voice(
            voice_raw,
            sound_id=sound_id,
            instance_volume=inst,
            pitch=pitch,
            pan=pan,
            attenuation=att,
            tracked=track,
            x=x,
            y=y,
        )

    def _get_sound(self, sound_id: str) -> _Sound:
        """Return a loaded sound entry.

        Args:
            sound_id: The sound ID to look up.

        Returns:
            The registered sound resource owner.

        Raises:
            KeyError: If ``sound_id`` is not found.
        """
        entry = self._sounds.get(sound_id)
        if entry is None:
            raise KeyError(f"Unknown sound id: {sound_id}")
        return entry

    def _start_voice(
        self, entry: _Sound, sound_id: str, volume: float, pitch: float, pan: float
    ) -> pr.Sound:
        """Start a raylib sound alias so one sound can overlap itself.

        Args:
            entry: Concrete source sound owning the samples.
            sound_id: ID of the loaded source sound.
            volume: Voice volume (0.0-1.0).
            pitch: Pitch multiplier.
            pan: Stereo pan (0.0 left .. 1.0 right).

        Returns:
            The raylib sound alias playing as the voice.
        """
        voice = pr.load_sound_alias(entry.raw)
        owner = _Voice(VoiceId(0), voice, sound_id, volume, pitch, pan)
        try:
            if not pr.is_sound_valid(voice):
                raise RuntimeError("Failed to create sound alias")
            pr.set_sound_volume(voice, volume)
            pr.set_sound_pitch(voice, pitch)
            pr.set_sound_pan(voice, _native_pan(pan))
            pr.play_sound(voice)
        except BaseException:
            if not owner.release(device_ready=self.active):
                # Failed startup aliases must still keep their samples alive.
                self._register_voice(
                    voice,
                    sound_id=sound_id,
                    instance_volume=volume,
                    pitch=pitch,
                    pan=pan,
                    tracked=False,
                )
            raise
        return voice

    def stop_voice(self, voice_id: VoiceId) -> None:
        """Stop an individual voice and release its raylib alias.

        Args:
            voice_id: The voice ID to stop.
        """
        rec = self._voices.get(voice_id)
        if rec is None or not rec.release(device_ready=self.active):
            return
        self._voices.pop(voice_id, None)
        with contextlib.suppress(ValueError):
            self._voice_order.remove(voice_id)

    def stop_all_sounds(self) -> None:
        """Stop all active (SFX) voices."""
        for vid in list(self._voices):
            self.stop_voice(vid)

    def is_voice_playing(self, voice_id: VoiceId) -> bool:
        """Check whether a specific voice is currently active.

        Args:
            voice_id: The voice ID to check.

        Returns:
            True if the voice exists and raylib reports it as playing.
        """
        rec = self._voices.get(voice_id)
        if rec is None or not self.active:
            return False
        return bool(pr.is_sound_playing(rec.voice_raw))

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
        position = (_finite_float(x, "source.x"), _finite_float(y, "source.y"))
        rec.x, rec.y = position
        if self.active:
            self._apply_spatial(rec)

    def _register_voice(
        self,
        voice_raw: pr.Sound,
        *,
        sound_id: str,
        instance_volume: float,
        pitch: float,
        pan: float,
        tracked: bool,
        attenuation: float = 1.0,
        x: float = 0.0,
        y: float = 0.0,
    ) -> VoiceId:
        """Take ownership of a new alias and issue a service-local token.

        Args:
            voice_raw: Native alias whose lifetime is now owned by the service.
            sound_id: ID of the source sound.
            instance_volume: Per-play gain before buses and attenuation.
            pitch: Positive pitch multiplier.
            pan: Public stereo position.
            tracked: Whether listener and position changes update spatial gain.
            attenuation: Initial spatial volume factor.
            x: Source world X coordinate.
            y: Source world Y coordinate.

        Returns:
            The token of the newly registered voice.
        """
        vid = VoiceId(self._next_voice_id)
        self._next_voice_id += 1
        self._voices[vid] = _Voice(
            voice_id=vid,
            voice_raw=voice_raw,
            sound_id=sound_id,
            instance_volume=instance_volume,
            pitch=pitch,
            pan=pan,
            attenuation=attenuation,
            tracked=tracked,
            x=x,
            y=y,
        )
        self._voice_order.append(vid)
        return vid

    def _ensure_voice_slot(self) -> None:
        """Ensure a voice slot is available; steals the oldest voice when full."""
        self._prune_finished_voices()
        if len(self._voices) >= self._max_voices and self._voice_order:
            self.stop_voice(self._voice_order[0])
        if len(self._voices) >= self._max_voices:
            raise RuntimeError("Failed to release an audio voice slot")

    def _prune_finished_voices(self) -> None:
        """Release voices that raylib reports as finished."""
        if not self.active:
            return
        finished = [
            vid
            for vid, rec in self._voices.items()
            if not pr.is_sound_playing(rec.voice_raw)
        ]
        for vid in finished:
            self.stop_voice(vid)

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
        inst = _finite_float(
            entry.default_volume if volume is None else volume, "volume"
        )
        if self._active_music_id is not None:
            self.stop_music()
        try:
            entry.raw.looping = entry.default_loop if loop is None else loop
            pr.set_music_volume(entry.raw, self._music_gain(inst))
            pr.play_music_stream(entry.raw)
        except BaseException:
            entry.stop()
            raise
        self._active_music_id = music_id
        self._active_music_instance_volume = inst
        self._music_paused = False
        self._music_generation += 1
        return self._music_generation

    def _active_music_entry(self) -> _Music | None:
        """Return the active music entry, or ``None`` if nothing is active."""
        if self._active_music_id is None:
            return None
        return self._music.get(self._active_music_id)

    def stop_music(self) -> None:
        """Stop the active music stream (no-op if there is none)."""
        if self._active_music_id is None:
            return
        entry = self._active_music_entry()
        self._active_music_id = None
        self._active_music_instance_volume = 1.0
        self._music_paused = False
        self._music_generation += 1
        if entry is not None and self.active:
            entry.stop()

    def pause_music(self) -> None:
        """Pause the active music stream (no-op if there is none)."""
        entry = self._active_music_entry()
        if entry is not None and self.active and not self._music_paused:
            pr.pause_music_stream(entry.raw)
            self._music_paused = True

    def resume_music(self) -> None:
        """Resume the active music stream (no-op if there is none)."""
        entry = self._active_music_entry()
        if entry is not None and self.active and self._music_paused:
            pr.resume_music_stream(entry.raw)
            self._music_paused = False

    def is_music_playing(self) -> bool:
        """Check whether the active music stream is playing."""
        entry = self._active_music_entry()
        return (
            self.active
            and entry is not None
            and not self._music_paused
            and bool(pr.is_music_stream_playing(entry.raw))
        )

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
            True if the live generation and optional asset ID match. Pausing
            preserves ownership; completion and device teardown invalidate it.
        """
        if not self.active or generation != self._music_generation:
            return False
        if music_id is not None and self._active_music_id != music_id:
            return False
        return self._active_music_id is not None and (
            self._music_paused or self.is_music_playing()
        )
