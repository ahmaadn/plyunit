from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as Canvas


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class C:
        def __init__(self, *args):
            pass

    class V:
        def __init__(self, x=0, y=0):
            if isinstance(x, (tuple, list)):
                x, y = x[0], x[1]
            self.x = float(x)
            self.y = float(y)

    class R:
        def __init__(self, x, y, width, height):
            self.x = float(x)
            self.y = float(y)
            self.width = float(width)
            self.height = float(height)

    fake = SimpleNamespace(
        Color=C,
        Vector2=V,
        Rectangle=R,
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        BLANK=(0, 0, 0, 0),
        draw_pixel_v=lambda *args: calls.append("pixel"),
        draw_line_ex=lambda *args: calls.append("line"),
        draw_circle_v=lambda *args: calls.append("circle"),
        draw_circle_lines_v=lambda *args: calls.append("circle_lines"),
        draw_ellipse=lambda *args: calls.append("ellipse"),
        draw_ellipse_lines=lambda *args: calls.append("ellipse_lines"),
        draw_ring=lambda *args: calls.append("ring"),
        draw_ring_lines=lambda *args: calls.append("ring_lines"),
        draw_rectangle_rec=lambda *args: calls.append("rect"),
        draw_rectangle_lines=lambda *args: calls.append("rect_lines"),
        draw_rectangle_lines_ex=lambda *args: calls.append("rect_lines_ex"),
        draw_triangle=lambda *args: calls.append("tri"),
        draw_triangle_lines=lambda *args: calls.append("tri_lines"),
        draw_poly=lambda *args: calls.append("poly"),
        draw_poly_lines_ex=lambda *args: calls.append("poly_lines"),
        draw_text=lambda *args: calls.append("text"),
        draw_text_ex=lambda *args: calls.append("text_ex"),
        draw_texture_v=lambda *args: calls.append("tex"),
        draw_texture_ex=lambda *args: calls.append("tex_ex"),
        draw_texture_pro=lambda *args: calls.append("tex_pro"),
        draw_texture_rec=lambda *args: calls.append("tex_rec"),
        begin_scissor_mode=lambda *args: calls.append("scissor"),
        end_scissor_mode=lambda: calls.append("end_scissor"),
        begin_blend_mode=lambda mode: calls.append("blend"),
        end_blend_mode=lambda: calls.append("end_blend"),
        begin_shader_mode=lambda shader: calls.append("shader"),
        end_shader_mode=lambda: calls.append("end_shader"),
        begin_texture_mode=lambda texture: calls.append("texmode"),
        end_texture_mode=lambda: calls.append("end_texmode"),
        clear_background=lambda color: calls.append("clear"),
        draw_rectangle=lambda *args: calls.append("rectangle"),
        draw_circle=lambda *args: calls.append("circle"),
        draw_line=lambda *args: calls.append("line"),
        draw_line_v=lambda *args: calls.append("line"),
        draw_pixel=lambda *args: calls.append("pixel"),
        draw_texture=lambda *args: calls.append("texture"),
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
    )
    monkeypatch.setattr(Canvas, "pr", fake)
    return calls


def test_canvas_batches(fake_pr):
    Canvas.draw_rectangle_batch(
        rects=[(0, 0, 10, 10), (20, 20, 5, 5)],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )
    Canvas.draw_circle_batch(
        centers=[(0, 0), (10, 10)],
        radii=[5, 3],
        colors=[(1, 1, 1, 255), (2, 2, 2, 255)],
    )
    Canvas.draw_line_batch(
        starts=[(0, 0), (1, 1)],
        ends=[(10, 10), (2, 2)],
        colors=[(255, 255, 255, 255), (0, 0, 0, 255)],
    )
    Canvas.draw_triangle_batch(
        v1s=[(0, 0)],
        v2s=[(1, 0)],
        v3s=[(0, 1)],
        colors=[(255, 0, 0, 255)],
    )

    assert fake_pr.count("rect") == 2
    assert fake_pr.count("circle") == 2
    assert fake_pr.count("line") == 2
    assert fake_pr.count("tri") == 1


def test_canvas_ring_and_outlines(fake_pr):
    Canvas.draw_ring(
        center=(0, 0),
        inner_radius=5,
        outer_radius=10,
        start_angle=0,
        end_angle=180,
        color=(255, 0, 0, 255),
    )
    Canvas.draw_circle(
        center=(0, 0),
        radius=5,
        color=(0, 0, 0, 255),
        outline_only=True,
    )
    Canvas.draw_rectangle(
        rect=(0, 0, 10, 10),
        color=(1, 1, 1, 255),
        outline_only=True,
    )

    assert "ring" in fake_pr
    assert "circle_lines" in fake_pr
    assert "rect_lines" in fake_pr
