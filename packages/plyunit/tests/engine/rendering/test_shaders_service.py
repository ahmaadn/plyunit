from __future__ import annotations

from types import SimpleNamespace

from plyunit.assets.shaders import ShaderHandle, Shaders, ShaderUniform


class FakeBackend:
    def __init__(self) -> None:
        self.locations: dict[str, int] = {}
        self.values: list[tuple] = []
        self.unloaded: list = []

    def load_shader(self, vs, fs):
        return SimpleNamespace(id=1, vs=vs, fs=fs)

    def load_shader_from_memory(self, vs, fs):
        return SimpleNamespace(id=2, vs=vs, fs=fs)

    def unload_shader(self, raw):
        self.unloaded.append(raw)

    def get_shader_location(self, raw, name):
        return self.locations.get(name, 7)

    def set_shader_value(self, raw, loc, value, uniform_type):
        self.values.append((loc, value, uniform_type))


def test_load_is_valid_set_value_unload():
    backend = FakeBackend()
    # pyrefly: ignore [bad-argument-type]
    svc = Shaders(loader=backend)
    h = svc.load("vs.glsl", "fs.glsl")
    assert svc.is_valid(h)
    assert isinstance(h, ShaderHandle)

    backend.locations["time"] = 3
    svc.set_value(h, "time", 1.5, ShaderUniform.FLOAT)
    assert backend.values == [(3, 1.5, int(ShaderUniform.FLOAT))]
    # location cached
    svc.set_value(h, "time", 2.0, ShaderUniform.FLOAT)
    assert backend.values[-1] == (3, 2.0, int(ShaderUniform.FLOAT))

    svc.unload(h)
    assert not svc.is_valid(h)
    assert not svc.is_valid(None)
    assert backend.unloaded


def test_get_shader_and_invalid():
    backend = FakeBackend()
    # pyrefly: ignore [bad-argument-type]
    svc = Shaders(loader=backend)
    h = svc.load("a", "b")
    assert svc.get_shader(h).id == 1
    svc.unload(h)
    try:
        svc.get_shader(h)
        raised = False
    except ValueError:
        raised = True
    assert raised
