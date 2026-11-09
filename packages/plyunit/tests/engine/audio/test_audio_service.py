"""Policy tests for the raylib audio service through its canonical API."""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_raylib import FakeRaylib

from plyunit.backends.integrations.raylib.audio import Audio
from plyunit.backends.ports.audio import IAudio
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.signal import Signal
from plyunit.services.audio import VoiceId


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    """Isolate service ownership from other test modules.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The test's empty global registry.
    """
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


@pytest.fixture
def audio_dir(tmp_path: Path) -> Path:
    """Create test asset paths without requiring actual decoders.

    Args:
        tmp_path: Test's temporary directory.

    Returns:
        The asset root.
    """
    (tmp_path / "sfx").mkdir()
    (tmp_path / "music").mkdir()
    (tmp_path / "sfx" / "jump.wav").write_bytes(b"RIFF")
    (tmp_path / "music" / "title.ogg").write_bytes(b"OggS")
    return tmp_path


@pytest.fixture
def raylib(monkeypatch: pytest.MonkeyPatch) -> FakeRaylib:
    """Patch the integration's native module rather than inject a backend.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The native call test double.
    """
    fake = FakeRaylib()
    module = importlib.import_module("plyunit.backends.integrations.raylib.audio")
    monkeypatch.setattr(module, "pr", fake)
    handler = importlib.import_module("plyunit.backends.integrations.raylib.handler")
    monkeypatch.setattr(handler, "pr", fake)
    return fake


@pytest.fixture
def svc(audio_dir: Path, raylib: FakeRaylib) -> Iterator[tuple[Audio, FakeRaylib]]:
    """Attach a service with a small voice limit and tear it down afterward.

    Args:
        audio_dir: Test asset root.
        raylib: Native call test double.

    Yields:
        The attached audio service and native test double.
    """
    service = Audio(assets_path=audio_dir, max_voices=2)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    assert service.active
    yield service, raylib
    service.on_detach(app)


def test_load_play_stop(svc: tuple[Audio, FakeRaylib]) -> None:
    """A stopped voice releases its alias while retaining the source samples."""
    service, native = svc
    assert isinstance(service, IAudio)
    assert service.load_sound("sfx/jump.wav", sound_id="jump") == "jump"
    voice = service.play_sound("jump", volume=0.5)
    assert isinstance(voice, int)
    assert service.is_voice_playing(voice)
    alias = native.aliases[-1]
    service.stop_voice(voice)
    service.stop_voice(voice)
    assert not service.is_voice_playing(voice)
    assert alias.unloaded
    assert not alias.source.unloaded
    assert native.calls.count(("unload_sound_alias", alias)) == 1


def test_volume_bus_multiplication(svc: tuple[Audio, FakeRaylib]) -> None:
    """Device master gain is applied exactly once to both buses."""
    service, native = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    service.load_music("music/title.ogg", music_id="bgm")
    service.set_master_volume(0.5)
    service.set_sfx_volume(0.5)
    service.set_music_volume(0.5)
    service.play_sound("jump", volume=0.5)
    service.play_music("bgm", volume=0.5)
    alias = native.aliases[-1]
    music = service._music["bgm"].raw
    assert alias.volume == pytest.approx(0.25)
    assert music.volume == pytest.approx(0.25)
    assert native.master * alias.volume == pytest.approx(0.125)
    assert native.master * music.volume == pytest.approx(0.125)
    service.set_master_volume(0.2)
    assert native.master * alias.volume == pytest.approx(0.05)
    assert native.master * music.volume == pytest.approx(0.05)
    service.set_sfx_volume(0.4)
    service.set_music_volume(0.4)
    assert alias.volume == pytest.approx(0.2)
    assert music.volume == pytest.approx(0.2)


def test_spatial_play_at_and_track(svc: tuple[Audio, FakeRaylib]) -> None:
    """Tracked voice positions recompute volume and native pan immediately."""
    service, native = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    voice = service.play_sound_at("jump", 425.0, 0.0, track=True)
    alias = native.aliases[-1]
    assert alias.volume == pytest.approx(0.5)
    assert alias.pan == pytest.approx(425.0 / 800.0)
    service.set_voice_position(voice, 0.0, 0.0)
    assert alias.volume == 1.0
    assert alias.pan == 0.0


def test_max_voices_stops_oldest(svc: tuple[Audio, FakeRaylib]) -> None:
    """Capacity steals the oldest live alias without disrupting newer ones."""
    service, native = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    first = service.play_sound("jump")
    second = service.play_sound("jump")
    third = service.play_sound("jump")
    assert not service.is_voice_playing(first)
    assert service.is_voice_playing(second)
    assert service.is_voice_playing(third)
    assert native.aliases[0].unloaded
    assert len(service._voices) == 2


def test_finished_voice_is_reclaimed_before_stealing(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """A finished newer voice frees capacity instead of stealing a live voice."""
    service, native = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    first = service.play_sound("jump")
    finished = service.play_sound("jump")
    native.aliases[-1].playing = False
    third = service.play_sound("jump")
    assert service.is_voice_playing(first)
    assert not service.is_voice_playing(finished)
    assert service.is_voice_playing(third)
    assert native.aliases[1].unloaded


def test_frame_reclaims_finished_aliases(svc: tuple[Audio, FakeRaylib]) -> None:
    """Frame maintenance unloads a completed alias exactly once."""
    service, native = svc
    service.load_sound("sfx/jump.wav", sound_id="jump")
    voice = service.play_sound_at("jump", 0.0, 0.0, track=True)
    alias = native.aliases[-1]
    alias.playing = False
    service._on_start_frame()
    service._on_start_frame()
    assert voice not in service._voices
    assert native.calls.count(("unload_sound_alias", alias)) == 1


def test_path_escape(svc: tuple[Audio, FakeRaylib], tmp_path: Path) -> None:
    """Relative and absolute paths cannot escape the configured asset root."""
    service, _ = svc
    with pytest.raises(ValueError, match="escapes"):
        service.load_sound("../secret.wav")
    with pytest.raises(ValueError, match="escapes"):
        service.load_music(tmp_path.parent / "secret.ogg")


@pytest.mark.parametrize("method", ["load_sound", "load_music", "load_bank"])
def test_missing_file(svc: tuple[Audio, FakeRaylib], method: str) -> None:
    """Missing assets fail before making native load calls."""
    service, _ = svc
    with pytest.raises(FileNotFoundError):
        getattr(service, method)("missing.file")


@pytest.mark.parametrize("method", ["play_sound", "play_music"])
def test_unknown_asset(svc: tuple[Audio, FakeRaylib], method: str) -> None:
    """Unknown playback IDs fail explicitly."""
    service, _ = svc
    with pytest.raises(KeyError):
        getattr(service, method)("unknown")


def test_inactive_operations(audio_dir: Path, raylib: FakeRaylib) -> None:
    """Creation/playback fail inactive while buses and cleanup remain safe."""
    service = Audio(assets_path=audio_dir)
    for method, args in (
        (service.load_sound, ("sfx/jump.wav",)),
        (service.load_music, ("music/title.ogg",)),
        (service.load_bank, ("bank.json",)),
        (service.play_sound, ("jump",)),
        (service.play_sound_at, ("jump", 0.0, 0.0)),
        (service.play_music, ("bgm",)),
    ):
        with pytest.raises(RuntimeError, match="not active"):
            method(*args)
    service.set_master_volume(0.4)
    service.set_sfx_volume(0.4)
    service.set_music_volume(0.4)
    service.set_listener(1.0, 2.0)
    service.set_spatial_params(1.0, 10.0)
    service.stop_voice(VoiceId(999))
    service.stop_all_sounds()
    service.stop_music()
    service.pause_music()
    service.resume_music()
    service.clear_all()
    service._on_start_frame()
    assert not service.is_voice_playing(VoiceId(999))
    assert not service.is_music_playing()
    assert not service.owns_music(0)
    assert raylib.calls == []


def test_music_play_stop_and_frame_update(svc: tuple[Audio, FakeRaylib]) -> None:
    """Live music pumps every frame and stop invalidates its generation."""
    service, native = svc
    service.load_music("music/title.ogg", music_id="bgm")
    generation = service.play_music("bgm", loop=True, volume=0.5)
    assert service.is_music_playing()
    assert service.owns_music(generation, "bgm")
    service._on_start_frame()
    assert native.updated == [service._music["bgm"].raw]
    service.stop_music()
    assert service.music_generation > generation
    assert not service.is_music_playing()
    assert not service.owns_music(generation, "bgm")


def test_load_bank(svc: tuple[Audio, FakeRaylib], audio_dir: Path) -> None:
    """Banks load defaults and metadata without introducing group buses."""
    service, native = svc
    bank = {
        "id": "main",
        "base_path": ".",
        "entries": [
            {"id": "jump", "path": "sfx/jump.wav", "volume": 0.9, "group": "sfx"},
            {
                "id": "bgm",
                "path": "music/title.ogg",
                "kind": "music",
                "volume": 0.6,
                "loop": False,
            },
        ],
    }
    (audio_dir / "bank.json").write_text(json.dumps(bank), encoding="utf-8")
    assert service.load_bank("bank.json") == "main"
    service.play_sound("jump")
    service.play_music("bgm")
    assert native.aliases[-1].volume == pytest.approx(0.9)
    assert service._sounds["jump"].group == "sfx"
    assert service._music["bgm"].raw.volume == pytest.approx(0.6)
    assert service._music["bgm"].raw.looping is False


def test_attach_detach_idempotent(audio_dir: Path, raylib: FakeRaylib) -> None:
    """Repeated lifecycle hooks do not reopen or double-close the device."""
    service = Audio(assets_path=audio_dir)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    service.on_attach(app)
    assert raylib.init_calls == 1
    assert len(app.on_start_frame) == 1
    service.load_sound("sfx/jump.wav", sound_id="jump")
    service.play_sound("jump")
    service.on_detach(app)
    service.on_detach(app)
    assert raylib.close_calls == 1
    assert not service.active
    assert len(app.on_start_frame) == 0
    assert service._sounds == {}
    assert service._voices == {}
