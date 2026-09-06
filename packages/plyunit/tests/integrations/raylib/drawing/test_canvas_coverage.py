from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as Canvas


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []

    class C:
        def __init__(self, *a):
            pass

    class V:
        def __init__(self, x=0, y=0):
            if isinstance(x, tuple):
                x, y = x
            self.x = float(x)
            self.y = float(y)

    class R:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = x, y, w, h

    fake = SimpleNamespace(
        Color=C,
        Vector2=V,
        Rectangle=R,
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        BLANK=(0, 0, 0, 0),
        draw_pixel=lambda *a: calls.append(("pixel", a)),
        draw_pixel_v=lambda *a: calls.append(("pixel_v", a)),
        draw_line=lambda *a: calls.append(("line", a)),
        draw_line_v=lambda *a: calls.append(("line_v", a)),
        draw_line_ex=lambda *a: calls.append(("line_ex", a)),
        draw_circle=lambda *a: calls.append(("circle", a)),
        draw_circle_v=lambda *a: calls.append(("circle_v", a)),
        draw_circle_lines=lambda *a: calls.append(("circle_lines", a)),
        draw_circle_lines_v=lambda *a: calls.append(("circle_lines_v", a)),
        draw_ellipse=lambda *a: calls.append(("ellipse", a)),
        draw_ellipse_lines=lambda *a: calls.append(("ellipse_lines", a)),
        draw_ring=lambda *a: calls.append(("ring", a)),
        draw_ring_lines=lambda *a: calls.append(("ring_lines", a)),
        draw_rectangle=lambda *a: calls.append(("rect", a)),
        draw_rectangle_v=lambda *a: calls.append(("rect_v", a)),
        draw_rectangle_rec=lambda *a: calls.append(("rect_rec", a)),
        draw_rectangle_lines=lambda *a: calls.append(("rect_lines", a)),
        draw_rectangle_lines_ex=lambda *a: calls.append(("rect_lines_ex", a)),
        draw_triangle=lambda *a: calls.append(("tri", a)),
        draw_triangle_lines=lambda *a: calls.append(("tri_lines", a)),
        draw_poly=lambda *a: calls.append(("poly", a)),
        draw_poly_lines=lambda *a: calls.append(("poly_lines", a)),
        draw_poly_lines_ex=lambda *a: calls.append(("poly_lines_ex", a)),
        draw_text=lambda *a: calls.append(("text", a)),
        draw_text_ex=lambda *a: calls.append(("text_ex", a)),
        draw_texture=lambda *a: calls.append(("tex", a)),
        draw_texture_v=lambda *a: calls.append(("tex_v", a)),
        draw_texture_ex=lambda *a: calls.append(("tex_ex", a)),
        draw_texture_rec=lambda *a: calls.append(("tex_rec", a)),
        draw_texture_pro=lambda *a: calls.append(("tex_pro", a)),
        begin_scissor_mode=lambda *a: calls.append(("scissor", a)),
        end_scissor_mode=lambda: calls.append(("end_scissor",)),
        begin_blend_mode=lambda m: calls.append(("blend", m)),
        end_blend_mode=lambda: calls.append(("end_blend",)),
        begin_shader_mode=lambda s: calls.append(("shader", s)),
        end_shader_mode=lambda: calls.append(("end_shader",)),
        begin_texture_mode=lambda t: calls.append(("texmode", t)),
        end_texture_mode=lambda: calls.append(("end_texmode",)),
        clear_background=lambda c: calls.append(("clear", c)),
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
        gui_get_font=lambda: SimpleNamespace(name="default"),
    )
    monkeypatch.setattr(Canvas, "pr", fake)
    return calls


def test_canvas_draw_primitives(fake_pr):
    calls = fake_pr
    Canvas.draw_pixel(pos=(1, 2), color=(255, 0, 0, 255))
    Canvas.draw_line(start=(0, 0), end=(10, 10), color=(0, 255, 0, 255))
    Canvas.draw_circle(center=(5, 5), radius=3, color=(0, 0, 255, 255))
    Canvas.draw_ellipse(center=(5, 5), radius_h=4, radius_v=2, color=(1, 1, 1, 255))
    Canvas.draw_rectangle(rect=(0, 0, 10, 10), color=(9, 9, 9, 255))
    Canvas.draw_triangle(
        v1=(0, 0), v2=(1, 0), v3=(0, 1), color=(2, 2, 2, 255)
    )
    Canvas.draw_poly(center=(0, 0), sides=5, radius=10, color=(3, 3, 3, 255))
    assert len(calls) >= 5


def test_canvas_gpu_modes(fake_pr):
    calls = fake_pr
    Canvas.begin_scissor_mode(10, 10, 100, 100)
    Canvas.end_scissor_mode()
    Canvas.begin_blend_mode(1)
    Canvas.end_blend_mode()
    # pyrefly: ignore [bad-argument-type]
    Canvas.begin_shader_mode(SimpleNamespace(id=1))
    Canvas.end_shader_mode()
    assert any(c[0] == "scissor" for c in calls)
    assert any(c[0] == "blend" for c in calls)


def test_canvas_text_and_texture(fake_pr):
    calls = fake_pr
    Canvas.draw_text(text="hi", pos=(0, 0), font_size=16, color=(255, 255, 255, 255))
    tex = SimpleNamespace(id=1, width=8, height=8)
    # pyrefly: ignore [bad-argument-type]
    Canvas.draw_texture(texture=tex, pos=(0, 0))
    assert any(c[0].startswith("text") or c[0].startswith("tex") for c in calls)
