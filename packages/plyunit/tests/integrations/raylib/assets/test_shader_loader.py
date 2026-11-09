from __future__ import annotations

import importlib
from array import array
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import plyunit.backends.integrations.raylib.shader as shader_mod
from plyunit._enums import ShaderUniform
from plyunit.backends.integrations.raylib.handler import Shader
from plyunit.backends.integrations.raylib.shader import Shaders
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.services.shaders.uniform import uniform_components


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
        is_shader_valid=Mock(
            side_effect=lambda raw: raw.id > 0 and raw.locs is not None
        ),
        rl_get_shader_id_default=Mock(return_value=1),
        get_shader_location=Mock(return_value=3),
        set_shader_value=Mock(),
        ffi=SimpleNamespace(
            new=Mock(side_effect=lambda kind, values: (kind, tuple(values)))
        ),
    )
    monkeypatch.setattr(shader_mod, "pr", fake_pr)
    service = Shaders()
    yield SimpleNamespace(service=service, pr=fake_pr, disk=disk, memory=memory)
    fake_pr.unload_shader.side_effect = None
    service.destroy()


def test_shader_service_delegates_loading_and_uniforms_to_raylib(env) -> None:
    disk = env.service.load("sprite.vs", "sprite.fs")
    memory = env.service.load_from_memory("vs-code", "fs-code")
    assert disk.raw_shader is env.disk
    assert memory.raw_shader is env.memory
    env.pr.load_shader.assert_called_once_with("sprite.vs", "sprite.fs")
    env.pr.load_shader_from_memory.assert_called_once_with("vs-code", "fs-code")
    env.service.set_value(disk, "u_time", 1.5, ShaderUniform.FLOAT)
    env.pr.get_shader_location.assert_called_once_with(env.disk, "u_time")
    env.pr.set_shader_value.assert_called_once_with(env.disk, 3, ("float[]", (1.5,)), 0)
    env.service.unload(disk)
    env.pr.unload_shader.assert_called_once_with(env.disk)


@pytest.mark.parametrize("loader", ["load", "load_from_memory"])
def test_default_shader_is_borrowed_and_its_struct_is_never_modified(
    env, loader
) -> None:
    default = SimpleNamespace(id=1, locs=object())
    getattr(
        env.pr, "load_shader" if loader == "load" else "load_shader_from_memory"
    ).return_value = default
    handle = getattr(env.service, loader)()
    assert env.service.is_valid(handle)
    handle.locations["time"] = 3
    locs = default.locs
    env.service.unload(handle)
    assert handle.raw_shader is None
    assert not handle._valid
    assert handle.locations == {}
    assert default.id == 1
    assert default.locs is locs
    env.pr.unload_shader.assert_not_called()


@pytest.mark.parametrize("loader", ["load", "load_from_memory"])
def test_compile_failure_returning_default_does_not_own_or_unload_it(
    env, loader
) -> None:
    default = SimpleNamespace(id=1, locs=object())
    getattr(
        env.pr, "load_shader" if loader == "load" else "load_shader_from_memory"
    ).return_value = default
    with pytest.raises(RuntimeError, match="raylib returned its default shader"):
        getattr(env.service, loader)("bad-vs", "bad-fs")
    assert env.service._handles == {}
    env.pr.unload_shader.assert_not_called()
    assert default.id == 1
    assert default.locs is not None


@pytest.mark.parametrize("raw", [None, SimpleNamespace(id=0, locs=None)])
def test_invalid_load_results_are_rejected_and_partial_resources_released(
    env, raw
) -> None:
    env.pr.load_shader.return_value = raw
    with pytest.raises(RuntimeError, match="failed to load shader"):
        env.service.load("v", "f")
    assert env.service._handles == {}
    if raw is None:
        env.pr.unload_shader.assert_not_called()
    else:
        env.pr.unload_shader.assert_called_once_with(raw)


def test_zero_id_shader_is_released_when_no_default_program_exists(env) -> None:
    partial = SimpleNamespace(id=0, locs=object())
    env.pr.load_shader.return_value = partial
    env.pr.rl_get_shader_id_default.return_value = 0
    with pytest.raises(RuntimeError, match="failed to load shader"):
        env.service.load("v", "f")
    env.pr.unload_shader.assert_called_once_with(partial)
    assert env.service._handles == {}


def test_handle_creation_failure_releases_owned_shader(env, monkeypatch) -> None:
    monkeypatch.setattr(
        Shader, "from_raw", Mock(side_effect=RuntimeError("wrap failed"))
    )
    with pytest.raises(RuntimeError, match="wrap failed"):
        env.service.load("v", "f")
    env.pr.unload_shader.assert_called_once_with(env.disk)
    assert env.service._handles == {}


@pytest.mark.parametrize(
    "kind, value, storage, expected",
    [
        (ShaderUniform.FLOAT, 1.5, "float[]", (1.5,)),
        (ShaderUniform.VEC2, [1, 2], "float[]", (1.0, 2.0)),
        (ShaderUniform.VEC3, (1, 2, 3), "float[]", (1.0, 2.0, 3.0)),
        (ShaderUniform.VEC4, (1, 0.5, 0.25, 1), "float[]", (1.0, 0.5, 0.25, 1.0)),
        (ShaderUniform.INT, 7, "int[]", (7,)),
        (ShaderUniform.IVEC2, [1, 2], "int[]", (1, 2)),
        (ShaderUniform.IVEC3, (1, 2, 3), "int[]", (1, 2, 3)),
        (ShaderUniform.IVEC4, (1, 2, 3, 4), "int[]", (1, 2, 3, 4)),
        (ShaderUniform.SAMPLER2D, 4, "int[]", (4,)),
    ],
)
def test_uniform_values_are_converted_to_correctly_sized_buffers(
    env, kind, value, storage, expected
) -> None:
    handle = env.service.load("v", "f")
    env.service.set_value(handle, "value", value, int(kind))
    env.pr.ffi.new.assert_called_once_with(storage, expected)
    env.pr.set_shader_value.assert_called_once_with(
        env.disk, 3, (storage, expected), int(kind)
    )


def test_general_numeric_sequence_is_supported(env) -> None:
    handle = env.service.load("v", "f")
    env.service.set_value(handle, "value", array("f", [1, 2, 3]), ShaderUniform.VEC3)
    env.pr.set_shader_value.assert_called_once_with(
        env.disk, 3, ("float[]", (1.0, 2.0, 3.0)), 2
    )


@pytest.mark.parametrize("value", [1, (), [1], [1, 2], [1, 2, 3, 4]])
def test_wrong_component_count_is_rejected_before_backend_update(env, value) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(ValueError, match="exactly 3 component"):
        env.service.set_value(handle, "value", value, ShaderUniform.VEC3)
    env.pr.ffi.new.assert_not_called()
    env.pr.set_shader_value.assert_not_called()


@pytest.mark.parametrize("value", [object(), "1", b"1", [object()]])
def test_raw_pointers_and_nonnumeric_values_are_not_part_of_the_service_port(
    env, value
) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(TypeError, match="numeric"):
        env.service.set_value(handle, "value", value, ShaderUniform.FLOAT)
    env.pr.ffi.new.assert_not_called()
    env.pr.set_shader_value.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1e100])
def test_nonfinite_or_overflowing_float_uniforms_are_rejected(env, value) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(ValueError, match="finite 32-bit"):
        env.service.set_value(handle, "value", value, ShaderUniform.FLOAT)
    env.pr.set_shader_value.assert_not_called()


@pytest.mark.parametrize(
    "value", [1.5, float("inf"), float("nan"), 2**31, -(2**31) - 1]
)
def test_fractional_or_out_of_range_integer_uniforms_are_rejected(env, value) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(ValueError):
        env.service.set_value(handle, "value", value, ShaderUniform.INT)
    env.pr.set_shader_value.assert_not_called()


def test_signed_int_boundaries_and_integral_floats_are_supported() -> None:
    assert uniform_components(-(2**31), ShaderUniform.INT) == (-(2**31),)
    assert uniform_components(2**31 - 1, ShaderUniform.INT) == (2**31 - 1,)
    assert uniform_components(2.0, ShaderUniform.INT) == (2,)


def test_huge_integer_cannot_overflow_float_uniform_storage(env) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(ValueError, match="finite 32-bit"):
        env.service.set_value(handle, "value", 10**1000, ShaderUniform.FLOAT)
    env.pr.set_shader_value.assert_not_called()


def test_invalid_uniform_enum_raises_without_backend_update(env) -> None:
    handle = env.service.load("v", "f")
    with pytest.raises(ValueError):
        env.service.set_value(handle, "value", 1.0, 100)
    env.pr.ffi.new.assert_not_called()
    env.pr.set_shader_value.assert_not_called()
