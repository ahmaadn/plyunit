from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.assets.font as text_mod
from plyunit.assets.text import Text
from plyunit.backends.integrations.raylib.assets import Font
from plyunit.backends.integrations.raylib.assets.font import shape_text


def _fake_font():
    return SimpleNamespace(
        baseSize=16,
        texture=SimpleNamespace(id=7, width=32, height=32),
        recs=[SimpleNamespace(x=0.0, y=0.0, width=8.0, height=12.0)],
        glyphs=[SimpleNamespace(offsetX=0.0, offsetY=0.0, advanceX=8.0)],
    )


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    default_font = _fake_font()
    draws = []
    shaped_submits = []

    class FakeRenderer:
        canvas = SimpleNamespace(
            draw_text=lambda **kw: draws.append(kw),
        )

        def render_shaped_text(self, shaped, **kw):
            shaped_submits.append((shaped, kw))

        def render_text(self, **kw):
            pass

    fake_pr = SimpleNamespace(
        get_font_default=lambda: default_font,
        load_font=lambda path: SimpleNamespace(
            path=path,
            baseSize=16,
            texture=SimpleNamespace(id=2, width=8, height=8),
            recs=[SimpleNamespace(x=0, y=0, width=8, height=12)],
            glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=8)],
        ),
        load_font_from_image=lambda img, key=None, firstChar=32: SimpleNamespace(
            img=True,
            baseSize=16,
            texture=SimpleNamespace(id=3, width=8, height=8),
            recs=[SimpleNamespace(x=0, y=0, width=8, height=12)],
            glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=8)],
        ),
        load_image=lambda path: SimpleNamespace(path=path),
        unload_image=lambda img: None,
        unload_font=lambda f: None,
        Color=lambda *a: a,
        get_glyph_index=lambda font, cp: 0,
        WHITE=(255, 255, 255, 255),
    )
    monkeypatch.setattr(text_mod, "pr", fake_pr)
    monkeypatch.setattr(text_mod, "templates", text_mod._build_default_templates())
    monkeypatch.setattr(text_mod, "font_cache", {"default": default_font})
    monkeypatch.setattr(text_mod, "glyph_index_cache", {})
    monkeypatch.setattr(text_mod, "version", 0)

    text = Text()
    # pyrefly: ignore [bad-assignment]
    text.one = lambda q, **kw: FakeRenderer()
    return text, draws, shaped_submits, fake_pr


def test_text_draw_push_measure(env):
    text, draws, shaped_submits, _ = env
    text["base"]
    text.draw("hello", pos=(1, 2), color=(255, 0, 0, 255), font_size=20)
    assert draws and draws[0]["text"] == "hello"
    text.push("world", pos=(3, 4), z=1, layer=2)
    assert shaped_submits
    shaped, kw = shaped_submits[0]
    assert kw["pos"] == (3, 4)
    assert kw["z"] == 1
    assert shaped.offsets_xy.shape[0] == len("world")
    w, h = text.measure("abc", font_size=16)
    assert w == 27  # 3 * advance 8 + 2 * automatic spacing 1.6
    assert h == 16


def test_font_load_config(tmp_path, env):
    _, _, _, fake_pr = env
    cfg = {
        "fonts": {
            "main": {"path": "main.ttf"},
            "bad": {},
            "img": {"path": "f.png", "color_key": [255, 0, 255, 255], "first_char": 32},
        },
        "templates": {
            "title": {"font": "main", "spacing": 1, "size": 24},
        },
    }
    path = tmp_path / "font.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    font = Font()
    font.load(str(path))
    assert "main" in font.font_cache
    assert "title" in font.templates
    assert font.templates["title"].font_size == 24


def test_shape_text_empty(env):
    _, _, _, _ = env
    font = Font().get_font()
    shaped = shape_text(font, "", 16, 0, {})
    assert shaped.offsets_xy.shape == (0, 2)
