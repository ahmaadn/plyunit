from __future__ import annotations

import gc
import importlib
from itertools import count
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import plyunit.backends.integrations.raylib.shader as shader_mod
from plyunit._enums import ShaderUniform
from plyunit.backends.integrations.raylib.handler import Shader
from plyunit.backends.integrations.raylib.shader import Shaders
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    registry = UnitRegistry()
    unit_mod = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_mod, "units", registry)
    ids = count(2)
    locations = {"time": 3, "zero": 0, "missing": -1}
    fake_pr = SimpleNamespace(
        load_shader=Mock(
            side_effect=lambda *_: SimpleNamespace(id=next(ids), locs=object())
        ),
        load_shader_from_memory=Mock(
            side_effect=lambda *_: SimpleNamespace(id=next(ids), locs=object())
        ),
        unload_shader=Mock(),
        is_shader_valid=Mock(
            side_effect=lambda raw: raw.id > 0 and raw.locs is not None
        ),
        rl_get_shader_id_default=Mock(return_value=1),
        get_shader_location=Mock(side_effect=lambda raw, name: locations.get(name, 7)),
        set_shader_value=Mock(),
        ffi=SimpleNamespace(new=Mock(side_effect=lambda kind, values: (kind, values))),
    )
    monkeypatch.setattr(shader_mod, "pr", fake_pr)
    service = Shaders()
    yield SimpleNamespace(service=service, pr=fake_pr, registry=registry)
    fake_pr.unload_shader.side_effect = None
    for item in registry.group(Shaders):
        item.destroy()


@pytest.mark.parametrize("name, location", [("time", 3), ("zero", 0)])
def test_uniform_location_is_cached_including_zero(env, name, location) -> None:
    handle = env.service.load("v", "f")
    raw = handle.raw_shader
    env.service.set_value(handle, name, 1.5, ShaderUniform.FLOAT)
    env.service.set_value(handle, name, 2.0, ShaderUniform.FLOAT)
    assert handle.locations == {name: location}
    env.pr.get_shader_location.assert_called_once_with(raw, name)
    assert env.pr.set_shader_value.call_args_list == [
        call(raw, location, ("float[]", (1.5,)), 0),
        call(raw, location, ("float[]", (2.0,)), 0),
    ]


def test_missing_location_is_cached_and_never_updated(env) -> None:
    handle = env.service.load("v", "f")
    env.service.set_value(handle, "missing", 1.5, ShaderUniform.FLOAT)
    env.service.set_value(handle, "missing", 2.0, ShaderUniform.FLOAT)
    assert handle.locations == {"missing": -1}
    env.pr.get_shader_location.assert_called_once()
    env.pr.ffi.new.assert_not_called()
    env.pr.set_shader_value.assert_not_called()


def test_location_caches_are_per_handle(env) -> None:
    first = env.service.load("v", "f")
    second = env.service.load_from_memory("v", "f")
    env.service.set_value(first, "time", 1, ShaderUniform.FLOAT)
    env.service.set_value(second, "time", 2, ShaderUniform.FLOAT)
    assert first.locations is not second.locations
    assert env.pr.get_shader_location.call_count == 2


def test_unload_is_idempotent_and_does_not_modify_raw_struct(env) -> None:
    handle = env.service.load("v", "f")
    raw = handle.raw_shader
    raw_id, raw_locs = raw.id, raw.locs
    env.service.set_value(handle, "time", 1, ShaderUniform.FLOAT)
    env.pr.get_shader_location.reset_mock()
    env.pr.set_shader_value.reset_mock()

    env.service.unload(handle)
    env.service.unload(handle)
    env.service.unload(None)
    assert handle.raw_shader is None
    assert handle.locations == {}
    assert not handle._valid
    assert raw.id == raw_id
    assert raw.locs is raw_locs
    assert not env.service.is_valid(handle)
    assert not env.service.is_valid(None)
    env.pr.unload_shader.assert_called_once_with(raw)
    env.service.set_value(handle, "time", 3, ShaderUniform.FLOAT)
    env.pr.get_shader_location.assert_not_called()
    env.pr.set_shader_value.assert_not_called()
    with pytest.raises(ValueError, match="invalid shader handle"):
        env.service.get_shader(handle)


def test_validity_checks_handle_state_and_backend_result(env) -> None:
    handle = env.service.load("v", "f")
    handle._valid = False
    assert not env.service.is_valid(handle)
    handle._valid = True
    env.pr.is_shader_valid.return_value = False
    env.pr.is_shader_valid.side_effect = None
    assert not env.service.is_valid(handle)
    with pytest.raises(ValueError, match="invalid shader handle"):
        env.service.get_shader(handle)


def test_foreign_handles_are_not_valid_updated_or_unloaded(env) -> None:
    owner = Shaders()
    foreign = owner.load("v", "f")
    unregistered = Shader.from_raw(SimpleNamespace(id=40, locs=object()))
    for handle in (foreign, unregistered):
        assert not env.service.is_valid(handle)
        env.service.unload(handle)
        env.service.set_value(handle, "time", 1, ShaderUniform.FLOAT)
        with pytest.raises(ValueError, match="invalid shader handle"):
            env.service.get_shader(handle)
    env.pr.unload_shader.assert_not_called()
    env.pr.get_shader_location.assert_not_called()
    assert owner.is_valid(foreign)


def test_service_strongly_retains_handles_until_teardown(env) -> None:
    handle = env.service.load("v", "f")
    identity, raw = id(handle), handle.raw_shader
    del handle
    gc.collect()
    assert env.service._handles[identity].raw_shader is raw
    env.service.unload_all()
    assert env.service._handles == {}
    env.pr.unload_shader.assert_called_once_with(raw)


def test_destroy_without_an_app_unloads_every_shader_and_unregisters(env) -> None:
    handles = [env.service.load("v", "f"), env.service.load_from_memory("v", "f")]
    env.service.destroy()
    assert all(handle.raw_shader is None and not handle._valid for handle in handles)
    assert env.pr.unload_shader.call_count == 2
    assert not env.registry.contains(env.service)
    env.service.destroy()
    assert env.pr.unload_shader.call_count == 2


def test_registry_detach_releases_resources_before_forgetting_service(env) -> None:
    app = ServiceUnit(name="TestApp")
    env.registry.activate_app(app)
    handle = env.service.load("v", "f")
    env.registry.unregister(env.service)
    assert handle.raw_shader is None
    assert not handle._valid
    env.pr.unload_shader.assert_called_once()


def test_unload_error_preserves_handle_and_cache_for_retry(env) -> None:
    handle = env.service.load("v", "f")
    raw = handle.raw_shader
    handle.locations["time"] = 3
    env.pr.unload_shader.side_effect = RuntimeError("GPU release failed")
    with pytest.raises(RuntimeError, match="GPU release failed"):
        env.service.unload(handle)
    assert env.service.is_valid(handle)
    assert handle.raw_shader is raw
    assert handle.locations == {"time": 3}
    env.pr.unload_shader.side_effect = None
    env.service.unload(handle)
    assert handle.raw_shader is None
    assert handle.locations == {}


def test_unload_all_attempts_later_handles_after_an_error(env) -> None:
    first = env.service.load("v", "f")
    second = env.service.load("v", "f")
    first_raw = first.raw_shader

    def unload(raw):
        if raw is first_raw:
            raise RuntimeError("first shader failed")

    env.pr.unload_shader.side_effect = unload
    with pytest.raises(ExceptionGroup, match="failed to unload shaders") as caught:
        env.service.unload_all()
    assert len(caught.value.exceptions) == 1
    assert env.service.is_valid(first)
    assert second.raw_shader is None
    assert env.pr.unload_shader.call_count == 2
    env.pr.unload_shader.side_effect = None
    env.service.unload_all()
    assert first.raw_shader is None
