from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as Canvas


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class C:
        def __init__(self, *a):
            self.a = a

    class V:
        def __init__(self, x=0, y=0):
            if isinstance(x, (tuple, list)):
                x, y = x[0], x[1]
            self.x = float(x)
            self.y = float(y)

    class R:
        def __init__(self, x, y, w, h):
            self.x = float(x)
            self.y = float(y)
            self.width = float(w)
            self.height = float(h)

    def rec(*a, **k):
        calls.append(a)

    fake = SimpleNamespace(
        Color=C,
        Vector2=V,
        Rectangle=R,
        BLACK=C(0, 0, 0, 255),
        WHITE=C(255, 255, 255, 255),
        BLANK=C(0, 0, 0, 0),
        draw_pixel=rec,
        draw_pixel_v=rec,
        draw_line=rec,
        draw_line_v=rec,
        draw_line_ex=rec,
        draw_circle=rec,
        draw_circle_v=rec,
        draw_circle_lines=rec,
        draw_circle_lines_v=rec,
        draw_ellipse=rec,
        draw_ellipse_lines=rec,
        draw_ring=rec,
        draw_ring_lines=rec,
        draw_rectangle=rec,
        draw_rectangle_v=rec,
        draw_rectangle_rec=rec,
        draw_rectangle_pro=rec,
        draw_rectangle_lines=rec,
        draw_rectangle_lines_ex=rec,
        draw_rectangle_rounded=rec,
        draw_rectangle_rounded_lines=rec,
        draw_triangle=rec,
        draw_triangle_lines=rec,
        draw_poly=rec,
        draw_poly_lines=rec,
        draw_poly_lines_ex=rec,
        draw_text=rec,
        draw_text_ex=rec,
        draw_text_pro=rec,
        draw_texture=rec,
        draw_texture_v=rec,
        draw_texture_ex=rec,
        draw_texture_rec=rec,
        draw_texture_pro=rec,
        draw_texture_n_patch=rec,
        begin_scissor_mode=rec,
        # pyrefly: ignore [bad-argument-type]
        end_scissor_mode=lambda: calls.append("end_scissor"),
        begin_blend_mode=rec,
        # pyrefly: ignore [bad-argument-type]
        end_blend_mode=lambda: calls.append("end_blend"),
        begin_shader_mode=rec,
        # pyrefly: ignore [bad-argument-type]
        end_shader_mode=lambda: calls.append("end_shader"),
        begin_texture_mode=rec,
        # pyrefly: ignore [bad-argument-type]
        end_texture_mode=lambda: calls.append("end_texmode"),
        clear_background=rec,
        # pyrefly: ignore [bad-argument-type]
        rl_push_matrix=lambda: calls.append("push"),
        # pyrefly: ignore [bad-argument-type]
        rl_pop_matrix=lambda: calls.append("pop"),
        rl_translatef=rec,
        rl_rotatef=rec,
        rl_scalef=rec,
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
        gui_get_font=lambda: SimpleNamespace(name="default"),
        draw_circle_sector=rec,
        draw_circle_sector_lines=rec,
    )
    monkeypatch.setattr(Canvas, "pr", fake)
    return calls


def test_canvas_helpers(fake_pr):
    assert Canvas.to_color((1, 2, 3, 4)) is not None
    assert Canvas.to_vec2((1, 2)) is not None
    assert Canvas.to_rect((0, 0, 10, 10)) is not None
    assert Canvas.rgb(1, 2, 3) is not None
    assert Canvas.rgba(1, 2, 3, 4) is not None


def test_canvas_many_draw_paths(fake_pr):
    calls = fake_pr
    Canvas.draw_pixel(pos=(1, 2), color=(255, 0, 0, 255))
    Canvas.draw_line(start=(0, 0), end=(1, 1), color=(0, 0, 0, 255), thickness=2)
    Canvas.draw_circle(center=(0, 0), radius=5, color=(1, 1, 1, 255))
    Canvas.draw_circle(
        center=(0, 0), radius=5, color=(1, 1, 1, 255), outline_only=True
    )
    Canvas.draw_ellipse(center=(0, 0), radius_h=3, radius_v=2, color=(1, 1, 1, 255))
    Canvas.draw_ellipse(
        center=(0, 0), radius_h=3, radius_v=2, color=(1, 1, 1, 255), outline_only=True
    )
    Canvas.draw_ring(
        center=(0, 0),
        inner_radius=2,
        outer_radius=5,
        start_angle=0,
        end_angle=90,
        color=(1, 1, 1, 255),
    )
    Canvas.draw_rectangle(rect=(0, 0, 10, 10), color=(1, 1, 1, 255))
    Canvas.draw_rectangle(
        rect=(0, 0, 10, 10), color=(1, 1, 1, 255), outline_only=True
    )
    Canvas.draw_triangle(
        v1=(0, 0), v2=(1, 0), v3=(0, 1), color=(1, 1, 1, 255)
    )
    Canvas.draw_triangle(
        v1=(0, 0), v2=(1, 0), v3=(0, 1), color=(1, 1, 1, 255), outline_only=True
    )
    Canvas.draw_poly(center=(0, 0), sides=6, radius=10, color=(1, 1, 1, 255))
    Canvas.draw_poly(
        center=(0, 0), sides=6, radius=10, color=(1, 1, 1, 255), outline_only=True
    )
    Canvas.draw_text(text="hi", pos=(0, 0), font_size=12, color=(255, 255, 255, 255))
    tex = SimpleNamespace(id=1, width=16, height=16)
    # pyrefly: ignore [bad-argument-type]
    Canvas.draw_texture(texture=tex, pos=(0, 0))
    # pyrefly: ignore [bad-argument-type]
    Canvas.draw_texture(texture=tex, pos=(0, 0), scale=2.0, rotation=45)
    Canvas.draw_texture(
        # pyrefly: ignore [bad-argument-type]
        texture=tex, dest=(0, 0, 32, 32), source=(0, 0, 16, 16)
    )
    Canvas.begin_scissor_mode(0, 0, 100, 100)
    Canvas.end_scissor_mode()
    Canvas.begin_blend_mode(1)
    Canvas.end_blend_mode()
    # pyrefly: ignore [bad-argument-type]
    Canvas.begin_shader_mode(SimpleNamespace(id=1))
    Canvas.end_shader_mode()
    # pyrefly: ignore [bad-argument-type]
    Canvas.begin_texture_mode(SimpleNamespace(id=2))
    Canvas.end_texture_mode()
    assert len(calls) > 10
