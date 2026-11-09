"""Regressions for streaming resource ownership and pixel-upload failures."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.backends.integrations.raylib.handler import StreamingTexture, Texture2D
from plyunit.backends.integrations.raylib.renderer import streaming_texture as module


@pytest.fixture
def gl(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Provide a deterministic OpenGL adapter without a graphics context."""
    functions = {name: MagicMock() for name in (
        "glGenBuffers", "glDeleteBuffers", "glBindBuffer", "glBufferData",
        "glMapBuffer", "glUnmapBuffer", "glBindTexture", "glPixelStorei",
        "glTexSubImage2D",
    )}
    functions["glMapBuffer"].return_value = object()
    functions["glUnmapBuffer"].return_value = 1
    state = {
        module.GL_PIXEL_UNPACK_BUFFER_BINDING: 21,
        module.GL_TEXTURE_BINDING_2D: 22,
        module.GL_UNPACK_ALIGNMENT: 8,
    }
    monkeypatch.setattr(module, "_initialized", True)
    monkeypatch.setattr(module, "get_gl_func", lambda name, signature: functions[name])
    monkeypatch.setattr(module, "get_gl_integer", state.__getitem__)
    monkeypatch.setattr(module, "new_uint_buffer", lambda size, values=None: list(values) if values is not None else [0] * size)
    monkeypatch.setattr(module, "flush_render_batch", MagicMock())
    copy = MagicMock()
    unload = MagicMock()
    monkeypatch.setattr(module, "copy_to_native", copy)
    monkeypatch.setattr(module.pr, "unload_texture", unload)
    return SimpleNamespace(functions=functions, copy=copy, unload=unload)


@pytest.fixture
def stream() -> StreamingTexture:
    """Create a backend handle around a small fake RGB texture."""
    raw = SimpleNamespace(id=42, width=3, height=2, format=6)
    return StreamingTexture(Texture2D.from_raw(raw), 3, 2, 3, [10, 11])


def test_first_frame_uploads_only_after_its_buffer_is_filled(gl, stream) -> None:
    events = []
    gl.copy.side_effect = lambda *args: events.append("fill")
    gl.functions["glTexSubImage2D"].side_effect = lambda *args: events.append("upload")
    assert stream.update(b"a" * 18)
    assert events == ["fill", "upload"]
    assert stream._primed and stream.current_pbo == 1
    gl.functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 10)
    gl.functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 21)
    gl.functions["glBindTexture"].assert_any_call(module.GL_TEXTURE_2D, 22)
    assert stream.update(b"b" * 18)
    assert events == ["fill", "upload", "upload", "fill"]
    assert stream.current_pbo == 0


def test_rgb_upload_restores_unpack_alignment(gl, stream) -> None:
    """Three-pixel RGB rows must not be treated as padded four-byte rows."""
    assert stream.update(b"a" * 18)
    assert gl.functions["glPixelStorei"].call_args_list == [
        ((module.GL_UNPACK_ALIGNMENT, 1),),
        ((module.GL_UNPACK_ALIGNMENT, 8),),
    ]


@pytest.mark.parametrize("failure", ["map", "unmap", "copy"])
def test_failed_fill_never_primes_or_uploads_uninitialized_pixels(gl, stream, failure) -> None:
    if failure == "map":
        gl.functions["glMapBuffer"].return_value = module.NULL_POINTER
    elif failure == "unmap":
        gl.functions["glUnmapBuffer"].return_value = 0
    else:
        gl.copy.side_effect = RuntimeError("copy failed")
    assert not stream.update(b"a" * 18)
    assert stream.current_pbo == 0 and not stream._primed
    gl.functions["glTexSubImage2D"].assert_not_called()
    if failure != "map":
        gl.functions["glUnmapBuffer"].assert_called_once()
    gl.functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 0)
    gl.functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 21)
    gl.functions["glBindTexture"].assert_any_call(module.GL_TEXTURE_2D, 22)


def test_upload_exception_restores_gl_state_and_allows_retry(gl, stream) -> None:
    gl.functions["glTexSubImage2D"].side_effect = RuntimeError("upload failed")
    assert not stream.update(b"a" * 18)
    assert stream.current_pbo == 0 and not stream._primed
    gl.functions["glPixelStorei"].assert_any_call(module.GL_UNPACK_ALIGNMENT, 8)
    gl.functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 21)
    gl.functions["glBindTexture"].assert_any_call(module.GL_TEXTURE_2D, 22)
    gl.functions["glTexSubImage2D"].side_effect = None
    assert stream.update(b"b" * 18)


@pytest.mark.parametrize("failure", ["resolve", "names", "data"])
def test_allocation_failure_releases_texture_and_partial_buffers(gl, monkeypatch, failure) -> None:
    raw = SimpleNamespace(id=42, width=3, height=2, format=6)
    monkeypatch.setattr(module, "_load_blank_texture", lambda *args: Texture2D.from_raw(raw))
    functions = gl.functions
    if failure == "resolve":
        def get_func(name, signature):
            if name == "glGenBuffers":
                raise RuntimeError("missing entry point")
            return functions[name]
        monkeypatch.setattr(module, "get_gl_func", get_func)
    else:
        names = [10, 0] if failure == "names" else [10, 11]
        functions["glGenBuffers"].side_effect = lambda count, out: out.__setitem__(slice(None), names)
        if failure == "data":
            functions["glBufferData"].side_effect = RuntimeError("allocation failed")
    assert module.create_streaming_texture(3, 2, channels=3) is None
    gl.unload.assert_called_once_with(raw)
    if failure != "resolve":
        expected = [10] if failure == "names" else [10, 11]
        functions["glDeleteBuffers"].assert_called_once_with(len(expected), expected)
    functions["glBindBuffer"].assert_any_call(module.GL_PIXEL_UNPACK_BUFFER, 21)


def test_stream_owns_its_exposed_texture(gl, monkeypatch) -> None:
    from plyunit.backends.integrations.raylib.assets import Assets

    raw = SimpleNamespace(id=42, width=3, height=2, format=6)
    monkeypatch.setattr(module, "_load_blank_texture", lambda *args: Texture2D.from_raw(raw))
    gl.functions["glGenBuffers"].side_effect = lambda count, out: out.__setitem__(slice(None), [10, 11])
    result = module.create_streaming_texture(3, 2, channels=3)
    assert result is not None
    with pytest.raises(ValueError, match="owned|borrowed|root"):
        Assets().store_texture("stream", result.texture)
    gl.unload.assert_not_called()


def test_destroy_still_releases_resources_after_availability_reset(gl, stream) -> None:
    raw = stream.texture.raw_texture
    module.reset_streaming()
    stream.destroy()
    gl.functions["glDeleteBuffers"].assert_called_once_with(2, [10, 11])
    gl.unload.assert_called_once_with(raw)
    assert not stream.alive and not stream.pbo_ids
    assert not stream.update(b"a" * 18)
    with pytest.raises(ValueError, match="released"):
        _ = stream.texture
    stream.destroy()
    gl.unload.assert_called_once()


def test_buffer_delete_failure_still_releases_texture(gl, stream) -> None:
    raw = stream.texture.raw_texture
    gl.functions["glDeleteBuffers"].side_effect = RuntimeError("delete failed")
    with pytest.raises(RuntimeError, match="delete failed"):
        stream.destroy()
    gl.unload.assert_called_once_with(raw)
    assert not stream.alive
