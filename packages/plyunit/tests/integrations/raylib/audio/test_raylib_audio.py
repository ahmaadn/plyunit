"""Native audio interaction tests for the raylib service, not a backend wrapper."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_raylib import FakeRaylib, make_listener

from plyunit.backends.integrations.raylib.audio import Audio
from plyunit.backends.ports.audio import IAudio
from plyunit.core.schema_config import AudioConfig
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.signal import Signal
from plyunit.services.audio import VoiceId


@pytest.fixture(autouse=True)
def registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    """Isolate services from the process-global unit registry.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The test's global service registry.
    """
    isolated = UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", isolated
    )
    return isolated


@pytest.fixture
def raylib(monkeypatch: pytest.MonkeyPatch) -> FakeRaylib:
    """Mock native calls at the integration boundary.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The native audio test double.
    """
    fake = FakeRaylib()
    module = importlib.import_module("plyunit.backends.integrations.raylib.audio")
    monkeypatch.setattr(module, "pr", fake)
    handler = importlib.import_module("plyunit.backends.integrations.raylib.handler")
    monkeypatch.setattr(handler, "pr", fake)
    return fake


@pytest.fixture
def audio_dir(tmp_path: Path) -> Path:
    """Create file paths accepted by mocked raylib loaders.

    Args:
        tmp_path: Temporary test directory.

    Returns:
        The audio asset root.
    """
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    (tmp_path / "m.ogg").write_bytes(b"OggS")
    return tmp_path


@pytest.fixture
def svc(audio_dir: Path, raylib: FakeRaylib) -> Iterator[tuple[Audio, FakeRaylib]]:
    """Provide an active service and release resources after each test.

    Args:
        audio_dir: Audio asset directory.
        raylib: Native call test double.

    Yields:
        The service and native test double.
    """
    service = Audio(assets_path=audio_dir)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    yield service, raylib
    raylib.failures.clear()
    service.on_detach(app)


def test_from_config(audio_dir: Path) -> None:
    """Configuration builds the canonical integration without backend injection."""
    cfg = AudioConfig(
        enabled=True,
        assets_path=str(audio_dir),
        master_volume=0.5,
        sfx_volume=0.7,
        music_volume=0.3,
        max_voices=4,
        spatial_min_distance=10.0,
        spatial_max_distance=100.0,
        spatial_rolloff=2.0,
    )
    service = Audio.from_config(cfg)
    assert isinstance(service, IAudio)
    assert service.name == "Audio"
    assert service.master_volume == 0.5
    assert service.sfx_volume == 0.7
    assert service.music_volume == 0.3
    assert service._max_voices == 4
    assert service._spatial_min == 10.0
    assert service._spatial_max == 100.0
    assert service._spatial_rolloff == 2.0
    assert not service.active


def test_from_config_validates_before_registration(registry: UnitRegistry) -> None:
    """Bad configuration does not leave a partially initialized service registered."""
    with pytest.raises(ValueError, match="master_volume"):
        Audio.from_config(AudioConfig(master_volume=1.5))
    assert registry._service_order == {}


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_constructor_rejects_invalid_voice_limit(
    registry: UnitRegistry, limit: object
) -> None:
    """Direct construction enforces the voice-capacity contract."""
    with pytest.raises(ValueError, match="max_voices"):
        Audio(max_voices=limit)
    assert registry._service_order == {}


@pytest.mark.parametrize(
    "values", [(-1, 10, 1), (10, 10, 1), (0, 10, 0), (0, float("nan"), 1)]
)
def test_constructor_rejects_invalid_spatial_parameters(
    registry: UnitRegistry, values: tuple[float, float, float]
) -> None:
    """Constructor spatial validation matches runtime parameter validation."""
    with pytest.raises(ValueError, match="spatial"):
        Audio(
            spatial_min_distance=values[0],
            spatial_max_distance=values[1],
            spatial_rolloff=values[2],
        )
    assert registry._service_order == {}


def test_registry_auto_attach_and_teardown(
    registry: UnitRegistry, raylib: FakeRaylib, audio_dir: Path
) -> None:
    """ServiceUnit attaches after construction and unregister tears audio down."""
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    registry.activate_app(app)
    service = Audio(assets_path=audio_dir, master_volume=0.4)
    assert service.active
    assert service._attached_app is app
    assert raylib.master == 0.4
    assert len(app.on_start_frame) == 1
    service.load_sound("a.wav", sound_id="a")
    service.play_sound("a")
    registry.unregister(service)
    assert not service.active
    assert service._attached_app is None
    assert len(app.on_start_frame) == 0
    assert raylib.close_calls == 1


def test_device_init_not_ready_is_inactive(raylib: FakeRaylib) -> None:
    """Failed native initialization must not set master gain or connect a signal."""
    raylib.init_succeeds = False
    service = Audio()
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    assert not service.active
    assert len(app.on_start_frame) == 0
    assert not any(call[0] == "set_master_volume" for call in raylib.calls)
    service.on_detach(app)
    assert raylib.close_calls == 0


def test_device_init_exception_is_inactive(raylib: FakeRaylib) -> None:
    """An init exception leaves no frame subscription and allows safe teardown."""
    raylib.failures["init_audio_device"] = RuntimeError("no device")
    service = Audio()
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    assert not service.active
    assert len(app.on_start_frame) == 0
    service.on_detach(app)
    assert raylib.close_calls == 0


def test_failed_attach_can_retry(raylib: FakeRaylib) -> None:
    """An inactive attach may retry initialization for the same app."""
    raylib.init_succeeds = False
    service = Audio()
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    raylib.init_succeeds = True
    service.on_attach(app)
    assert service.active
    assert len(app.on_start_frame) == 1
    service.on_detach(app)
    assert raylib.init_calls == 2
    assert raylib.close_calls == 1


def test_attach_setup_failure_closes_owned_device(raylib: FakeRaylib) -> None:
    """Failure after opening a device rolls back native ownership and signals."""
    raylib.failures["set_master_volume"] = RuntimeError("native setup failed")
    service = Audio()
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    assert not service.active
    assert not raylib.ready
    assert raylib.close_calls == 1
    assert len(app.on_start_frame) == 0
    service.on_detach(app)
    assert raylib.close_calls == 1


def test_borrowed_device_is_not_reinitialized_or_closed(
    raylib: FakeRaylib, audio_dir: Path
) -> None:
    """A pre-existing device is borrowed, while service-owned assets still unload."""
    raylib.ready = True
    service = Audio(assets_path=audio_dir)
    app = SimpleNamespace(on_start_frame=Signal("on_start_frame"))
    service.on_attach(app)
    service.load_sound("a.wav", sound_id="a")
    raw = service._sounds["a"].raw
    service.on_detach(app)
    assert raw.unloaded
    assert raylib.init_calls == 0
    assert raylib.close_calls == 0
    assert raylib.ready


def test_different_app_cannot_attach_or_detach_live_audio(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Foreign lifecycle hooks cannot steal or destroy the host's device."""
    service, native = svc
    other = SimpleNamespace(on_start_frame=Signal("other"))
    with pytest.raises(RuntimeError, match="another app"):
        service.on_attach(other)
    service.on_detach(other)
    assert service.active
    assert native.close_calls == 0


def test_teardown_resource_order(svc: tuple[Audio, FakeRaylib]) -> None:
    """Teardown frees aliases before samples and all assets before the device."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    sound = service._sounds["a"].raw
    music = service._music["m"].raw
    voice = service.play_sound("a")
    service.play_music("m")
    alias = native.aliases[-1]
    listener = make_listener(3.0, 4.0)
    service.set_listener(listener)
    service.on_detach(service._app)
    assert alias.unloaded and sound.unloaded and music.unloaded
    assert service.listener_node is None
    assert service.listener == (3.0, 4.0)
    assert not service.is_voice_playing(voice)
    alias_index = native.calls.index(("unload_sound_alias", alias))
    sound_index = native.calls.index(("unload_sound", sound))
    music_index = native.calls.index(("unload_music_stream", music))
    close_index = native.calls.index(("close_audio_device",))
    assert alias_index < sound_index < close_index
    assert music_index < close_index


def test_device_loss_never_calls_stale_native_resources(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """A closed native device overrides the cached active flag for every control."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    voice = service.play_sound_at("a", 1.0, 2.0, track=True)
    generation = service.play_music("m")
    native.ready = False
    before = list(native.calls)
    assert not service.active
    assert not service.is_voice_playing(voice)
    assert not service.is_music_playing()
    assert not service.owns_music(generation)
    with pytest.raises(RuntimeError, match="not active"):
        service.play_sound("a")
    service.set_master_volume(0.5)
    service.set_sfx_volume(0.5)
    service.set_music_volume(0.5)
    service.set_voice_position(voice, 10.0, 20.0)
    service.pause_music()
    service.resume_music()
    service._on_start_frame()
    service.clear_all()
    service.on_detach(service._app)
    assert service._voices == {}
    assert service._sounds == {}
    assert service._music == {}
    assert native.calls == before


def test_detected_device_loss_requires_reattach_and_reload(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """A reopened global device cannot silently revive stale audio handles."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    old_voice = service.play_sound("a")
    native.ready = False
    assert not service.active
    assert service._voices == {}
    assert service._sounds == {}
    native.ready = True
    assert not service.active
    service.on_attach(service._app)
    assert service.active
    with pytest.raises(KeyError):
        service.play_sound("a")
    service.load_sound("a.wav", sound_id="a")
    assert service.play_sound("a") != old_voice


@pytest.mark.parametrize(
    "failure", ["set_sound_volume", "set_sound_pitch", "set_sound_pan", "play_sound"]
)
def test_startup_failure_releases_alias(
    svc: tuple[Audio, FakeRaylib], failure: str
) -> None:
    """Failure after alias allocation stops and unloads the unregistered alias."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    raw = service._sounds["a"].raw
    native.failures[failure] = RuntimeError("native failure")
    with pytest.raises(RuntimeError, match="native failure"):
        service.play_sound("a")
    alias = native.aliases[-1]
    assert alias.unloaded
    assert not raw.unloaded
    assert service._voices == {}
    assert native.calls.count(("stop_sound", alias)) == 1
    assert native.calls.count(("unload_sound_alias", alias)) == 1


def test_invalid_alias_is_never_played(svc: tuple[Audio, FakeRaylib]) -> None:
    """An invalid native alias is reclaimed without configuring or playing it."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    native.invalid_alias = True
    with pytest.raises(RuntimeError, match="alias"):
        service.play_sound("a")
    alias = native.aliases[-1]
    assert alias.unloaded
    assert not any(call[0] == "play_sound" for call in native.calls)
    assert service._voices == {}


def test_stop_failure_still_unloads_alias(svc: tuple[Audio, FakeRaylib]) -> None:
    """Stopping errors must not skip releasing the alias buffer."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    voice = service.play_sound("a")
    alias = native.aliases[-1]
    native.failures["stop_sound"] = RuntimeError("stop failed")
    service.stop_voice(voice)
    service.stop_voice(voice)
    assert alias.unloaded
    assert native.calls.count(("unload_sound_alias", alias)) == 1


def test_music_start_failure_does_not_claim_generation(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """A failed music start stops partial playback and claims no ownership."""
    service, native = svc
    service.load_music("m.ogg", music_id="m")
    old = service.play_music("m")
    native.failures["play_music_stream"] = RuntimeError("play failed")
    with pytest.raises(RuntimeError, match="play failed"):
        service.play_music("m")
    assert service.active_music_id is None
    assert not service.owns_music(old)
    assert not service._music["m"].raw.playing


def test_music_stop_failure_invalidates_generation(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """A native stop error cannot leave a stale music token owning playback."""
    service, native = svc
    service.load_music("m.ogg", music_id="m")
    old = service.play_music("m")
    native.failures["stop_music_stream"] = RuntimeError("stop failed")
    service.stop_music()
    assert service.active_music_id is None
    assert not service.owns_music(old)
    service.unload_music("m")
    assert service._music == {}


def test_failed_music_reload_preserves_previous(svc: tuple[Audio, FakeRaylib]) -> None:
    """An invalid decoder replacement preserves the previous stream and token."""
    service, native = svc
    service.load_music("m.ogg", music_id="m")
    raw = service._music["m"].raw
    generation = service.play_music("m")
    native.invalid_music = True
    with pytest.raises(RuntimeError, match="load music"):
        service.load_music("m.ogg", music_id="m")
    assert service._music["m"].raw is raw
    assert not raw.unloaded
    assert service.owns_music(generation, "m")


@pytest.mark.parametrize(
    "major, pan, expected",
    [
        (5, 0.0, 1.0),
        (5, 0.5, 0.5),
        (5, 1.0, 0.0),
        (6, 0.0, -1.0),
        (6, 0.5, 0.0),
        (6, 1.0, 1.0),
    ],
)
def test_public_pan_converts_to_native_convention(
    svc: tuple[Audio, FakeRaylib], major: int, pan: float, expected: float
) -> None:
    """Both supported raylib versions preserve public left/center/right pan."""
    service, native = svc
    native.RAYLIB_VERSION_MAJOR = major
    service.load_sound("a.wav", sound_id="a")
    service.play_sound("a", pan=pan)
    assert native.aliases[-1].pan == expected


@pytest.mark.parametrize("pan, expected", [(-2.0, -1.0), (2.0, 1.0)])
def test_public_pan_is_clamped(
    svc: tuple[Audio, FakeRaylib], pan: float, expected: float
) -> None:
    """Finite out-of-range pan clamps before native conversion."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.play_sound("a", pan=pan)
    assert native.aliases[-1].pan == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pitch": 0.0},
        {"pitch": -1.0},
        {"pitch": float("inf")},
        {"pan": float("nan")},
        {"volume": float("inf")},
    ],
)
def test_invalid_playback_values_do_not_allocate_alias(
    svc: tuple[Audio, FakeRaylib], kwargs: dict[str, float]
) -> None:
    """Non-finite or invalid playback inputs fail before native allocation."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    with pytest.raises(ValueError):
        service.play_sound("a", **kwargs)
    assert native.aliases == []


@pytest.mark.parametrize(
    "method", ["set_master_volume", "set_sfx_volume", "set_music_volume"]
)
def test_nonfinite_bus_volume_is_rejected(
    svc: tuple[Audio, FakeRaylib], method: str
) -> None:
    """NaN and infinity cannot reach native bus controls."""
    service, native = svc
    before = list(native.calls)
    with pytest.raises(ValueError, match="finite"):
        getattr(service, method)(float("nan"))
    assert native.calls == before


def test_tokens_do_not_repeat_after_clear_and_reattach(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Reusing the service cannot make old voice/music tokens valid again."""
    service, _ = svc
    app = service._app
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    old_voice = service.play_sound("a")
    old_music = service.play_music("m")
    service.on_detach(app)
    service.on_attach(app)
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    new_voice = service.play_sound("a")
    new_music = service.play_music("m")
    service.stop_voice(VoiceId(old_voice))
    assert new_voice != old_voice
    assert new_music != old_music
    assert service.is_voice_playing(new_voice)
    assert service.owns_music(new_music, "m")
    assert not service.owns_music(old_music, "m")


def test_audio_resources_are_backend_handler_types(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Concrete resource owners stay in the backend, not portable service types."""
    service, _ = svc
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    voice = service.play_sound("a")
    for resource in (service._sounds["a"], service._music["m"], service._voices[voice]):
        assert (
            type(resource).__module__ == "plyunit.backends.integrations.raylib.handler"
        )


def test_device_recovery_does_not_revive_stale_handles(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Device loss invalidates resources before retrying initialization."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    service.load_music("m.ogg", music_id="m")
    old_voice = service.play_sound("a")
    old_music = service.play_music("m")
    native.ready = False
    before = list(native.calls)
    assert not service.active
    assert native.calls == before
    assert service._sounds == {}
    assert service._music == {}
    assert service._voices == {}
    service.on_attach(service._app)
    assert service.active
    with pytest.raises(KeyError):
        service.play_sound("a")
    service.load_sound("a.wav", sound_id="a")
    assert service.play_sound("a") != old_voice
    assert not service.owns_music(old_music)


@pytest.mark.parametrize("kind", ["sound", "music"])
def test_native_validation_error_reclaims_new_resource(
    svc: tuple[Audio, FakeRaylib], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A validation exception releases the allocation and preserves the old entry."""
    service, native = svc
    path = "a.wav" if kind == "sound" else "m.ogg"
    load = service.load_sound if kind == "sound" else service.load_music
    id_arg = {"sound_id": "asset"} if kind == "sound" else {"music_id": "asset"}
    entries = service._sounds if kind == "sound" else service._music
    load(path, **id_arg)
    old = entries["asset"].raw

    def fail_validation(_raw: object) -> bool:
        raise RuntimeError("validation failed")

    monkeypatch.setattr(native, f"is_{kind}_valid", fail_validation)
    with pytest.raises(RuntimeError, match="validation failed"):
        load(path, **id_arg)
    assert entries["asset"].raw is old
    allocated = list((native.sounds if kind == "sound" else native.music).values())[-1]
    assert allocated is not old
    assert allocated.unloaded
    assert not old.unloaded


def test_failed_alias_unload_preserves_shared_samples(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Source samples remain owned until a failing alias release can be retried."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    source = service._sounds["a"].raw
    voice = service.play_sound("a")
    alias = native.aliases[-1]
    native.failures["unload_sound_alias"] = RuntimeError("alias release failed")
    service.unload_sound("a")
    assert not alias.unloaded
    assert not source.unloaded
    assert voice in service._voices
    assert "a" in service._sounds
    assert ("unload_sound", source) not in native.calls
    native.failures.clear()
    service.unload_sound("a")
    assert alias.unloaded and source.unloaded
    assert service._voices == {}
    assert service._sounds == {}


def test_unreleasable_voice_slot_fails_without_allocating(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Native release errors cannot cause an endless voice-stealing loop."""
    service, native = svc
    service._max_voices = 1
    service.load_sound("a.wav", sound_id="a")
    service.play_sound("a")
    native.failures["unload_sound_alias"] = RuntimeError("alias release failed")
    with pytest.raises(RuntimeError, match="voice slot"):
        service.play_sound("a")
    assert len(native.aliases) == 1
    native.failures.clear()


def test_start_failure_with_release_failure_keeps_samples_owned(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """An unreleasable startup alias remains tracked for safe cleanup retries."""
    service, native = svc
    service.load_sound("a.wav", sound_id="a")
    source = service._sounds["a"].raw
    native.failures["play_sound"] = RuntimeError("play failed")
    native.failures["unload_sound_alias"] = RuntimeError("release failed")
    with pytest.raises(RuntimeError, match="play failed"):
        service.play_sound("a")
    alias = native.aliases[-1]
    service.unload_sound("a")
    assert not source.unloaded
    assert not alias.unloaded
    assert len(service._voices) == 1
    native.failures.clear()
    service.clear_all()
    assert alias.unloaded and source.unloaded


def test_invalid_tracked_position_update_is_atomic(
    svc: tuple[Audio, FakeRaylib],
) -> None:
    """Invalid Y coordinates do not partially mutate the tracked X coordinate."""
    service, _ = svc
    service.load_sound("a.wav", sound_id="a")
    voice = service.play_sound_at("a", 10.0, 20.0, track=True)
    with pytest.raises(ValueError, match="finite"):
        service.set_voice_position(voice, 100.0, float("nan"))
    assert (service._voices[voice].x, service._voices[voice].y) == (10.0, 20.0)
