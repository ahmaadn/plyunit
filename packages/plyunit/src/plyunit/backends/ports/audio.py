"""Backend-independent audio service contract.

Assets are addressed by string IDs. Voices and music generations are opaque,
service-local playback tokens; native resources never cross this port.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from plyunit.backends.ports._unit import IServiceUnit

if TYPE_CHECKING:
    from plyunit.backends.ports._unit import INodeUnit
    from plyunit.services.audio._types import VoiceId


@runtime_checkable
class IAudio(IServiceUnit, Protocol):
    """Provide SFX, music, volume buses, and 2D spatial playback.

    Loading and starting playback require an active device. Controls and cleanup
    are safe when inactive. Music ownership survives pause, but ends on stop,
    replacement, completion, or device teardown. Tokens must only be used with
    the service that issued them.
    """

    @property
    def active(self) -> bool:
        """True if the audio device is ready."""
        ...

    @property
    def master_volume(self) -> float:
        """Master bus volume (0.0-1.0)."""
        ...

    @property
    def sfx_volume(self) -> float:
        """SFX bus volume (0.0-1.0)."""
        ...

    @property
    def music_volume(self) -> float:
        """Music bus volume (0.0-1.0)."""
        ...

    @property
    def listener(self) -> tuple[float, float]:
        """Current world-space listener position."""
        ...

    @property
    def listener_node(self) -> INodeUnit | None:
        """Node followed as the listener, or ``None``."""
        ...

    @property
    def active_music_id(self) -> str | None:
        """ID of the active music stream, or ``None``."""
        ...

    @property
    def music_generation(self) -> int:
        """Generation token of the current music stream."""
        ...

    def set_master_volume(self, volume: float) -> None:
        """Set the master volume (clamped to 0.0-1.0)."""
        ...

    def set_sfx_volume(self, volume: float) -> None:
        """Set the SFX bus volume (clamped to 0.0-1.0)."""
        ...

    def set_music_volume(self, volume: float) -> None:
        """Set the music bus volume (clamped to 0.0-1.0)."""
        ...

    def set_listener(self, x: float | INodeUnit, y: float | None = None) -> None:
        """Set fixed listener coordinates, or follow a node with ``.transform``."""
        ...

    def clear_listener_follow(self) -> None:
        """Stop following the listener node; keep the last position."""
        ...

    def set_spatial_params(
        self, min_distance: float, max_distance: float, rolloff: float = 1.0
    ) -> None:
        """Set global spatial attenuation parameters."""
        ...

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base directory for subsequent loads."""
        ...

    def load_sound(
        self,
        path: str | Path,
        *,
        sound_id: str | None = None,
        default_volume: float = 1.0,
        group: str | None = None,
    ) -> str:
        """Load an SFX and return its ID."""
        ...

    def load_music(
        self,
        path: str | Path,
        *,
        music_id: str | None = None,
        default_volume: float = 1.0,
        default_loop: bool = True,
        group: str | None = None,
    ) -> str:
        """Load a music stream and return its ID."""
        ...

    def load_bank(self, path: str | Path) -> str:
        """Eagerly load a JSON sound bank and return the bank ID."""
        ...

    def unload_sound(self, sound_id: str) -> None:
        """Stop voices of a sound and unload it."""
        ...

    def unload_music(self, music_id: str) -> None:
        """Stop (if active) and unload a music stream."""
        ...

    def clear_all(self) -> None:
        """Unload every sound and music stream."""
        ...

    def play_sound(
        self,
        sound_id: str,
        *,
        volume: float | None = None,
        pitch: float = 1.0,
        pan: float = 0.5,
    ) -> VoiceId:
        """Play a non-spatial one-shot SFX."""
        ...

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
        """Play an SFX at a world position.

        Args:
            sound_id: Loaded sound ID.
            x: Source world X coordinate.
            y: Source world Y coordinate.
            volume: Instance volume, or ``None`` for the asset default.
            pitch: Positive pitch multiplier.
            track: Recompute attenuation and pan when the listener or source
                moves. Otherwise freeze both at playback time.

        Returns:
            A voice token owned by this audio service.
        """
        ...

    def set_voice_position(self, voice_id: VoiceId, x: float, y: float) -> None:
        """Move a tracked voice."""
        ...

    def is_voice_playing(self, voice_id: VoiceId) -> bool:
        """Return True if the voice is still active."""
        ...

    def stop_voice(self, voice_id: VoiceId) -> None:
        """Stop one voice."""
        ...

    def stop_all_sounds(self) -> None:
        """Stop every SFX voice."""
        ...

    def play_music(
        self,
        music_id: str,
        *,
        loop: bool | None = None,
        volume: float | None = None,
    ) -> int:
        """Start a music stream and return its generation token."""
        ...

    def stop_music(self) -> None:
        """Stop the active music stream."""
        ...

    def pause_music(self) -> None:
        """Pause the active music stream."""
        ...

    def resume_music(self) -> None:
        """Resume the active music stream."""
        ...

    def is_music_playing(self) -> bool:
        """Return True if the active music stream is playing."""
        ...

    def owns_music(self, generation: int, music_id: str | None = None) -> bool:
        """Return whether a token still owns music, including while paused.

        Args:
            generation: Token returned by ``play_music`` on this service.
            music_id: Optional asset ID to match as well.

        Returns:
            Whether the token identifies the current live music playback.
        """
        ...


__all__ = ["IAudio"]
