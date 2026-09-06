from __future__ import annotations

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
    (tmp_path / "sfx" / "a.wav").write_bytes(b"x")
    (tmp_path / "music" / "m.ogg").write_bytes(b"y")
    return tmp_path


@pytest.fixture()
def svc(audio_dir: Path) -> tuple[Audio, FakeBackend]:
    backend = FakeBackend()
    service = Audio(backend, assets_path=audio_dir, max_voices=4)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)  # type: ignore[arg-type]
    return service, backend


def test_reload_sound_unloads_previous(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc
    service.load_sound("sfx/a.wav", sound_id="a")
    service.play_sound("a")
    service.load_sound("sfx/a.wav", sound_id="a")
    assert "a" in service._sounds  # noqa: SLF001


def test_unload_music_while_playing(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc
    service.load_music("music/m.ogg", music_id="m")
    service.play_music("m")
    service.unload_music("m")
    assert not service.is_music_playing()
    assert service.active_music_id is None


def test_pause_resume_music(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_music("music/m.ogg", music_id="m")
    service.play_music("m")
    service.pause_music()
    assert backend.music_playing[service._music["m"].raw] is False  # noqa: SLF001
    service.resume_music()
    assert backend.music_playing[service._music["m"].raw] is True  # noqa: SLF001


def test_set_music_volume_bus(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_music("music/m.ogg", music_id="m")
    service.play_music("m", volume=1.0)
    service.set_music_volume(0.5)
    raw = service._music["m"].raw  # noqa: SLF001
    assert abs(backend.music_volume[raw] - 0.5) < 1e-6


def test_set_sfx_volume_updates_non_tracked(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, backend = svc
    service.load_sound("sfx/a.wav", sound_id="a")
    service.play_sound("a", volume=1.0)
    service.set_sfx_volume(0.25)
    assert abs(backend.playing_voices[1]["volume"] - 0.25) < 1e-6


def test_getters(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    service.set_master_volume(0.2)
    service.set_sfx_volume(0.3)
    service.set_music_volume(0.4)
    assert service.master_volume == 0.2
    assert service.sfx_volume == 0.3
    assert service.music_volume == 0.4
    assert service.listener == (0.0, 0.0)
    service.set_listener(1.0, 2.0)
    assert service.listener == (1.0, 2.0)
    assert service.listener_node is None


def test_set_listener_follow_node(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    service.load_sound("sfx/a.wav", sound_id="a")

    class FakeWorld:
        position = (10.0, 20.0)

    class FakeTransform:
        world = FakeWorld()

    class FakeNode:
        transform = FakeTransform()

    node = FakeNode()
    service.set_listener(node)
    assert service.listener == (10.0, 20.0)
    assert service.listener_node is node

    # tracked voice updates when node moves + frame sync
    vid = service.play_sound_at("a", 10.0, 20.0, track=True)
    FakeWorld.position = (100.0, 20.0)
    service._on_start_frame()  # noqa: SLF001
    assert service.listener == (100.0, 20.0)
    # source still at (10,20), listener at (100,20) → pan left of center
    assert backend.playing_voices[vid]["pan"] < 0.5

    # fixed coords clear follow
    service.set_listener(0.0, 0.0)
    assert service.listener_node is None
    assert service.listener == (0.0, 0.0)


def test_set_listener_node_without_transform_raises(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc
    with pytest.raises(TypeError, match="transform"):
        service.set_listener(object())


def test_clear_listener_follow(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc

    class FakeWorld:
        position = (5.0, 6.0)

    class FakeTransform:
        world = FakeWorld()

    class FakeNode:
        transform = FakeTransform()

    service.set_listener(FakeNode())
    service.clear_listener_follow()
    assert service.listener_node is None
    assert service.listener == (5.0, 6.0)


def test_listener_property_reads_node_live(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc

    class FakeWorld:
        position = (1.0, 2.0)

    class FakeTransform:
        world = FakeWorld()

    class FakeNode:
        transform = FakeTransform()

    service.set_listener(FakeNode())
    FakeWorld.position = (9.0, 8.0)
    # Without waiting for on_start_frame — property reads node live
    assert service.listener == (9.0, 8.0)


def test_set_spatial_params_validation(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc
    with pytest.raises(ValueError):
        service.set_spatial_params(-1, 10)
    with pytest.raises(ValueError):
        service.set_spatial_params(10, 5)
    with pytest.raises(ValueError):
        service.set_spatial_params(1, 10, 0)
    service.set_spatial_params(1.0, 100.0, 1.5)


def test_default_volume_from_entry(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, backend = svc
    service.load_sound("sfx/a.wav", sound_id="a", default_volume=0.5)
    service.play_sound("a")
    assert abs(backend.playing_voices[1]["volume"] - 0.5) < 1e-6


def test_second_music_stops_first(
    svc: tuple[Audio, FakeBackend], audio_dir: Path
) -> None:
    service, _ = svc
    (audio_dir / "music" / "m2.ogg").write_bytes(b"z")
    service.load_music("music/m.ogg", music_id="m1")
    service.load_music("music/m2.ogg", music_id="m2")
    g1 = service.play_music("m1")
    g2 = service.play_music("m2")
    assert not service.owns_music(g1, "m1")
    assert service.owns_music(g2, "m2")
    assert service.active_music_id == "m2"
    assert service.music_generation == g2


def test_stop_music_when_none(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    service.stop_music()
    service.pause_music()
    service.resume_music()
    assert not service.is_music_playing()


def test_set_voice_position_unknown(
    svc: tuple[Audio, FakeBackend],
) -> None:
    service, _ = svc
    from plyunit.audio.types import VoiceId

    service.set_voice_position(VoiceId(999), 1.0, 2.0)


def test_clear_all(svc: tuple[Audio, FakeBackend]) -> None:
    service, _ = svc
    service.load_sound("sfx/a.wav", sound_id="a")
    service.load_music("music/m.ogg", music_id="m")
    service.play_sound("a")
    service.play_music("m")
    service.clear_all()
    assert service._sounds == {}  # noqa: SLF001
    assert service._music == {}  # noqa: SLF001


def test_attach_init_failure(audio_dir: Path) -> None:
    backend = FakeBackend()

    def boom() -> None:
        raise RuntimeError("no device")

    backend.init_device = boom  # type: ignore[method-assign]
    service = Audio(backend, assets_path=audio_dir)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)  # type: ignore[arg-type]
    assert service.active is False


def test_bank_missing_entry_fields(
    svc: tuple[Audio, FakeBackend], audio_dir: Path
) -> None:
    import json

    service, _ = svc
    (audio_dir / "bad.json").write_text(
        json.dumps({"entries": [{"id": "x"}]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="id/path"):
        service.load_bank("bad.json")


def test_bank_unknown_kind(
    svc: tuple[Audio, FakeBackend], audio_dir: Path
) -> None:
    import json

    service, _ = svc
    (audio_dir / "bad2.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"id": "x", "path": "sfx/a.wav", "kind": "noise"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kind"):
        service.load_bank("bad2.json")


def test_backend_property(svc: tuple[Audio, FakeBackend]) -> None:
    service, backend = svc
    assert service.backend is backend


def test_start_frame_inactive(audio_dir: Path) -> None:
    backend = FakeBackend()
    service = Audio(backend, assets_path=audio_dir)
    service._on_start_frame()  # noqa: SLF001


def test_set_assets_path(svc: tuple[Audio, FakeBackend], tmp_path: Path) -> None:
    service, _ = svc
    service.set_assets_path(tmp_path / "other")
