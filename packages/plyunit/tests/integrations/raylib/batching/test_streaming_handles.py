"""Streaming texture handle tests at the concrete raylib boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.backends.integrations.raylib.handler import StreamingTexture, Texture2D
from plyunit.backends.integrations.raylib.renderer import streaming_texture as module
from plyunit.backends.ports.handler import StreamingTextureHandle


def test_streaming_texture_wraps_concrete_handle_and_native_id() -> None:
    """Streaming distinguishes numeric GPU names from string asset identities."""
    raw = SimpleNamespace(id=73, width=2, height=2, format=7)
    texture = Texture2D.from_raw(raw, texture_id="pixels")
    stream = StreamingTexture(texture, 2, 2, 4, [1, 2])
    assert isinstance(stream, StreamingTextureHandle)
    assert isinstance(stream.texture, Texture2D)
    assert stream.texture is texture
    assert stream.texture.texture_id == "pixels"
    assert stream.texture_id == 73


def test_blank_texture_converts_pixel_data_not_just_format_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RGB streaming needs converted pixel bytes before upload, not relabeled RGBA."""
    image = SimpleNamespace(format=7)
    raw = SimpleNamespace(id=73, width=2, height=2, format=6)
    fake = SimpleNamespace(
        BLANK=(0, 0, 0, 0),
        gen_image_color=MagicMock(return_value=image),
        image_format=MagicMock(),
        load_texture_from_image=MagicMock(return_value=raw),
        unload_image=MagicMock(),
    )
    monkeypatch.setattr(module, "pr", fake)
    monkeypatch.setattr(
        module,
        "rl",
        SimpleNamespace(
            PIXELFORMAT_UNCOMPRESSED_R8G8B8=6,
            PIXELFORMAT_UNCOMPRESSED_R8G8B8A8=7,
        ),
    )
    texture = module._load_blank_texture(2, 2, 3)
    fake.image_format.assert_called_once_with(image, 6)
    fake.load_texture_from_image.assert_called_once_with(image)
    fake.unload_image.assert_called_once_with(image)
    assert isinstance(texture, Texture2D)
    assert texture.raw_texture is raw


def test_blank_texture_always_releases_cpu_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A native upload error still frees its temporary image."""
    image = SimpleNamespace(format=7)
    fake = SimpleNamespace(
        BLANK=(0, 0, 0, 0),
        gen_image_color=MagicMock(return_value=image),
        image_format=MagicMock(),
        load_texture_from_image=MagicMock(side_effect=RuntimeError("upload failed")),
        unload_image=MagicMock(),
    )
    monkeypatch.setattr(module, "pr", fake)
    monkeypatch.setattr(
        module, "rl", SimpleNamespace(PIXELFORMAT_UNCOMPRESSED_R8G8B8A8=7)
    )
    with pytest.raises(RuntimeError, match="upload failed"):
        module._load_blank_texture(2, 2, 4)
    fake.unload_image.assert_called_once_with(image)
