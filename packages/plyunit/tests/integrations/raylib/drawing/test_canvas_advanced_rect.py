from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as Canvas


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class C:
        def __init__(self, *a):
            self.r = a[0] if a else 0
            self.g = a[1] if len(a) > 1 else 0
            self.b = a[2] if len(a) > 2 else 0
            self.a = a[3] if len(a) > 3 else 255

    class V:
        def __init__(self, x=0, y=0):
            if isinstance(x, (tuple, list)):
                x, y = x[0], x[1]
            self.x = float(x)
            self.y = float(y)

    class R:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = map(float, (x, y, w, h))

    def rec(*a, **k):
        calls.append(True)

    fake = SimpleNamespace(
        Color=C,
        Vector2=V,
        Rectangle=R,
        BLACK=C(0, 0, 0, 255),
        WHITE=C(255, 255, 255, 255),
        end_scissor_mode=lambda: None,
        end_blend_mode=lambda: None,
        end_shader_mode=lambda: None,
        end_texture_mode=lambda: None,
        rl_push_matrix=lambda: None,
        rl_pop_matrix=lambda: None,
        gui_get_font=lambda: SimpleNamespace(),
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
    )
    # Catch-all: any missing draw_* / begin_* attribute returns rec
    def _getattr(name):
        if name.startswith("draw_") or name.startswith("begin_") or name.startswith("rl_"):
            return rec
        raise AttributeError(name)

    fake.__getattr__ = _getattr  # type: ignore[method-assign]
    # also set common ones explicitly for SimpleNamespace
    for n in (
        "draw_rectangle",
        "draw_rectangle_rec",
        "draw_rectangle_lines",
        "draw_rectangle_lines_ex",
        "draw_rectangle_rounded",
        "draw_rectangle_rounded_lines",
        "draw_rectangle_rounded_lines_ex",
        "draw_rectangle_pro",
        "draw_rectangle_gradient_v",
        "draw_rectangle_gradient_h",
        "draw_rectangle_gradient_ex",
        "draw_circle",
        "draw_circle_v",
        "draw_circle_lines_v",
        "draw_circle_sector",
        "draw_circle_sector_lines",
        "draw_circle_gradient",
        "draw_line_ex",
        "draw_line_v",
        "draw_pixel_v",
        "draw_ellipse",
        "draw_ellipse_lines",
        "draw_ring",
        "draw_ring_lines",
        "draw_triangle",
        "draw_triangle_lines",
        "draw_poly",
        "draw_poly_lines",
        "draw_poly_lines_ex",
        "draw_text",
        "draw_text_ex",
        "draw_text_pro",
        "draw_texture_v",
        "draw_texture_ex",
        "draw_texture_pro",
        "draw_texture_rec",
        "begin_scissor_mode",
        "begin_blend_mode",
        "begin_shader_mode",
        "begin_texture_mode",
        "clear_background",
        "rl_translatef",
        "rl_rotatef",
        "rl_scalef",
    ):
        setattr(fake, n, rec)
    monkeypatch.setattr(Canvas, "pr", fake)
    return calls


def test_rounded_rect_and_corners(fake_pr):
    Canvas.draw_rectangle(
        rect=(0, 0, 40, 40),
        color=(255, 0, 0, 255),
        roundness=0.5,
        segments=8,
    )
    Canvas.draw_rectangle(
        rect=(0, 0, 40, 40),
        color=(255, 0, 0, 255),
        roundness=0.5,
        outline_only=True,
        thickness=2,
    )
    Canvas.draw_rectangle(
        rect=(0, 0, 40, 40),
        color=(0, 255, 0, 255),
        roundness=0.3,
        round_tl=True,
        round_tr=False,
        round_bl=True,
        round_br=False,
    )
    assert fake_pr


def test_circle_sector_gradient(fake_pr):
    Canvas.draw_circle(
        center=(10, 10),
        radius=20,
        color=(255, 0, 0, 255),
        sector_angles=(0, 90),
        segments=12,
    )
    Canvas.draw_circle(
        center=(10, 10),
        radius=20,
        color=(255, 0, 0, 255),
        gradient_outer=(0, 0, 255, 255),
    )
    assert fake_pr


def test_gradients_and_rotation(fake_pr):
    Canvas.draw_rectangle(
        rect=(0, 0, 20, 20),
        color=(1, 1, 1, 255),
        gradient_v=((255, 0, 0, 255), (0, 0, 255, 255)),
    )
    Canvas.draw_rectangle(
        rect=(0, 0, 20, 20),
        color=(1, 1, 1, 255),
        gradient_h=((255, 0, 0, 255), (0, 0, 255, 255)),
    )
    Canvas.draw_rectangle(
        rect=(0, 0, 20, 20),
        color=(1, 1, 1, 255),
        rotation=45,
        origin=(10, 10),
    )
    assert fake_pr
