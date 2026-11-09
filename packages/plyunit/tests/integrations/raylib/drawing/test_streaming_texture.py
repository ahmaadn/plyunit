from __future__ import annotations

from types import SimpleNamespace

import pytest

from plyunit.backends.integrations.raylib.handler import StreamingTexture, Texture2D
import plyunit.backends.integrations.raylib.renderer.gl_ffi as gl_ffi
import plyunit.backends.integrations.raylib.renderer.streaming_texture as stream_mod
from plyunit.backends.integrations.raylib.renderer.streaming_texture import (
    create_streaming_texture,
    destroy_streaming_texture,
    init_streaming,
    is_streaming_available,
    update_streaming_texture,
)


@pytest.fixture(autouse=True)
def streaming_gl_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate availability and native scalar queries from other GL tests."""
    monkeypatch.setattr(stream_mod, "_initialized", False)
    monkeypatch.setattr(stream_mod, "get_gl_integer", lambda parameter: 4 if parameter == stream_mod.GL_UNPACK_ALIGNMENT else 0)


def test_create_streaming_rejects_bad_channels() -> None:
    with pytest.raises(ValueError, match="channels"):
        create_streaming_texture(16, 16, channels=2)


def test_create_streaming_rejects_bad_size() -> None:
    with pytest.raises(ValueError, match="width"):
        create_streaming_texture(0, 16, channels=4)


def test_update_size_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_mod._initialized = True
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)

    tex = Texture2D.from_raw(SimpleNamespace(id=1, width=2, height=2, format=7))
    st = StreamingTexture(texture=tex, width=2, height=2, channels=4, pbo_ids=[10, 11])
    assert st.buffer_size == 16
    assert update_streaming_texture(st, b"\x00" * 8) is False


def test_update_map_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_mod._initialized = True

    def fake_get(name: str, signature: str):
        if name == "glMapBuffer":
            return lambda *a: stream_mod.pr.ffi.NULL
        return lambda *a: None

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get)
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)

    tex = Texture2D.from_raw(SimpleNamespace(id=7, width=2, height=2, format=7))
    st = StreamingTexture(
        texture=tex,
        width=2,
        height=2,
        channels=4,
        pbo_ids=[10, 11],
    )
    ok = update_streaming_texture(st, b"\x00" * 16)
    assert ok is False


def test_update_success_swaps_pbo(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = object()
    moves: list[tuple] = []

    stream_mod._initialized = True

    def fake_get(name: str, signature: str):
        if name == "glMapBuffer":
            return lambda *a: mapped
        if name == "glUnmapBuffer":
            return lambda *a: 1
        return lambda *a: None

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get)
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)
    monkeypatch.setattr(
        stream_mod.pr,
        "ffi",
        SimpleNamespace(
            NULL=None,
            memmove=lambda ptr, data, size: moves.append((ptr, len(data), size)),
        ),
        raising=False,
    )

    tex = Texture2D.from_raw(SimpleNamespace(id=3, width=2, height=2, format=7))
    st = StreamingTexture(
        texture=tex,
        width=2,
        height=2,
        channels=4,
        pbo_ids=[100, 101],
    )
    payload = b"\x01" * 16
    assert st.update(payload) is True
    assert st.current_pbo == 1
    assert moves and moves[0][1] == 16


def test_destroy_marks_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[int] = []
    unloaded: list = []

    stream_mod._initialized = True

    def fake_get(name: str, signature: str):
        if name == "glDeleteBuffers":
            return lambda n, ids: deleted.append(n)
        return lambda *a: None

    monkeypatch.setattr(stream_mod, "get_gl_func", fake_get)
    monkeypatch.setattr(stream_mod, "flush_render_batch", lambda: None)
    monkeypatch.setattr(
        stream_mod.pr,
        "ffi",
        SimpleNamespace(new=lambda *a, **k: [0, 0]),
        raising=False,
    )
    monkeypatch.setattr(
        stream_mod.pr,
        "unload_texture",
        lambda t: unloaded.append(t),
        raising=False,
    )

    tex = Texture2D.from_raw(SimpleNamespace(id=5, width=4, height=4, format=7))
    st = StreamingTexture(
        texture=tex, width=4, height=4, channels=4, pbo_ids=[1, 2]
    )
    destroy_streaming_texture(st)
    assert st.alive is False
    assert deleted == [2]
    assert unloaded == [tex.raw_texture]
    destroy_streaming_texture(st)
    assert deleted == [2]


def test_init_streaming_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_mod.reset_streaming()
    gl_ffi.reset_gl_funcs()

    fake_addr = object()
    monkeypatch.setattr(
        gl_ffi.pr, "rl_get_proc_address", lambda name: fake_addr, raising=False
    )
    monkeypatch.setattr(
        gl_ffi.pr,
        "ffi",
        SimpleNamespace(NULL=None, cast=lambda signature, addr: 1234 if signature == "uintptr_t" else lambda *a, **k: None),
        raising=False,
    )
    assert init_streaming() is True
    assert is_streaming_available() is True
    assert init_streaming() is True
    stream_mod.reset_streaming()
    gl_ffi.reset_gl_funcs()


def test_canvas_streaming_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    from plyunit.backends.integrations.raylib.renderer import canvas as Canvas

    calls: list[str] = []
    monkeypatch.setattr(
        Canvas, "init_streaming", lambda: calls.append("init") or True
    )
    monkeypatch.setattr(
        Canvas,
        "create_streaming_texture",
        lambda w, h, channels=4: calls.append(f"create:{w}x{h}:{channels}") or "tex",
    )
    monkeypatch.setattr(
        Canvas,
        "destroy_streaming_texture",
        lambda s: calls.append(f"destroy:{s}"),
    )

    assert Canvas.init_streaming() is True
    assert Canvas.create_streaming_texture(8, 4, channels=4) == "tex"
    Canvas.destroy_streaming_texture("tex")
    assert calls == ["init", "create:8x4:4", "destroy:tex"]
