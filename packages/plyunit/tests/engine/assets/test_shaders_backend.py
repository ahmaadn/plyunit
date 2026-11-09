from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock

import pytest

import plyunit.backends.integrations.raylib.shader as shader_mod
from plyunit._enums import ShaderUniform
from plyunit.backends.integrations.raylib.handler import Shader
from plyunit.backends.integrations.raylib.shader import Shaders
from plyunit.backends.ports.handler import ShaderHandle
from plyunit.backends.ports.shaders import IShaders
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    registry = UnitRegistry()
    unit_mod = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_mod, "units", registry)
    disk = SimpleNamespace(id=7, locs=object())
    memory = SimpleNamespace(id=8, locs=object())
    fake_pr = SimpleNamespace(
        load_shader=Mock(return_value=disk),
        load_shader_from_memory=Mock(return_value=memory),
        unload_shader=Mock(),
        is_shader_valid=Mock(side_effect=lambda raw: raw.id > 0),
        rl_get_shader_id_default=Mock(return_value=1),
        get_shader_location=Mock(return_value=3),
        set_shader_value=Mock(),
        ffi=SimpleNamespace(new=Mock(side_effect=lambda kind, values: (kind, values))),
    )
    monkeypatch.setattr(shader_mod, "pr", fake_pr)
    service = Shaders(tags={"custom"})
    yield SimpleNamespace(
        service=service, pr=fake_pr, disk=disk, memory=memory, registry=registry
    )
    fake_pr.unload_shader.side_effect = None
    service.destroy()


def test_shader_service_constructs_without_loading_backend_resources(env) -> None:
    service = env.service
    assert isinstance(service, IShaders)
    assert service.tags == {"service", "shaders", "custom"}
    assert env.registry.one("@Shaders") is service
    env.pr.load_shader.assert_not_called()
    env.pr.load_shader_from_memory.assert_not_called()
    env.pr.rl_get_shader_id_default.assert_not_called()


def test_load_uses_concrete_shader_handle_and_uniform_buffer(env) -> None:
    service = env.service
    handle = service.load("a.vs", "b.fs")
    assert isinstance(handle, Shader)
    assert isinstance(handle, ShaderHandle)
    assert handle.raw_shader is env.disk
    assert service.get_shader(handle) is handle
    assert service.is_valid(handle)
    env.pr.load_shader.assert_called_once_with("a.vs", "b.fs")

    service.set_value(handle, "uTime", 1.5, ShaderUniform.FLOAT)
    env.pr.get_shader_location.assert_called_once_with(env.disk, "uTime")
    env.pr.set_shader_value.assert_called_once_with(
        env.disk, 3, ("float[]", (1.5,)), int(ShaderUniform.FLOAT)
    )

    service.unload(handle)
    assert not service.is_valid(handle)
    assert handle.raw_shader is None
    assert not handle._valid
    assert handle.locations == {}
    env.pr.unload_shader.assert_called_once_with(env.disk)


def test_load_from_memory_wraps_its_own_shader(env) -> None:
    handle = env.service.load_from_memory("vs", "fs")
    assert isinstance(handle, Shader)
    assert handle.raw_shader is env.memory
    assert env.service.is_valid(handle)
    env.pr.load_shader_from_memory.assert_called_once_with("vs", "fs")


@pytest.mark.parametrize("vertex", [None, ""])
def test_omitted_stage_is_passed_as_null_not_empty_filename(env, vertex) -> None:
    env.service.load(vertex, Path("sprite.fs"))
    env.pr.load_shader.assert_called_once_with(None, "sprite.fs")


def test_backend_api_annotations_use_concrete_handles() -> None:
    assert get_type_hints(Shaders.load)["return"] is Shader
    assert get_type_hints(Shaders.load_from_memory)["return"] is Shader
    assert get_type_hints(Shaders.get_shader)["return"] is Shader
    assert get_type_hints(Shaders.set_value)["handle"] is Shader
    assert get_type_hints(Shaders.unload)["handle"] == Shader | None


def test_core_port_returns_generic_handles_not_raw_shader_objects() -> None:
    assert IShaders.get_shader.__annotations__["return"] == "ShaderHandle"
    assert IShaders.load.__annotations__["return"] == "ShaderHandle"
