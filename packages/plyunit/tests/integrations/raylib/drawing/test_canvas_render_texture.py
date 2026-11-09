"""Render-target and sampling operations using concrete raylib handles."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from plyunit._enums import TextureFilter
from plyunit.backends.integrations.raylib.handler import RenderTexture, Texture2D
from plyunit.backends.integrations.raylib.renderer import canvas


@pytest.fixture
def backend(monkeypatch):
    raw_texture = SimpleNamespace(id=12, width=10, height=20, format=7)
    raw_target = SimpleNamespace(id=4, texture=raw_texture)
    fake = SimpleNamespace(
        load_render_texture=Mock(return_value=raw_target),
        unload_render_texture=Mock(),
        begin_texture_mode=Mock(),
        end_texture_mode=Mock(),
        draw_texture_pro=Mock(),
        gen_texture_mipmaps=Mock(),
        set_texture_filter=Mock(),
        TEXTURE_FILTER_POINT=0,
        TEXTURE_FILTER_BILINEAR=1,
        TEXTURE_FILTER_TRILINEAR=2,
        Rectangle=lambda *values: values,
        Vector2=lambda *values: values,
        WHITE=(255, 255, 255, 255),
    )
    monkeypatch.setattr(canvas, "pr", fake)
    monkeypatch.setattr(canvas, "rl", SimpleNamespace(
        TEXTURE_FILTER_POINT=0,
        TEXTURE_FILTER_BILINEAR=1,
        TEXTURE_FILTER_TRILINEAR=2,
    ))
    return fake, raw_target


def test_render_target_operations_unwrap_only_inside_adapter(backend):
    fake, raw_target = backend
    target = canvas.load_render_texture(10, 20)
    assert isinstance(target, RenderTexture)
    assert target.raw_render_texture is raw_target
    assert target.texture is target.texture
    assert isinstance(target.texture, Texture2D)
    canvas.begin_texture_mode(target)
    canvas.draw_texture_region(target.texture, (0, 0, 8, 8), (1, 2, 8, 8))
    canvas.end_texture_mode()
    canvas.gen_mipmaps(target)
    canvas.unload_render_texture(target)
    fake.begin_texture_mode.assert_called_once_with(raw_target)
    fake.draw_texture_pro.assert_called_once_with(
        raw_target.texture, (0, 0, 8, 8), (1, 2, 8, 8), (0, 0), 0.0, fake.WHITE
    )
    fake.gen_texture_mipmaps.assert_called_once_with(raw_target.texture)
    fake.unload_render_texture.assert_called_once_with(raw_target)


@pytest.mark.parametrize(
    ("filter_mode", "expected"),
    [(TextureFilter.NEAREST, 0), (TextureFilter.LINEAR, 1), (TextureFilter.TRILINEAR, 2)],
)
@pytest.mark.parametrize("use_target", [True, False])
def test_sampling_modes_use_explicit_enum_mapping(backend, filter_mode, expected, use_target):
    fake, raw = backend
    target = RenderTexture(raw)
    canvas.set_texture_filter(target if use_target else target.texture, filter_mode)
    fake.set_texture_filter.assert_called_once_with(raw.texture, expected)


def test_sampling_does_not_accept_removed_string_modes(backend):
    fake, raw = backend
    with pytest.raises((ValueError, TypeError, KeyError)):
        canvas.set_texture_filter(RenderTexture(raw), "point")
    fake.set_texture_filter.assert_not_called()
