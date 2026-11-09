"""AudioSource playback tests using the audio port rather than host imports."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.backends.ports.audio import IAudio
from plyunit.core.components.builtin.audio_source import AudioSource
from plyunit.core.components.transform import TransformState
from plyunit.services.audio import VoiceId


def _make_unit(audio_service: IAudio | None = None) -> SimpleNamespace:
    """Create a node with a service registry and mutable world transform.

    Args:
        audio_service: Optional structural audio service.

    Returns:
        A node-shaped component owner.
    """
    services = {} if audio_service is None else {id(audio_service): audio_service}
    unit = SimpleNamespace(
        global_units=SimpleNamespace(_service_order=services),
        transform=TransformState(),
    )
    unit.transform.set_position(10.0, 20.0)
    unit.transform.recalc_world(None)
    return unit


def _audio() -> MagicMock:
    """Create a mock constrained to the canonical audio service protocol.

    Returns:
        An active structural audio service with deterministic playback tokens.
    """
    audio = MagicMock(spec=IAudio)
    audio.active = True
    audio.play_sound.return_value = VoiceId(1)
    audio.play_sound_at.return_value = VoiceId(7)
    audio.play_music.return_value = 5
    audio.is_voice_playing.return_value = True
    audio.owns_music.return_value = True
    return audio


def test_music_spatial_raises() -> None:
    """Music streams reject positional sound playback options."""
    with pytest.raises(ValueError, match="spatial"):
        AudioSource("bgm", kind="music", spatial=True)


def test_unknown_kind_raises() -> None:
    """Unknown asset kinds fail during component construction."""
    with pytest.raises(ValueError, match="kind"):
        AudioSource("noise", kind="noise")


def test_auto_play_sound() -> None:
    """Automatic start forwards per-instance values to the audio port."""
    audio = _audio()
    source = AudioSource("jump", auto_play=True, volume=0.8)
    source.unit = _make_unit(audio)
    source.on_start()
    audio.play_sound.assert_called_once_with("jump", volume=0.8, pitch=1.0)


def test_manual_source_does_not_auto_play() -> None:
    """The start hook is inert unless automatic playback is requested."""
    audio = _audio()
    source = AudioSource("jump")
    source.unit = _make_unit(audio)
    source.on_start()
    audio.play_sound.assert_not_called()


def test_spatial_play_and_update() -> None:
    """Spatial sources track their node's current 2D world position."""
    audio = _audio()
    unit = _make_unit(audio)
    source = AudioSource("jump", spatial=True)
    source.unit = unit
    source.play()
    audio.play_sound_at.assert_called_once_with(
        "jump", 10.0, 20.0, volume=1.0, pitch=1.0, track=True
    )
    unit.transform.set_position(30.0, 40.0)
    unit.transform.recalc_world(None)
    source.update(0.016)
    audio.set_voice_position.assert_called_once_with(VoiceId(7), 30.0, 40.0)
    audio.is_voice_playing.assert_called_once_with(VoiceId(7))


def test_destroy_stops_voice_once() -> None:
    """Destroy releases the owned voice and leaves no replay token."""
    audio = _audio()
    source = AudioSource("jump")
    source.unit = _make_unit(audio)
    source.play()
    source.on_destroy()
    source.stop()
    audio.stop_voice.assert_called_once_with(VoiceId(1))
    assert source._voice_id is None


def test_music_ownership_on_destroy() -> None:
    """Music destruction stops only the generation issued to this source."""
    audio = _audio()
    source = AudioSource("bgm", kind="music", loop=True)
    source.unit = _make_unit(audio)
    source.play()
    audio.play_music.assert_called_once_with("bgm", loop=True, volume=1.0)
    source.on_destroy()
    audio.owns_music.assert_called_once_with(5, "bgm")
    audio.stop_music.assert_called_once()
    assert source._music_generation is None


def test_missing_service_raises() -> None:
    """Playback requires a registered structural audio service."""
    source = AudioSource("jump")
    source.unit = _make_unit()
    with pytest.raises(RuntimeError, match="IAudio"):
        source.play()


def test_unattached_source_has_actionable_error() -> None:
    """Unattached playback reports the node requirement rather than AttributeError."""
    source = AudioSource("jump")
    with pytest.raises(RuntimeError, match="attached"):
        source.play()
    source.stop()
    source.pause()
    source.resume()


@pytest.mark.parametrize("spatial", [False, True])
def test_loop_sfx_retriggers(spatial: bool) -> None:
    """Both direct and spatial loops restart after their voice completes."""
    audio = _audio()
    playback = audio.play_sound_at if spatial else audio.play_sound
    playback.side_effect = [VoiceId(1), VoiceId(2)]
    audio.is_voice_playing.return_value = False
    source = AudioSource("jump", spatial=spatial, loop=True)
    source.unit = _make_unit(audio)
    source.play()
    source.update(0.016)
    assert playback.call_count == 2
    assert source._voice_id == VoiceId(2)
    audio.stop_voice.assert_not_called()


def test_loop_does_not_restart_after_explicit_stop() -> None:
    """Stopped looping sources remain stopped on later updates."""
    audio = _audio()
    source = AudioSource("jump", spatial=True, loop=True)
    source.unit = _make_unit(audio)
    source.play()
    source.stop()
    source.update(0.016)
    audio.play_sound_at.assert_called_once()


def test_inactive_owner_clears_loop_without_restarting() -> None:
    """Device teardown cannot make looping components create new native playback."""
    audio = _audio()
    source = AudioSource("jump", loop=True)
    source.unit = _make_unit(audio)
    source.play()
    audio.active = False
    source.update(0.016)
    assert source._voice_id is None
    audio.play_sound.assert_called_once()
    audio.is_voice_playing.assert_not_called()


def test_structural_service_lookup_rejects_ambiguity() -> None:
    """More than one audio port implementation is reported rather than guessed."""
    audio, other = _audio(), _audio()
    unit = _make_unit(audio)
    unit.global_units._service_order[id(other)] = other
    source = AudioSource("jump")
    source.unit = unit
    with pytest.raises(RuntimeError, match="exactly one"):
        source.play()
    audio.play_sound.assert_not_called()
    other.play_sound.assert_not_called()
