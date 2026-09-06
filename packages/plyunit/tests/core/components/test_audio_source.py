from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.core.components.builtin.audio_source import AudioSource
from plyunit.core.components.transform import TransformState
from plyunit.audio.types import VoiceId


def _make_unit(audio_service=None):
    unit = SimpleNamespace()
    unit.transform = TransformState()
    unit.transform.set_position(10.0, 20.0)
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


def test_music_spatial_raises() -> None:
    with pytest.raises(ValueError, match="spatial"):
        AudioSource("bgm", kind="music", spatial=True)


def test_auto_play_sound() -> None:
    audio = MagicMock()
    audio.play_sound.return_value = VoiceId(1)
    audio.is_voice_playing.return_value = True
    unit = _make_unit(audio)
    src = AudioSource("jump", auto_play=True, volume=0.8)
    src.unit = unit  # type: ignore[assignment]
    src.on_start()
    audio.play_sound.assert_called_once_with("jump", volume=0.8, pitch=1.0)


def test_spatial_play_and_update() -> None:
    audio = MagicMock()
    audio.play_sound_at.return_value = VoiceId(7)
    audio.is_voice_playing.return_value = True
    unit = _make_unit(audio)
    src = AudioSource("jump", spatial=True)
    src.unit = unit  # type: ignore[assignment]
    src.play()
    audio.play_sound_at.assert_called_once()
    args = audio.play_sound_at.call_args
    assert args[0][0] == "jump"
    assert args[0][1] == 10.0
    assert args[0][2] == 20.0
    assert args[1]["track"] is True
    unit.transform.set_position(30.0, 40.0)
    unit.transform.recalc_world(None)
    src.update(0.016)
    audio.set_voice_position.assert_called_with(VoiceId(7), 30.0, 40.0)


def test_destroy_stops_voice() -> None:
    audio = MagicMock()
    audio.play_sound.return_value = VoiceId(3)
    unit = _make_unit(audio)
    src = AudioSource("jump")
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.on_destroy()
    audio.stop_voice.assert_called_with(VoiceId(3))


def test_music_ownership_on_destroy() -> None:
    audio = MagicMock()
    audio.play_music.return_value = 5
    audio.owns_music.return_value = True
    unit = _make_unit(audio)
    src = AudioSource("bgm", kind="music", loop=True)
    src.unit = unit  # type: ignore[assignment]
    src.play()
    src.on_destroy()
    audio.owns_music.assert_called()
    audio.stop_music.assert_called_once()


def test_missing_service_raises() -> None:
    unit = _make_unit(None)
    src = AudioSource("jump")
    src.unit = unit  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="Audio"):
        src.play()


def test_loop_sfx_retriggers() -> None:
    audio = MagicMock()
    audio.play_sound.side_effect = [VoiceId(1), VoiceId(2)]
    audio.is_voice_playing.side_effect = [False]
    unit = _make_unit(audio)
    src = AudioSource("jump", loop=True)
    src.unit = unit  # type: ignore[assignment]
    src.play()
    assert src._voice_id == VoiceId(1)  # noqa: SLF001
    src.update(0.016)
    assert audio.play_sound.call_count == 2
