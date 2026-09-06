from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.streaming_texture as stream_mod
from plyunit.backends.integrations.raylib.drawing.streaming_texture import (
    create_streaming_texture,
    destroy_streaming_texture,
)


def test_create_streaming_texture_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_mod._initialized = True
    created_pbo: list[int] = []
    binds: list[tuple] = []

    def gl_gen_buffers(n, out):
        out[0] = 10
        out[1] = 11
        created_pbo.extend([10, 11])

    def gl_bind_buffer(target, bid):
        binds.append((target, bid))

    def gl_buffer_data(target, size, data, usage):
        binds.append(("data", size, usage))

    def fake_get(name: str, signature: str):
        return {
            "glGenBuffers": gl_gen_buffers,
            "glBindBuffer": gl_bind_buffer,
            "glBufferData": gl_buffer_data,
        }[name]

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get)
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)

    image = SimpleNamespace(format=0)
    texture = SimpleNamespace(id=42, width=8, height=4)

    monkeypatch.setattr(
        stream_mod.pr,
        "gen_image_color",
        lambda w, h, c: image,
        raising=False,
    )
    monkeypatch.setattr(
        stream_mod.pr,
        "load_texture_from_image",
        lambda img: texture,
        raising=False,
    )
    monkeypatch.setattr(stream_mod.pr, "unload_image", lambda img: None, raising=False)
    monkeypatch.setattr(
        stream_mod.pr,
        "PIXELFORMAT_UNCOMPRESSED_R8G8B8A8",
        7,
        raising=False,
    )
    monkeypatch.setattr(
        stream_mod.pr,
        "PIXELFORMAT_UNCOMPRESSED_R8G8B8",
        4,
        raising=False,
    )
    monkeypatch.setattr(stream_mod.pr, "BLANK", (0, 0, 0, 0), raising=False)
    monkeypatch.setattr(
        stream_mod.pr,
        "ffi",
        SimpleNamespace(
            NULL=None,
            new=lambda *a, **k: [0, 0],
        ),
        raising=False,
    )

    st = create_streaming_texture(8, 4, channels=4)
    assert st is not None
    assert st.texture_id == 42
    assert st.width == 8
    assert st.height == 4
    assert st.channels == 4
    assert st._buffer_size == 8 * 4 * 4
    assert st._pbo_ids == [10, 11]
    assert created_pbo == [10, 11]

    # destroy without real GL
    def gl_delete(n, ids):
        binds.append(("delete", n))

    def fake_get2(name: str, signature: str):
        if name == "glDeleteBuffers":
            return gl_delete
        return lambda *a: None

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get2)
    monkeypatch.setattr(
        stream_mod.pr, "unload_texture", lambda t: binds.append(("unload", t.id)), raising=False
    )
    destroy_streaming_texture(st)
    assert st._alive is False
    assert ("delete", 2) in binds
    assert ("unload", 42) in binds


def test_create_streaming_rgb_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_mod._initialized = True

    def fake_get(name: str, signature: str):
        if name == "glGenBuffers":
            return lambda n, out: out.__setitem__(slice(None), [1, 2])
        return lambda *a: None

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get)
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)
    monkeypatch.setattr(
        stream_mod.pr, "gen_image_color", lambda *a: SimpleNamespace(format=0), raising=False
    )
    monkeypatch.setattr(
        stream_mod.pr,
        "load_texture_from_image",
        lambda img: SimpleNamespace(id=9, width=2, height=2),
        raising=False,
    )
    monkeypatch.setattr(stream_mod.pr, "unload_image", lambda img: None, raising=False)
    monkeypatch.setattr(
        stream_mod.pr, "PIXELFORMAT_UNCOMPRESSED_R8G8B8", 4, raising=False
    )
    monkeypatch.setattr(
        stream_mod.pr, "PIXELFORMAT_UNCOMPRESSED_R8G8B8A8", 7, raising=False
    )
    monkeypatch.setattr(stream_mod.pr, "BLANK", (0, 0, 0, 0), raising=False)
    monkeypatch.setattr(
        stream_mod.pr, "ffi", SimpleNamespace(NULL=None, new=lambda *a, **k: [0, 0]), raising=False
    )

    st = create_streaming_texture(2, 2, channels=3)
    assert st is not None
    assert st.channels == 3
    assert st._buffer_size == 12
