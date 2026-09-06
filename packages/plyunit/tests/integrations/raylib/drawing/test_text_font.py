from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.assets.font as text_mod
from plyunit.assets.text import Text
from plyunit.assets.types import ShapedText, TemplateText
from plyunit.backends.integrations.raylib.assets import Font
from plyunit.backends.integrations.raylib.assets.font import shape_text


def _make_fake_font(*, base_size: int = 16, tex_id: int = 99) -> SimpleNamespace:
    """Minimal raylib-like Font for shape_text."""
    recs = [
        SimpleNamespace(x=0.0, y=0.0, width=8.0, height=12.0),  # A
        SimpleNamespace(x=8.0, y=0.0, width=8.0, height=12.0),  # B
        SimpleNamespace(x=16.0, y=0.0, width=4.0, height=12.0),  # space
    ]
    glyphs = [
        SimpleNamespace(offsetX=0.0, offsetY=0.0, advanceX=8.0),
        SimpleNamespace(offsetX=0.0, offsetY=0.0, advanceX=8.0),
        SimpleNamespace(offsetX=0.0, offsetY=0.0, advanceX=4.0),
    ]

    def get_idx(font, cp):
        return {65: 0, 66: 1, 32: 2}.get(cp, 0)

    return SimpleNamespace(
        baseSize=base_size,
        texture=SimpleNamespace(id=tex_id, width=32, height=32),
        recs=recs,
        glyphs=glyphs,
        _get_idx=get_idx,
    )


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    default_font = _make_fake_font(tex_id=1)
    unloaded: list = []

    def get_glyph_index(font, codepoint):
        return font._get_idx(font, codepoint)

    fake = SimpleNamespace(
        get_font_default=lambda: default_font,
        load_font=lambda path: SimpleNamespace(
            path=path,
            baseSize=16,
            texture=SimpleNamespace(id=2, width=32, height=32),
            recs=[SimpleNamespace(x=0, y=0, width=8, height=12)],
            glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=8)],
            _get_idx=lambda f, cp: 0,
        ),
        load_font_from_image=lambda img, key=None, firstChar=32: SimpleNamespace(
            img=img,
            first=firstChar,
            baseSize=16,
            texture=SimpleNamespace(id=3, width=32, height=32),
            recs=[SimpleNamespace(x=0, y=0, width=8, height=12)],
            glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=8)],
            _get_idx=lambda f, cp: 0,
        ),
        load_image=lambda path: SimpleNamespace(path=path),
        unload_image=lambda img: None,
        unload_font=lambda f: unloaded.append(f),
        Color=lambda *a: a,
        get_glyph_index=get_glyph_index,
        WHITE=(255, 255, 255, 255),
        BLACK=(0, 0, 0, 255),
    )
    monkeypatch.setattr(text_mod, "pr", fake)
    monkeypatch.setattr(text_mod, "templates", text_mod._build_default_templates())
    monkeypatch.setattr(text_mod, "font_cache", {"default": default_font})
    monkeypatch.setattr(text_mod, "glyph_index_cache", {})
    monkeypatch.setattr(text_mod, "version", 0)
    return fake, unloaded, default_font


def test_font_get_default(fake_pr):
    fake, _, default_font = fake_pr
    font = Font()
    assert font.get_font("default") is default_font
    assert font.get_font("missing") is not None
    assert font.version == 0


def test_font_get_default_populates_cache_lazily(fake_pr):
    _, _, default_font = fake_pr
    text_mod.font_cache.clear()

    assert text_mod.get_font() is default_font
    assert text_mod.font_cache["default"] is default_font


def test_font_get_default_refreshes_pre_window_font(fake_pr):
    _, _, default_font = fake_pr
    text_mod.font_cache["default"] = SimpleNamespace(baseSize=0)

    assert text_mod.get_font() is default_font


def test_font_set_and_get_template(fake_pr):
    font = Font()
    font.set_template("title", "default", spacing=2, size=22)
    t = font.get_template("title")
    assert isinstance(t, TemplateText)
    assert t.font_size == 22
    assert t.spacing == 2
    base = font.get_template("nope")
    assert base.font_name == "default"


def test_font_load_templates(fake_pr):
    font = Font()
    font.load_templates(
        {
            "hud": {"font": "default", "spacing": 1, "size": 14},
        }
    )
    assert font.templates["hud"].font_size == 14


def test_font_load_font_and_unload(fake_pr):
    _, unloaded, _ = fake_pr
    font = Font()
    font.load_font("custom", "x.ttf")
    assert "custom" in font.font_cache
    assert font.version == 1
    font.unload()
    assert "default" in font.font_cache
    assert unloaded
    assert font.version == 2
    assert font.glyph_index_cache == {}


def test_font_reserved_name_skipped(fake_pr):
    font = Font()
    before = font.version
    result = font.load_font("default", "hack.ttf")
    assert result is font.font_cache["default"]
    assert font.version == before


def test_font_load_image_font(fake_pr):
    font = Font()
    font.load_font("img", "sheet.png", color_key=(255, 0, 255, 255), first_char=32)
    assert "img" in font.font_cache
    assert font.version == 1


def test_text_service_getitem(fake_pr):
    text = Text()
    assert text.one("@Text") is text
    t = text["base"]
    assert t is text
    t2 = text["missing"]
    assert t2 is text


def test_shape_text_basic(fake_pr):
    _, _, default_font = fake_pr
    cache: dict[int, int] = {}
    shaped = shape_text(default_font, "AB", font_size=16, spacing=0, glyph_index_cache=cache)
    assert isinstance(shaped, ShapedText)
    assert shaped.offsets_xy.shape == (2, 2)
    assert shaped.sizes_wh.shape == (2, 2)
    assert shaped.uv_rects.shape == (2, 4)
    assert shaped.tex_id == 1
    assert 65 in cache and 66 in cache
    # space skipped as quad but advances
    shaped2 = shape_text(default_font, "A B", 16, 0, cache)
    assert shaped2.offsets_xy.shape[0] == 2
    assert shaped2.total_width > shaped.total_width


def test_shape_text_applies_spacing_only_between_characters(fake_pr):
    _, _, default_font = fake_pr

    shaped = shape_text(default_font, "AB", 16, 2, {})

    assert float(shaped.offsets_xy[1, 0]) == 10.0
    assert shaped.total_width == 18.0


def test_shape_text_newline(fake_pr):
    _, _, default_font = fake_pr
    shaped = shape_text(default_font, "A\nB", 16, 0, {})
    assert shaped.offsets_xy.shape[0] == 2
    assert float(shaped.offsets_xy[1, 1]) > 0
    assert shaped.total_height > 16


def test_text_measure_uses_shape_cache(fake_pr):
    text = Text()
    text["base"]
    w, h = text.measure("AB", font_size=16)
    assert w > 0 and h > 0
    # second measure hits cache
    w2, h2 = text.measure("AB", font_size=16)
    assert (w, h) == (w2, h2)


def test_text_push_submit_text_shaped(fake_pr):
    text = Text()
    calls = []

    class FakeRenderer:
        def render_shaped_text(self, shaped, **kw):
            calls.append((shaped, kw))

    text.one = lambda q, **kw: FakeRenderer()  # type: ignore[method-assign]
    text["base"].push("AB", pos=(10, 20), color=(1, 2, 3, 4), z=5, layer=1)
    assert len(calls) == 1
    shaped, kw = calls[0]
    assert isinstance(shaped, ShapedText)
    assert shaped.offsets_xy.shape[0] == 2
    assert kw["pos"] == (10, 20)
    assert kw["color"] == (1, 2, 3, 4)
    assert kw["z"] == 5


def test_text_draw_immediate(fake_pr):
    text = Text()
    draws = []

    class FakeRenderer:
        canvas = SimpleNamespace(draw_text=lambda **kw: draws.append(kw))

    text.one = lambda q, **kw: FakeRenderer()  # type: ignore[method-assign]
    text["base"].draw("hi", pos=(1, 2), color=(255, 0, 0, 255), font_size=20)
    assert draws and draws[0]["text"] == "hi"
    assert draws[0]["font_size"] == 20


def test_shape_cache_invalidated_on_font_version(fake_pr):
    text = Text()
    text["base"]
    text.measure("AB")
    assert len(text._shape_cache._store) == 1
    text.font.load_font("x", "a.ttf")
    text.measure("AB")
    # cache cleared then refilled
    assert len(text._shape_cache._store) == 1


def test_templates_shared_across_font_factories(fake_pr):
    a = Font()
    b = Font()
    a.set_template("base", "default", spacing=9, size=99)
    assert b.templates["base"].font_size == 99
    assert a.templates["base"].font_size == 99
