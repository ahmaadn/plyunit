from __future__ import annotations

import json
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from plyunit.audio.service import Audio
from plyunit.events.signal import Signal
from plyunit.core.units.unit_registry import UnitRegistry

# pyrefly: ignore [missing-import]
from fake_backend import FakeBackend


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


@pytest.fixture()
def audio_dir(tmp_path: Path) -> Path:
    (tmp_path / "sfx").mkdir()
    (tmp_path / "music").mkdir()
    (tmp_path / "sfx" / "jump.wav").write_bytes(b"RIFF")
    (tmp_path / "music" / "title.ogg").write_bytes(b"OggS")
    return tmp_path


@pytest.fixture()
def svc(audio_dir: Path) -> tuple[Audio, FakeBackend]:
    backend = FakeBackend()
    service = Audio(backend, assets_path=audio_dir, max_voices=2)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)  # type: ignore[arg-type]
    assert service.active
    return service, backend


def test_load_play_stop(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    sid = service.load_sound("sfx/jump.wav", sound_id="jump")
    assert sid == "jump"
    vid = service.play_sound("jump", volume=0.5)
    assert service.is_voice_playing(vid)
    service.stop_voice(vid)
    assert not service.is_voice_playing(vid)
    assert backend.playing_voices[1]["playing"] is False


def test_volume_bus_multiplication(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    service.set_master_volume(0.5)
    service.set_sfx_volume(0.5)
    service.play_sound("jump", volume=0.5)
    # master * sfx * instance = 0.5 * 0.5 * 0.5 = 0.125
    assert abs(backend.playing_voices[1]["volume"] - 0.125) < 1e-6


def test_spatial_play_at_and_track(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    service.set_listener(0.0, 0.0)
    vid = service.play_sound_at("jump", 425.0, 0.0, volume=1.0, track=True)
    # mid attenuation ~0.5 with defaults min=50 max=800
    assert abs(backend.playing_voices[1]["volume"] - 0.5) < 1e-3
    service.set_voice_position(vid, 0.0, 0.0)
    assert abs(backend.playing_voices[1]["volume"] - 1.0) < 1e-6


def test_max_voices_stops_oldest(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    v1 = service.play_sound("jump")
    v2 = service.play_sound("jump")
    v3 = service.play_sound("jump")
    assert not service.is_voice_playing(v1)
    assert service.is_voice_playing(v2)
    assert service.is_voice_playing(v3)
    assert len(service._voices) == 2  # noqa: SLF001


def test_path_escape(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    with pytest.raises(ValueError, match="escapes"):
        service.load_sound("../secret.wav")


def test_missing_file(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    with pytest.raises(FileNotFoundError):
        service.load_sound("sfx/missing.wav")


def test_unknown_sound(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    with pytest.raises(KeyError):
        service.play_sound("nope")


def test_play_while_inactive(audio_dir: Path) -> None:
    backend = FakeBackend()
    service = Audio(backend, assets_path=audio_dir)
    with pytest.raises(RuntimeError, match="not active"):
        service.load_sound("sfx/jump.wav")


def test_music_play_stop_and_frame_update(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, backend = svc
    service.load_music("music/title.ogg", music_id="bgm")
    gen = service.play_music("bgm", loop=True, volume=0.5)
    assert service.is_music_playing()
    assert service.owns_music(gen, "bgm")
    service._on_start_frame()  # noqa: SLF001
    assert backend.updated
    service.stop_music()
    assert not service.is_music_playing()
    assert not service.owns_music(gen, "bgm")


def test_load_bank(svc: tuple[Audio, FakeBackend], audio_dir: Path) -> None:
    service, _ = svc
    bank = {
        "id": "main",
        "base_path": ".",
        "entries": [
            {
                "id": "jump",
                "path": "sfx/jump.wav",
                "kind": "sound",
                "volume": 0.9,
            },
            {
                "id": "bgm",
                "path": "music/title.ogg",
                "kind": "music",
                "volume": 0.6,
                "loop": True,
            },
        ],
    }
    (audio_dir / "bank.json").write_text(json.dumps(bank), encoding="utf-8")
    assert service.load_bank("bank.json") == "main"
    service.play_sound("jump")
    service.play_music("bgm")
    assert service.is_music_playing()


def test_attach_detach_idempotent(audio_dir: Path) -> None:
    backend = FakeBackend()
    service = Audio(backend, assets_path=audio_dir)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)  # type: ignore[arg-type]
    service.load_sound("sfx/jump.wav", sound_id="jump")
    service.play_sound("jump")
    service.on_detach(app)  # type: ignore[arg-type]
    assert backend.close_calls == 1
    assert not service.active
    service.on_detach(app)  # type: ignore[arg-type]
    assert backend.close_calls == 1
