"""AudioSource ownership tests with mocks and a structurally registered fake."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import get_protocol_members
from unittest.mock import MagicMock

import pytest

from plyunit.backends.ports.audio import IAudio
from plyunit.core.components.builtin.audio_source import AudioSource
from plyunit.core.components.transform import TransformState
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.services.audio import VoiceId


def _audio() -> MagicMock:
    """Build an active audio port mock with default playback responses.

    Returns:
        The canonical service mock.
    """
    audio = MagicMock(spec=IAudio)
    audio.active = True
    audio.play_sound.return_value = VoiceId(1)
    audio.play_sound_at.return_value = VoiceId(9)
    audio.play_music.return_value = 1
    audio.owns_music.return_value = True
    audio.is_voice_playing.return_value = True
    return audio


def _make_unit(audio: IAudio | None = None) -> SimpleNamespace:
    """Create a transform owner with a structural service registry.

    Args:
        audio: Optional audio service.

    Returns:
        The component owner.
    """
    unit = SimpleNamespace(
        global_units=SimpleNamespace(
            _service_order={} if audio is None else {id(audio): audio}
        ),
        transform=TransformState(),
    )
    unit.transform.set_position(0.0, 0.0)
    unit.transform.recalc_world(None)
    return unit


def test_pause_resume_music() -> None:
    """Pause and resume use this component's original music generation."""
    audio = _audio()
    source = AudioSource("bgm", kind="music")
    source.unit = _make_unit(audio)
    source.play()
    source.pause()
    source.resume()
    audio.pause_music.assert_called_once()
    audio.resume_music.assert_called_once()
    assert audio.owns_music.call_args_list == [((1, "bgm"),), ((1, "bgm"),)]


def test_pause_resume_sound_noop() -> None:
    """Sound sources never invoke music-stream controls."""
    audio = _audio()
    source = AudioSource("jump")
    source.unit = _make_unit(audio)
    source.play()
    source.pause()
    source.resume()
    audio.pause_music.assert_not_called()
    audio.resume_music.assert_not_called()


def test_replay_stops_previous_voice() -> None:
    """Replaying a source releases its existing voice first."""
    audio = _audio()
    audio.play_sound.side_effect = [VoiceId(1), VoiceId(2)]
    source = AudioSource("jump")
    source.unit = _make_unit(audio)
    source.play()
    source.play()
    audio.stop_voice.assert_called_once_with(VoiceId(1))
    assert source._voice_id == VoiceId(2)


def test_update_disabled() -> None:
    """Disabled components neither query playback nor move a tracked voice."""
    audio = _audio()
    source = AudioSource("jump", spatial=True)
    source.unit = _make_unit(audio)
    source.play()
    source.enabled = False
    source.update(0.016)
    audio.is_voice_playing.assert_not_called()
    audio.set_voice_position.assert_not_called()


def test_stop_without_service_clears_tokens() -> None:
    """Cleanup is safe for an unplayed or partially initialized component."""
    source = AudioSource("jump")
    source.unit = _make_unit()
    source._voice_id = VoiceId(1)
    source._music_generation = 3
    source._music_id = "bgm"
    source.stop()
    assert source._voice_id is None
    assert source._music_generation is None
    assert source._music_id is None


@pytest.mark.parametrize("spatial", [False, True])
def test_finished_one_shot_clears_id(spatial: bool) -> None:
    """Completed direct and spatial one-shots relinquish their local token."""
    audio = _audio()
    audio.is_voice_playing.return_value = False
    source = AudioSource("jump", spatial=spatial)
    source.unit = _make_unit(audio)
    source.play()
    source.update(0.016)
    assert source._voice_id is None
    assert source._playback_audio is None


def test_stale_music_cannot_control_new_owner() -> None:
    """A displaced source cannot stop, pause, or resume another generation."""
    audio = _audio()
    source = AudioSource("bgm", kind="music")
    source.unit = _make_unit(audio)
    source.play()
    audio.owns_music.return_value = False
    source.pause()
    source.resume()
    source.stop()
    audio.pause_music.assert_not_called()
    audio.resume_music.assert_not_called()
    audio.stop_music.assert_not_called()


def test_registry_replacement_does_not_steal_voice_token() -> None:
    """Cleanup uses the issuing service even if another service reuses its ID."""
    original, replacement = _audio(), _audio()
    unit = _make_unit(original)
    source = AudioSource("jump")
    source.unit = unit
    source.play()
    unit.global_units._service_order = {id(replacement): replacement}
    source.stop()
    original.stop_voice.assert_called_once_with(VoiceId(1))
    replacement.stop_voice.assert_not_called()


def test_registry_replacement_does_not_steal_music_generation() -> None:
    """Music controls remain bound to the issuing service, not a new registry owner."""
    original, replacement = _audio(), _audio()
    unit = _make_unit(original)
    source = AudioSource("bgm", kind="music")
    source.unit = unit
    source.play()
    unit.global_units._service_order = {id(replacement): replacement}
    source.pause()
    source.resume()
    source.stop()
    original.pause_music.assert_called_once()
    original.resume_music.assert_called_once()
    original.stop_music.assert_called_once()
    replacement.owns_music.assert_not_called()
    replacement.stop_music.assert_not_called()


def test_cleanup_failure_still_clears_source_state() -> None:
    """An adapter error cannot leave a component holding a stale token."""
    audio = _audio()
    audio.stop_voice.side_effect = RuntimeError("stop failed")
    source = AudioSource("jump")
    source.unit = _make_unit(audio)
    source.play()
    with pytest.raises(RuntimeError, match="stop failed"):
        source.stop()
    assert source._voice_id is None
    assert source._playback_audio is None


def test_nonconcrete_structural_service_uses_real_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover a renamed audio service without concrete backend inheritance."""
    registry = UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", registry
    )
    contract = _audio()

    class SilentAudio(ServiceUnit):
        """Provide the audio surface structurally, with a different service name."""

        def __init__(self) -> None:
            """Populate audio methods before ServiceUnit finalizes registration."""
            super().__init__("SilentAudio")
            for name in get_protocol_members(IAudio):
                if not hasattr(self, name):
                    setattr(self, name, getattr(contract, name))
            self.active = True

    service = SilentAudio()
    assert isinstance(service, IAudio)
    unit = _make_unit()
    unit.global_units = registry
    source = AudioSource("jump")
    source.unit = unit
    source.play()
    contract.play_sound.assert_called_once_with("jump", volume=1.0, pitch=1.0)
    registry.unregister(service)
    source.stop()
    contract.stop_voice.assert_called_once_with(VoiceId(1))
