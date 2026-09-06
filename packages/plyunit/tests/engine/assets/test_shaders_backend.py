from __future__ import annotations

from types import SimpleNamespace

from plyunit.assets.shaders import (
    ShaderHandle,
    Shaders,
    ShaderUniform,
)


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def load_shader(self, vs, fs):
        self.calls.append(("load", vs, fs))
        return SimpleNamespace(id=7)

    def load_shader_from_memory(self, vs, fs):
        self.calls.append(("mem", vs, fs))
        return SimpleNamespace(id=8)

    def unload_shader(self, raw):
        self.calls.append(("unload", raw.id))

    def get_shader_location(self, raw, name):
        self.calls.append(("loc", name))
        return 3

    def set_shader_value(self, raw, loc, value, uniform_type):
        self.calls.append(("set", loc, value, uniform_type))


def test_shaders_service_uses_injected_backend() -> None:
    backend = FakeBackend()
    # pyrefly: ignore [bad-argument-type]
    svc = Shaders(loader=backend)
    h = svc.load("a.vs", "b.fs")
    assert isinstance(h, ShaderHandle)
    assert svc.is_valid(h)
    svc.set_value(h, "uTime", 1.5, ShaderUniform.FLOAT)
    assert ("loc", "uTime") in backend.calls
    assert ("set", 3, 1.5, int(ShaderUniform.FLOAT)) in backend.calls
    svc.unload(h)
    assert not svc.is_valid(h)
    assert ("unload", 7) in backend.calls


def test_shaders_load_from_memory() -> None:
    backend = FakeBackend()
    # pyrefly: ignore [bad-argument-type]
    svc = Shaders(loader=backend)
    h = svc.load_from_memory("vs", "fs")
    assert h.raw.id == 8
    assert ("mem", "vs", "fs") in backend.calls


def test_default_loader_falls_back_to_shader_loader(monkeypatch) -> None:
    backend = FakeBackend()
    monkeypatch.setattr("plyunit.backends.integrations.ShaderLoader", lambda: backend)
    svc = Shaders()
    svc.load("x", "y")
    assert backend.calls[0][0] == "load"
