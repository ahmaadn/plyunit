from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.audio import Audio
from plyunit.core.app import AudioConfig
from plyunit.backends.integrations.raylib.audio import (
    AudioBackend,
    backend as audio_backend,
    get_audio_backend,
)


@pytest.fixture()
def pr(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    mock.is_audio_device_ready.return_value = True
    mock.is_sound_playing.return_value = True
    mock.is_music_stream_playing.return_value = True
    mock.load_sound.return_value = "snd"
    mock.load_sound_alias.return_value = "alias"
    mock.load_music_stream.return_value = "mus"
    monkeypatch.setattr("plyunit.backends.integrations.raylib.audio.backend.pr", mock)
    return mock


def test_audio_service_from_config() -> None:
    cfg = AudioConfig(
        enabled=True,
        master_volume=0.5,
        sfx_volume=0.7,
        music_volume=0.3,
        max_voices=4,
        assets_path="./sfx",
        spatial_min_distance=10.0,
        spatial_max_distance=100.0,
        spatial_rolloff=2.0,
    )
    svc = Audio.from_config(cfg)
    assert svc.name == "Audio"
    assert svc.backend is get_audio_backend()
    assert svc._max_voices == 4  # noqa: SLF001
    assert svc._master_volume == 0.5  # noqa: SLF001


def test_device_lifecycle(pr: MagicMock) -> None:
    be = AudioBackend()
    be.init_device()
    pr.init_audio_device.assert_called_once()
    assert be.is_device_ready() is True
    be.set_master_volume(0.4)
    pr.set_master_volume.assert_called_with(0.4)
    be.close_device()
    pr.close_audio_device.assert_called_once()
    assert be._ready is False  # noqa: SLF001


def test_sound_play_stop(pr: MagicMock) -> None:
    be = AudioBackend()
    raw = be.load_sound("a.wav")
    assert raw == "snd"
    voice = be.play_sound(raw, 0.5, 1.2, 0.25)
    assert voice == ("alias", "alias")
    pr.load_sound_alias.assert_called_with("snd")
    pr.set_sound_volume.assert_called()
    pr.set_sound_pitch.assert_called()
    pr.set_sound_pan.assert_called()
    pr.play_sound.assert_called_with("alias")
    assert be.is_voice_playing(voice) is True
    be.set_voice_volume(voice, 0.1)
    be.set_voice_pitch(voice, 0.9)
    be.set_voice_pan(voice, 0.8)
    be.stop_voice(voice)
    pr.stop_sound.assert_called_with("alias")
    pr.unload_sound_alias.assert_called_with("alias")
    be.unload_sound(raw)
    pr.unload_sound.assert_called_with("snd")


def test_music_stream(pr: MagicMock) -> None:
    be = AudioBackend()
    mus = be.load_music_stream("m.ogg")
    assert mus == "mus"
    be.set_music_volume(mus, 0.6)
    pr.set_music_volume.assert_called_with("mus", 0.6)
    be.play_music_stream(mus)
    pr.play_music_stream.assert_called_with("mus")
    be.update_music_stream(mus)
    pr.update_music_stream.assert_called_with("mus")
    assert be.is_music_stream_playing(mus) is True
    be.pause_music_stream(mus)
    be.resume_music_stream(mus)
    be.stop_music_stream(mus)
    be.unload_music_stream(mus)
    pr.unload_music_stream.assert_called_with("mus")


def test_music_looping_via_attribute(pr: MagicMock) -> None:
    be = AudioBackend()
    mus = SimpleNamespace(looping=False)
    be.set_music_looping(mus, True)
    assert mus.looping is True


def test_unpack_requires_tuple(pr: MagicMock) -> None:
    with pytest.raises(TypeError, match="tuple"):
        audio_backend._unpack("raw")  # noqa: SLF001
