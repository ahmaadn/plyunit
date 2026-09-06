from __future__ import annotations

from types import SimpleNamespace

import plyunit.backends.integrations.raylib.assets.shader as shader


def test_shader_loader_delegates_to_raylib(monkeypatch) -> None:
    calls: list[tuple] = []
    disk_shader = SimpleNamespace(id=1)
    memory_shader = SimpleNamespace(id=2)
    fake_pr = SimpleNamespace(
        load_shader=lambda vs, fs: calls.append(("load", vs, fs)) or disk_shader,
        load_shader_from_memory=lambda vs, fs: calls.append(("memory", vs, fs))
        or memory_shader,
        unload_shader=lambda raw: calls.append(("unload", raw)),
        get_shader_location=lambda raw, name: calls.append(("location", raw, name))
        or 7,
        set_shader_value=lambda raw, loc, value, kind: calls.append(
            ("value", raw, loc, value, kind)
        ),
    )
    monkeypatch.setattr(shader, "pr", fake_pr)

    assert shader.load_shader("sprite.vs", "sprite.fs") is disk_shader
    assert shader.load_shader_from_memory("vs-code", "fs-code") is memory_shader
    assert shader.get_shader_location(disk_shader, "u_time") == 7
    shader.set_shader_value(disk_shader, 7, 1.5, 0)
    shader.unload_shader(disk_shader)
    shader.unload_shader(None)

    assert calls == [
        ("load", "sprite.vs", "sprite.fs"),
        ("memory", "vs-code", "fs-code"),
        ("location", disk_shader, "u_time"),
        ("value", disk_shader, 7, 1.5, 0),
        ("unload", disk_shader),
    ]


def _fake_cffi_pr(recorded: dict) -> SimpleNamespace:
    """Build a fake ``pr`` whose ``ffi.new`` records buffers."""

    def fake_new(ctype: str, values: list) -> tuple:
        return ("buffer", ctype, tuple(values))

    def fake_set(raw, loc, value, kind) -> None:
        recorded["call"] = (raw, loc, value, kind)

    return SimpleNamespace(ffi=SimpleNamespace(new=fake_new), set_shader_value=fake_set)


def test_set_shader_value_wraps_scalar_float(monkeypatch) -> None:
    recorded: dict = {}
    monkeypatch.setattr(shader, "pr", _fake_cffi_pr(recorded))

    shader.set_shader_value("raw", 3, 1.5, 0)

    assert recorded["call"] == ("raw", 3, ("buffer", "float[]", (1.5,)), 0)


def test_set_shader_value_wraps_vec4_sequence(monkeypatch) -> None:
    recorded: dict = {}
    monkeypatch.setattr(shader, "pr", _fake_cffi_pr(recorded))

    shader.set_shader_value("raw", 4, (1.0, 0.5, 0.25, 1.0), 3)

    assert recorded["call"] == (
        "raw",
        4,
        ("buffer", "float[]", (1.0, 0.5, 0.25, 1.0)),
        3,
    )


def test_set_shader_value_wraps_int_uniforms(monkeypatch) -> None:
    recorded: dict = {}
    monkeypatch.setattr(shader, "pr", _fake_cffi_pr(recorded))

    shader.set_shader_value("raw", 5, 7, 4)
    assert recorded["call"] == ("raw", 5, ("buffer", "int[]", (7,)), 4)

    shader.set_shader_value("raw", 6, [1, 2], 5)
    assert recorded["call"] == ("raw", 6, ("buffer", "int[]", (1, 2)), 5)


def test_set_shader_value_passes_cdata_through(monkeypatch) -> None:
    recorded: dict = {}
    monkeypatch.setattr(shader, "pr", _fake_cffi_pr(recorded))
    pointer = object()

    shader.set_shader_value("raw", 3, pointer, 0)

    assert recorded["call"] == ("raw", 3, pointer, 0)
