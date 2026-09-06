from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from plyunit.core.components.builtin.audio_source import AudioSource
from plyunit.core.components.transform import TransformState
from plyunit.audio.types import VoiceId


def _make_unit(audio_service=None):
    unit = SimpleNamespace()
    unit.transform = TransformState()
    unit.transform.set_position(0.0, 0.0)
    unit.transform.recalc_world(None)

    def one(name):
        if name == "Audio":
            if audio_service is None:
                raise LookupError("missing")
            return audio_service
        raise LookupError(name)

    def one_or_none(name):
        try:
            return one(name)
        except LookupError:
            return None

    unit.one = one
    unit.one_or_none = one_or_none
    return unit


def test_pause_resume_music() -> None:
    audio = MagicMock()
    audio.play_music.return_value = 1
    audio.owns_music.return_value = True
    unit = _make_unit(audio)
    src = AudioSource("bgm", kind="music")
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.pause()
    audio.pause_music.assert_called_once()
    src.resume()
    audio.resume_music.assert_called_once()


def test_pause_resume_sound_noop() -> None:
    audio = MagicMock()
    audio.play_sound.return_value = VoiceId(1)
    unit = _make_unit(audio)
    src = AudioSource("jump")
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.pause()
    src.resume()
    audio.pause_music.assert_not_called()


def test_replay_stops_previous_voice() -> None:
    audio = MagicMock()
    audio.play_sound.side_effect = [VoiceId(1), VoiceId(2)]
    unit = _make_unit(audio)
    src = AudioSource("jump")
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.play()
    audio.stop_voice.assert_called_with(VoiceId(1))


def test_update_disabled() -> None:
    audio = MagicMock()
    unit = _make_unit(audio)
    src = AudioSource("jump", spatial=True)
    src.unit = unit  # type: ignore[assignment]
    src.enabled = False
    src.update(0.016)
    audio.set_voice_position.assert_not_called()


def test_stop_without_service() -> None:
    unit = _make_unit(None)
    src = AudioSource("jump")
    src.unit = unit  # type: ignore[assignment]
    src._voice_id = VoiceId(1)  # noqa: SLF001
    src.stop()
    assert src._voice_id is None  # noqa: SLF001


def test_spatial_voice_finished_clears_id() -> None:
    audio = MagicMock()
    audio.play_sound_at.return_value = VoiceId(9)
    audio.is_voice_playing.return_value = False
    unit = _make_unit(audio)
    src = AudioSource("jump", spatial=True)
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.update(0.016)
    assert src._voice_id is None  # noqa: SLF001
