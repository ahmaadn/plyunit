from __future__ import annotations

import importlib
from itertools import count
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock

import numpy as np
import pytest

import plyunit.backends.integrations.raylib.text as text_mod
from plyunit.backends.integrations.raylib.handler import Font, Texture2D
from plyunit.backends.integrations.raylib.text import Text, shape_glyphs
from plyunit.backends.ports.handler import FontHandle, Texture2DHandle
from plyunit.backends.ports.text import IText, ShapedText, TemplateText
from plyunit.core.units.unit_registry import UnitRegistry


def _make_fake_font(*, base_size: int = 16, tex_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(
        baseSize=base_size,
        glyphCount=3,
        glyphPadding=0,
        texture=SimpleNamespace(id=tex_id, width=32, height=32, format=7, mipmaps=1),
        recs=[
            SimpleNamespace(x=0.0, y=0.0, width=8.0, height=12.0),
            SimpleNamespace(x=8.0, y=0.0, width=8.0, height=12.0),
            SimpleNamespace(x=16.0, y=0.0, width=4.0, height=12.0),
        ],
        glyphs=[
            SimpleNamespace(offsetX=0, offsetY=0, advanceX=8),
            SimpleNamespace(offsetX=0, offsetY=0, advanceX=8),
            SimpleNamespace(offsetX=0, offsetY=0, advanceX=4),
        ],
    )


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    registry = UnitRegistry()
    unit_mod = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_mod, "units", registry)
    default = _make_fake_font(tex_id=1)
    ids = count(2)
    image = SimpleNamespace(width=32, height=32)
    fake_pr = SimpleNamespace(
        get_font_default=Mock(return_value=default),
        load_font=Mock(side_effect=lambda path: _make_fake_font(tex_id=next(ids))),
        load_font_from_image=Mock(
            side_effect=lambda *_: _make_fake_font(tex_id=next(ids))
        ),
        is_font_valid=Mock(
            side_effect=lambda raw: raw.baseSize > 0 and raw.glyphCount > 0
        ),
        load_image=Mock(return_value=image),
        is_image_valid=Mock(return_value=True),
        unload_image=Mock(),
        unload_font=Mock(),
        Color=Mock(side_effect=lambda *channels: channels),
        get_glyph_index=Mock(
            side_effect=lambda raw, cp: {65: 0, 66: 1, 32: 2, 9: 2}.get(cp, 0)
        ),
    )
    monkeypatch.setattr(text_mod, "pr", fake_pr)
    renderer = SimpleNamespace(
        canvas=SimpleNamespace(draw_text=Mock()),
        render_shaped_text=Mock(),
    )
    service = Text(renderer=renderer)
    yield SimpleNamespace(
        text=service,
        pr=fake_pr,
        default=default,
        image=image,
        renderer=renderer,
        registry=registry,
    )
    fake_pr.unload_font.side_effect = None
    for item in registry.group(Text):
        item.destroy()


def test_text_construction_and_template_selection_are_window_independent(env) -> None:
    assert isinstance(env.text, IText)
    assert env.registry.one("@Text") is env.text
    assert env.text["base"] is env.text
    assert env.text["missing"] is env.text
    env.pr.get_font_default.assert_not_called()
    env.pr.load_font.assert_not_called()


def test_get_font_lazily_returns_concrete_handle_with_borrowed_atlas(env) -> None:
    font = env.text.get_font()
    assert isinstance(font, Font)
    assert isinstance(font, FontHandle)
    assert font.raw_font is env.default
    assert font.base_size == 16
    assert font.glyph_count == 3
    assert isinstance(font.texture, Texture2D)
    assert isinstance(font.texture, Texture2DHandle)
    assert font.texture.raw_texture is env.default.texture
    assert font.texture.texture_id == font.texture.parent_id
    assert font.texture.source_rect == (0.0, 0.0, 32.0, 32.0)
    assert font.texture.width == 32
    assert font.texture.height == 32
    assert env.text.get_font("missing") is font
    env.pr.get_font_default.assert_called_once_with()


def test_reserved_default_font_name_never_loads_or_unloads_a_file(env) -> None:
    font = env.text.get_font()
    shape = env.text.shape("AB")
    assert env.text.load_font("default", "hack.ttf") is font
    assert env.text.shape("AB") is shape
    env.pr.load_font.assert_not_called()
    env.pr.unload_font.assert_not_called()


def test_set_get_and_load_templates(env) -> None:
    env.text.set_template("title", "default", spacing=2, size=22)
    template = env.text.get_template("title")
    assert template == TemplateText("default", 2.0, 22)
    assert env.text.get_template("missing") is env.text.get_template("base")
    env.text.load_templates({"hud": {"font": "default", "spacing": None, "size": 14}})
    assert env.text.get_template("hud") == TemplateText("default", None, 14)


def test_replacing_selected_template_changes_measurement_without_reselecting(
    env,
) -> None:
    env.text.set_template("title", "default", spacing=0, size=16)
    env.text["title"]
    old = env.text.shape("AB")
    env.text.set_template("title", "default", spacing=2, size=32)
    new = env.text.shape("AB")
    assert new is not old
    assert new.total_width == 34
    assert new.total_height == 32
    assert env.text.measure("AB") == (34, 32)


def test_base_template_replacement_is_observed_after_missing_template_fallback(
    env,
) -> None:
    env.text["missing"]
    env.text.set_template("base", "default", spacing=0, size=24)
    assert env.text.measure("AB") == (24, 24)


def test_templates_and_caches_are_not_shared_between_text_services(env) -> None:
    other = Text()
    env.text.set_template("base", "default", spacing=9, size=99)
    assert other.get_template("base") == TemplateText("default", None, 16)
    first = env.text.shape("AB")
    second = other.shape("AB")
    assert first is not second
    assert first.texture is not second.texture
    assert first.texture.texture_id != second.texture.texture_id


def test_shape_glyphs_returns_readonly_float32_quads_with_texture_handle(env) -> None:
    font = env.text.get_font()
    glyph_cache = {}
    shaped = shape_glyphs(font, "AB", 16, 0, glyph_cache)
    assert isinstance(shaped, ShapedText)
    assert shaped.texture is font.texture
    assert not hasattr(shaped, "tex_id")
    assert shaped.offsets_xy.shape == (2, 2)
    assert shaped.sizes_wh.shape == (2, 2)
    assert shaped.uv_rects.shape == (2, 4)
    assert shaped.total_width == 16
    assert shaped.total_height == 16
    assert glyph_cache == {65: 0, 66: 1}
    for array in (shaped.offsets_xy, shaped.sizes_wh, shaped.uv_rects):
        assert array.dtype == np.float32
        assert array.flags.c_contiguous
        assert not array.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        shaped.offsets_xy[0, 0] = 100


def test_spacing_is_applied_only_between_characters(env) -> None:
    shaped = shape_glyphs(env.text.get_font(), "AB", 16, 2, {})
    np.testing.assert_array_equal(shaped.offsets_xy, [[0, 0], [10, 0]])
    assert shaped.total_width == 18


@pytest.mark.parametrize("text", ["A B", "A\tB"])
def test_spaces_and_tabs_advance_without_visible_quads(env, text) -> None:
    shaped = shape_glyphs(env.text.get_font(), text, 16, 0, {})
    assert shaped.offsets_xy.shape == (2, 2)
    np.testing.assert_array_equal(shaped.offsets_xy, [[0, 0], [12, 0]])
    assert shaped.total_width == 20


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_newlines_reset_spacing_and_use_longest_line_for_width(env, separator) -> None:
    shaped = shape_glyphs(env.text.get_font(), f"AB{separator}A", 16, 2, {})
    np.testing.assert_array_equal(shaped.offsets_xy, [[0, 0], [10, 0], [0, 16]])
    assert shaped.total_width == 18
    assert shaped.total_height == 32


def test_blank_lines_and_trailing_newline_contribute_to_height(env) -> None:
    shaped = env.text.shape("A\n\nB\n", spacing=0)
    np.testing.assert_array_equal(shaped.offsets_xy, [[0, 0], [0, 32]])
    assert shaped.total_width == 8
    assert shaped.total_height == 64


def test_empty_text_has_consistent_empty_arrays_and_one_line_height(env) -> None:
    shaped = env.text.shape("", spacing=0)
    assert shaped.offsets_xy.shape == (0, 2)
    assert shaped.sizes_wh.shape == (0, 2)
    assert shaped.uv_rects.shape == (0, 4)
    assert shaped.total_width == 0
    assert shaped.total_height == 16
    assert env.text.measure("") == (0, 16)


def test_zero_advance_falls_back_to_rectangle_width(env) -> None:
    env.default.glyphs[0].advanceX = 0
    assert env.text.shape("AA", spacing=0).total_width == 16


def test_glyph_padding_offsets_and_uvs_match_raylib_at_double_size(env) -> None:
    raw = env.default
    raw.glyphPadding = 2
    raw.recs[0].x = 10
    raw.recs[0].y = 6
    raw.glyphs[0].offsetX = 3
    raw.glyphs[0].offsetY = 5
    shaped = env.text.shape("A", font_size=32, spacing=0)
    np.testing.assert_array_equal(shaped.offsets_xy, [[2, 6]])
    np.testing.assert_array_equal(shaped.sizes_wh, [[24, 32]])
    np.testing.assert_array_equal(shaped.uv_rects, [[0.25, 0.125, 0.625, 0.625]])
    assert shaped.total_width == 16


def test_unicode_lookup_is_memoized_per_codepoint(env) -> None:
    font = env.text.get_font()
    cache = {}
    shape_glyphs(font, "λAλ", 16, 0, cache)
    shape_glyphs(font, "λλ", 32, 2, cache)
    assert cache == {ord("λ"): 0, ord("A"): 0}
    assert env.pr.get_glyph_index.call_count == 2


@pytest.mark.parametrize("index", [-1, 3])
def test_invalid_glyph_indices_are_rejected_instead_of_indexing_native_memory(
    env, index
) -> None:
    env.pr.get_glyph_index.side_effect = None
    env.pr.get_glyph_index.return_value = index
    cache = {}
    with pytest.raises(ValueError, match="invalid glyph index"):
        shape_glyphs(env.text.get_font(), "A", 16, 0, cache)
    assert cache == {}


def test_invalid_cached_glyph_index_is_rejected(env) -> None:
    with pytest.raises(ValueError, match="invalid glyph index"):
        shape_glyphs(env.text.get_font(), "A", 16, 0, {65: -1})


def test_raw_fonts_and_released_handles_are_rejected(env) -> None:
    with pytest.raises(TypeError, match="Font handle"):
        shape_glyphs(env.default, "A", 16, 0, {})
    font = env.text.load_font("custom", "custom.ttf")
    env.text.unload_fonts()
    with pytest.raises(ValueError, match="invalid font"):
        shape_glyphs(font, "A", 16, 0, {})
    with pytest.raises(ValueError, match="released"):
        _ = font.texture
    with pytest.raises(ValueError, match="released"):
        _ = font.base_size


def test_shape_and_measure_share_cache_and_explicit_zero_spacing(env) -> None:
    first = env.text.shape("AB")
    calls = env.pr.get_glyph_index.call_count
    assert env.text.measure("AB") == (17, 16)
    assert env.text.shape("AB") is first
    assert env.pr.get_glyph_index.call_count == calls
    assert env.text.shape("AB", spacing=0).total_width == 16
    assert env.text.shape("AB", spacing=0) is not first


def test_render_and_push_forward_cached_handle_based_shapes(env) -> None:
    expected = env.text.shape("AB")
    env.text.push(
        "AB", pos=(10, 20), color=(1, 2, 3, 4), z=5, layer=1, origin=(2, 3), rotation=45
    )
    env.renderer.render_shaped_text.assert_called_once_with(
        expected,
        pos=(10, 20),
        color=(1, 2, 3, 4),
        origin=(2, 3),
        rotation=45,
        z=5,
        layer=1,
    )
    env.text.render("AB", pos=(30, 40))
    assert env.renderer.render_shaped_text.call_args.args[0] is expected


def test_immediate_draw_passes_font_handle_and_resolved_spacing_to_canvas(env) -> None:
    env.text.draw("A\r\nB", pos=(1, 2), color=(255, 0, 0, 255), font_size=20)
    env.renderer.canvas.draw_text.assert_called_once_with(
        text="A\nB",
        pos=(1, 2),
        color=(255, 0, 0, 255),
        font_size=20,
        spacing=2.0,
        font=env.text.get_font(),
        origin=(0, 0),
        rotation=0,
    )
    env.renderer.render_shaped_text.assert_not_called()


@pytest.mark.parametrize("font_size", [0, -1])
def test_invalid_font_sizes_are_not_silently_replaced_by_template_defaults(
    env, font_size
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        env.text.shape("A", font_size=font_size)
    with pytest.raises(ValueError, match="positive integer"):
        env.text.draw("A", pos=(0, 0), font_size=font_size)
    with pytest.raises(ValueError, match="positive integer"):
        env.text.set_template("bad", "default", size=font_size)


@pytest.mark.parametrize("spacing", [float("nan"), float("inf")])
def test_nonfinite_spacing_is_rejected(env, spacing) -> None:
    with pytest.raises(ValueError, match="finite"):
        env.text.shape("A", spacing=spacing)
    with pytest.raises(ValueError, match="finite"):
        env.text.set_template("bad", "default", spacing=spacing)


def test_backend_api_annotations_use_concrete_font_handles() -> None:
    assert get_type_hints(Text.load_font)["return"] is Font
    assert get_type_hints(Text.get_font)["return"] is Font
    assert get_type_hints(shape_glyphs)["font"] is Font
    assert IText.load_font.__annotations__["return"] == "FontHandle"
    assert IText.get_font.__annotations__["return"] == "FontHandle"
