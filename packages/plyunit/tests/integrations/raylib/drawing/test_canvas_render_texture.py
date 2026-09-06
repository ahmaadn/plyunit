"""raylib canvas render-texture functions (tilemap bake), without a GPU."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as canvas_mod
from plyunit.backends.integrations.raylib.drawing.canvas import (
    clear_transparent,
    draw_texture_region,
    gen_mipmaps,
    load_render_texture,
    set_texture_filter,
    unload_render_texture,
)


def test_canvas_render_texture_ops(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    tex = SimpleNamespace(id="tex")
    rt = SimpleNamespace(texture=tex)
    fake = SimpleNamespace(
        load_render_texture=lambda w, h: calls.append(("load", w, h)) or rt,
        unload_render_texture=lambda t: calls.append(("unload", t)),
        begin_texture_mode=lambda t: calls.append(("begin", t)),
        end_texture_mode=lambda: calls.append(("end",)),
        clear_background=lambda c: calls.append(("clear", c)),
        draw_texture_pro=lambda *a: calls.append(("draw", a[0])),
        gen_texture_mipmaps=lambda t: calls.append(("mipmap", t)),
        set_texture_filter=lambda t, f: calls.append(("filter", t, f)),
        TextureFilter=SimpleNamespace(
            TEXTURE_FILTER_TRILINEAR="tri",
            TEXTURE_FILTER_POINT="point",
        ),
        Rectangle=lambda x, y, w, h: (x, y, w, h),
        Vector2=lambda x, y: (x, y),
        WHITE=(255, 255, 255, 255),
        BLANK=(0, 0, 0, 0),
    )
    monkeypatch.setattr(canvas_mod, "pr", fake)

    assert load_render_texture(10, 20) is rt
    canvas_mod.begin_texture_mode(rt)
    clear_transparent()
    draw_texture_region("tex", (0, 0, 8, 8), (1, 2, 8, 8))
    canvas_mod.end_texture_mode()
    gen_mipmaps(rt)
    set_texture_filter(rt, "trilinear")
    set_texture_filter(rt, "point")
    unload_render_texture(rt)

    assert ("load", 10, 20) in calls
    assert ("clear", fake.BLANK) in calls
    assert ("draw", "tex") in calls
    assert ("mipmap", tex) in calls
    assert ("filter", tex, "tri") in calls
    assert ("filter", tex, "point") in calls
    assert ("unload", rt) in calls


def test_canvas_render_texture_noop_without_texture(
    monkeypatch: pytest.MonkeyPatch,
):
    def _boom(*a):
        raise AssertionError("must not touch pr")

    fake = SimpleNamespace(
        gen_texture_mipmaps=_boom,
        set_texture_filter=_boom,
    )
    monkeypatch.setattr(canvas_mod, "pr", fake)
    # A target without a ``texture`` attribute is a no-op.
    gen_mipmaps(SimpleNamespace())
    set_texture_filter(SimpleNamespace(), "point")
