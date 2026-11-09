"""Listener, bus, loading, and music-ownership regression tests."""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_raylib import FakeRaylib, make_listener

from plyunit.backends.integrations.raylib.audio import Audio
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.signal import Signal
from plyunit.services.audio import VoiceId


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    """Provide independent global service ownership.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The test registry.
    """
    registry = UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", registry
    )
    return registry


@pytest.fixture
def audio_dir(tmp_path: Path) -> Path:
    """Create paths accepted by the mocked native loaders.

    Args:
        tmp_path: Test temporary directory.

    Returns:
        The audio asset directory.
    """
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    (tmp_path / "m.ogg").write_bytes(b"OggS")
    return tmp_path


@pytest.fixture
def raylib(monkeypatch: pytest.MonkeyPatch) -> FakeRaylib:
    """Replace only the audio integration's pyray calls.

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
    """Create an attached audio service with guaranteed teardown.

    Args:
        audio_dir: Audio asset directory.
        raylib: Native call test double.

    Yields:
        The audio service and native call test double.
    """
    service = Audio(assets_path=audio_dir, max_voices=4)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    yield service, raylib
    service.on_detach(app)


def test_reload_sound_unloads_previous(svc: tuple[Audio, FakeRaylib]) -> None:
    """Reload stops/unloads all old aliases before freeing their samples."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    old = service._sounds["a"].raw
    voice = service.play_sound("a")
    alias = native.aliases[-1]
    service.load_sound("a.wav", sound_id="a")
    assert alias.unloaded
    assert old.unloaded
    assert not service.is_voice_playing(voice)
    assert service._sounds["a"].raw is not old
    assert native.calls.index(("unload_sound_alias", alias)) < native.calls.index((
        "unload_sound",
        old,
    ))


def test_failed_sound_reload_preserves_previous(svc: tuple[Audio, FakeRaylib]) -> None:
    """An invalid replacement does not destroy the usable loaded sound."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    old = service._sounds["a"].raw
    voice = service.play_sound("a")
    native.invalid_sound = True
    with pytest.raises(RuntimeError, match="load sound"):
        service.load_sound("a.wav", sound_id="a")
    assert service._sounds["a"].raw is old
    assert service.is_voice_playing(voice)
    assert not old.unloaded


def test_unload_music_while_playing(svc: tuple[Audio, FakeRaylib]) -> None:
    """Unloading active music stops its decoder and invalidates ownership."""
    service, native = svc
    service.load_music("m.ogg", music_id="m")
    raw = service._music["m"].raw
    generation = service.play_music("m")
    service.unload_music("m")
    service.unload_music("m")
    assert service.active_music_id is None
    assert not service.owns_music(generation, "m")
    assert raw.unloaded
    assert native.calls.count(("unload_music_stream", raw)) == 1


def test_pause_resume_music_preserves_ownership(svc: tuple[Audio, FakeRaylib]) -> None:
    """Paused streams retain ownership and are not mistaken for completion."""
    service, native = svc
    service.load_music("m.ogg", music_id="m")
    generation = service.play_music("m")
    raw = service._music["m"].raw
    service.pause_music()
    service.pause_music()
    assert not service.is_music_playing()
    assert service.owns_music(generation, "m")
    service._on_start_frame()
    assert native.updated == []
    assert service.music_generation == generation
    service.set_music_volume(0.25)
    assert raw.volume == pytest.approx(0.25)
    service.resume_music()
    service.resume_music()
    assert service.is_music_playing()
    assert service.owns_music(generation, "m")
    assert native.calls.count(("pause_music_stream", raw)) == 1
    assert native.calls.count(("resume_music_stream", raw)) == 1


def test_music_completion_relinquishes_generation(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Natural non-looping completion invalidates tokens and stops pumping."""
    service, native = svc
    service.load_music("m.ogg", music_id="m", default_loop=False)
    generation = service.play_music("m")
    native.finish_music_on_update = True
    service._on_start_frame()
    assert service.active_music_id is None
    assert not service.owns_music(generation)
    assert service.music_generation > generation
    service._on_start_frame()
    assert len(native.updated) == 1


def test_same_music_replay_invalidates_old_generation(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Replaying the same asset is a distinct music ownership generation."""
    service, _ = svc
    service.load_music("m.ogg", music_id="m")
    old = service.play_music("m")
    new = service.play_music("m")
    assert new > old
    assert not service.owns_music(old, "m")
    assert service.owns_music(new, "m")
    assert not service.owns_music(new, "another")


def test_second_music_stops_first(svc: tuple[Audio, FakeRaylib]) -> None:
    """Switching tracks stops the previous stream and changes ownership."""
    service, _ = svc
    service.load_music("m.ogg", music_id="first")
    service.load_music("m.ogg", music_id="second")
    raw = service._music["first"].raw
    first = service.play_music("first")
    second = service.play_music("second")
    assert not raw.playing
    assert not service.owns_music(first, "first")
    assert service.owns_music(second, "second")


def test_set_sfx_volume_updates_all_voice_modes(svc: tuple[Audio, FakeRaylib]) -> None:
    """Bus changes preserve tracked and frozen spatial attenuation."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.play_sound("a")
    service.play_sound_at("a", 425.0, 0.0, track=True)
    service.play_sound_at("a", 425.0, 0.0, track=False)
    service.set_sfx_volume(0.25)
    direct, tracked, frozen = native.aliases
    assert direct.volume == pytest.approx(0.25)
    assert tracked.volume == pytest.approx(0.125)
    assert frozen.volume == pytest.approx(0.125)
    original_pan = frozen.pan
    service.set_listener(425.0, 0.0)
    service.set_sfx_volume(0.5)
    assert tracked.volume == pytest.approx(0.5)
    assert frozen.volume == pytest.approx(0.25)
    assert frozen.pan == original_pan


def test_bus_getters_and_clamping(svc: tuple[Audio, FakeRaylib]) -> None:
    """Finite bus values are clamped and reflected in public properties."""
    service, _ = svc
    service.set_master_volume(-1.0)
    service.set_sfx_volume(2.0)
    service.set_music_volume(0.4)
    assert service.master_volume == 0.0
    assert service.sfx_volume == 1.0
    assert service.music_volume == 0.4


def test_listener_follow_updates_spatial_pan(svc: tuple[Audio, FakeRaylib]) -> None:
    """Moving the listener updates tracked aliases each frame."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    node = make_listener(10.0, 20.0)
    service.set_listener(node)
    assert service.listener == (10.0, 20.0)
    assert service.listener_node is node
    service.play_sound_at("a", 10.0, 20.0, track=True)
    node.transform.world.position = (100.0, 20.0)
    service._on_start_frame()
    assert service.listener == (100.0, 20.0)
    assert native.aliases[-1].pan < 0.0
    service.set_listener(0.0, 0.0)
    assert service.listener_node is None


def test_listener_reads_live_without_voices(svc: tuple[Audio, FakeRaylib]) -> None:
    """Following caches the latest position even without tracked playback."""
    service, _ = svc
    node = make_listener(1.0, 2.0)
    service.set_listener(node)
    node.transform.world.position = (9.0, 8.0)
    service._on_start_frame()
    del node.transform
    assert service.listener == (9.0, 8.0)
    assert service.listener_node is None


def test_clear_listener_follow(svc: tuple[Audio, FakeRaylib]) -> None:
    """Clearing follow preserves the latest world position."""
    service, _ = svc
    node = make_listener(5.0, 6.0)
    service.set_listener(node)
    node.transform.world.position = (7.0, 8.0)
    service.clear_listener_follow()
    node.transform.world.position = (100.0, 100.0)
    assert service.listener_node is None
    assert service.listener == (7.0, 8.0)


@pytest.mark.parametrize("node", [object(), SimpleNamespace(transform=object())])
def test_invalid_listener_does_not_replace_follow(
    svc: tuple[Audio, FakeRaylib], node: object
) -> None:
    """Malformed listeners raise without discarding the current listener."""
    service, _ = svc
    valid = make_listener(5.0, 6.0)
    service.set_listener(valid)
    with pytest.raises(TypeError, match="transform"):
        service.set_listener(node)
    assert service.listener_node is valid
    assert service.listener == (5.0, 6.0)


@pytest.mark.parametrize(
    "values",
    [(-1, 10, 1), (10, 5, 1), (1, 10, 0), (0, float("inf"), 1), (0, 10, float("nan"))],
)
def test_set_spatial_params_validation(
    svc: tuple[Audio, FakeRaylib], values: tuple[float, float, float]
) -> None:
    """Invalid or non-finite spatial parameters never reach native audio."""
    service, _ = svc
    with pytest.raises(ValueError):
        service.set_spatial_params(*values)


def test_spatial_parameter_change_refreshes_tracked(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Changing global attenuation updates live tracked voices immediately."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a", default_volume=0.5)
    service.play_sound_at("a", 50.0, 0.0, track=True)
    service.set_spatial_params(0.0, 100.0, 2.0)
    assert native.aliases[-1].volume == pytest.approx(0.125)


def test_unknown_or_untracked_position_is_noop(svc: tuple[Audio, FakeRaylib]) -> None:
    """Only tracked tokens accept position updates."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    voice = service.play_sound("a")
    before = list(native.calls)
    service.set_voice_position(voice, 10.0, 20.0)
    service.set_voice_position(VoiceId(999), 10.0, 20.0)
    assert native.calls == before


def test_clear_all(svc: tuple[Audio, FakeRaylib]) -> None:
    """Clearing all resources retains the live device and is idempotent."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    service.play_sound("a")
    service.play_music("m")
    service.clear_all()
    before = list(native.calls)
    service.clear_all()
    assert native.calls == before
    assert service.active
    assert service._sounds == {}
    assert service._music == {}
    assert service._voices == {}


@pytest.mark.parametrize(
    "entry, message",
    [({"id": "x"}, "id/path"), ({"id": "x", "path": "a.wav", "kind": "noise"}, "kind")],
)
def test_bank_invalid_entry(
    svc: tuple[Audio, FakeRaylib], audio_dir: Path, entry: dict, message: str
) -> None:
    """Banks report missing fields and unknown kinds explicitly."""
    service, _ = svc
    (audio_dir / "bad.json").write_text(
        json.dumps({"entries": [entry]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=message):
        service.load_bank("bad.json")


def test_set_assets_path(svc: tuple[Audio, FakeRaylib], tmp_path: Path) -> None:
    """Subsequent loads use the new asset directory."""
    service, native = svc
    other = tmp_path / "other"
    other.mkdir()
    (other / "b.wav").write_bytes(b"RIFF")
    service.set_assets_path(other)
    assert service.load_sound("b.wav") == "b"
    assert str((other / "b.wav").resolve()) in native.sounds
