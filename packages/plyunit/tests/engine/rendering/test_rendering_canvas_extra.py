from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as canvas_module

Canvas = canvas_module


class FakeColor:
    def __init__(self, r: int, g: int, b: int, a: int):
        self.r = int(r)
        self.g = int(g)
        self.b = int(b)
        self.a = int(a)

class FakeVector2:
    def __init__(self, x=0.0, y=0.0):
        if isinstance(x, tuple):
            x, y = x
        self.x = float(x)
        self.y = float(y)

class FakeRectangle:
    def __init__(self, x: float, y: float, width: float, height: float):
        self.x = float(x)
        self.y = float(y)
        self.width = float(width)
        self.height = float(height)

def test_canvas_draw_circle_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list] = {
        "draw_circle_sector_lines": [],
        "draw_circle_sector": [],
        "draw_circle_gradient": [],
        "draw_circle_lines_v": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_circle_sector_lines=lambda *args: calls["draw_circle_sector_lines"].append(args),
        draw_circle_sector=lambda *args: calls["draw_circle_sector"].append(args),
        draw_circle_gradient=lambda *args: calls["draw_circle_gradient"].append(args),
        draw_circle_lines_v=lambda *args: calls["draw_circle_lines_v"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = Canvas

    # Sector outline
    canvas.draw_circle(center=(0, 0), radius=10, sector_angles=(0, 90), outline_only=True)
    assert len(calls["draw_circle_sector_lines"]) == 1

    # Sector solid
    canvas.draw_circle(center=(0, 0), radius=10, sector_angles=(0, 90))
    assert len(calls["draw_circle_sector"]) == 1

    # Gradient
    canvas.draw_circle(center=(0, 0), radius=10, gradient_outer=(255, 0, 0, 255))
    assert len(calls["draw_circle_gradient"]) == 1
    assert len(calls["draw_circle_gradient"][0]) == 4

    # Outline only
    canvas.draw_circle(center=(0, 0), radius=10, outline_only=True)
    assert len(calls["draw_circle_lines_v"]) == 1

def test_canvas_draw_rectangle_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list] = {
        "draw_rectangle_gradient_v": [],
        "draw_rectangle_gradient_h": [],
        "draw_rectangle_gradient_ex": [],
        "draw_rectangle_rounded_lines_ex": [],
        "draw_rectangle_lines_ex": [],
        "draw_rectangle_lines": [],
        "draw_rectangle_rounded": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_rectangle_gradient_v=lambda *args: calls["draw_rectangle_gradient_v"].append(args),
        draw_rectangle_gradient_h=lambda *args: calls["draw_rectangle_gradient_h"].append(args),
        draw_rectangle_gradient_ex=lambda *args: calls["draw_rectangle_gradient_ex"].append(args),
        draw_rectangle_rounded_lines_ex=lambda *args: calls["draw_rectangle_rounded_lines_ex"].append(args),
        draw_rectangle_lines_ex=lambda *args: calls["draw_rectangle_lines_ex"].append(args),
        draw_rectangle_lines=lambda *args: calls["draw_rectangle_lines"].append(args),
        draw_rectangle_rounded=lambda *args: calls["draw_rectangle_rounded"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = Canvas

    c1, c2 = (255, 0, 0, 255), (0, 255, 0, 255)
    c3, c4 = (0, 0, 255, 255), (255, 255, 0, 255)

    canvas.draw_rectangle(rect=(0, 0, 10, 10), gradient_v=(c1, c2))
    assert len(calls["draw_rectangle_gradient_v"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), gradient_h=(c1, c2))
    assert len(calls["draw_rectangle_gradient_h"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), gradient_ex=(c1, c2, c3, c4))
    assert len(calls["draw_rectangle_gradient_ex"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), outline_only=True, roundness=0.5, thickness=2.0)
    assert len(calls["draw_rectangle_rounded_lines_ex"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), outline_only=True, thickness=2.0)
    assert len(calls["draw_rectangle_lines_ex"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), outline_only=True)
    assert len(calls["draw_rectangle_lines"]) == 1

    canvas.draw_rectangle(rect=(0, 0, 10, 10), roundness=0.5)
    assert len(calls["draw_rectangle_rounded"]) == 1

def test_canvas_draw_ellipse_ring_triangle_poly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list] = {
        "draw_ellipse_lines": [],
        "draw_ellipse": [],
        "draw_ring_lines": [],
        "draw_ring": [],
        "draw_triangle_lines": [],
        "draw_triangle": [],
        "draw_poly_lines_ex": [],
        "draw_poly_lines": [],
        "draw_poly": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_ellipse_lines=lambda *args: calls["draw_ellipse_lines"].append(args),
        draw_ellipse=lambda *args: calls["draw_ellipse"].append(args),
        draw_ring_lines=lambda *args: calls["draw_ring_lines"].append(args),
        draw_ring=lambda *args: calls["draw_ring"].append(args),
        draw_triangle_lines=lambda *args: calls["draw_triangle_lines"].append(args),
        draw_triangle=lambda *args: calls["draw_triangle"].append(args),
        draw_poly_lines_ex=lambda *args: calls["draw_poly_lines_ex"].append(args),
        draw_poly_lines=lambda *args: calls["draw_poly_lines"].append(args),
        draw_poly=lambda *args: calls["draw_poly"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = Canvas

    # Ellipse
    canvas.draw_ellipse(center=(0, 0), radius_h=10, radius_v=5, outline_only=True)
    canvas.draw_ellipse(center=(0, 0), radius_h=10, radius_v=5)
    assert len(calls["draw_ellipse_lines"]) == 1
    assert len(calls["draw_ellipse"]) == 1

    # Ring
    canvas.draw_ring(center=(0, 0), outline_only=True)
    canvas.draw_ring(center=(0, 0))
    assert len(calls["draw_ring_lines"]) == 1
    assert len(calls["draw_ring"]) == 1

    # Triangle
    canvas.draw_triangle(v1=(0, 0), v2=(1, 0), v3=(0, 1), outline_only=True)
    canvas.draw_triangle(v1=(0, 0), v2=(1, 0), v3=(0, 1))
    assert len(calls["draw_triangle_lines"]) == 1
    assert len(calls["draw_triangle"]) == 1

    # Per-vertex gradient: three solid sub-triangles (no rlgl)
    calls["draw_triangle"].clear()
    canvas.draw_triangle(
        v1=(0, 0),
        v2=(10, 0),
        v3=(0, 10),
        gradient=((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)),
    )
    assert len(calls["draw_triangle"]) == 3

    # Poly
    canvas.draw_poly(center=(0, 0), sides=5, outline_only=True, thickness=2.0)
    canvas.draw_poly(center=(0, 0), sides=5, outline_only=True)
    canvas.draw_poly(center=(0, 0), sides=5)
    assert len(calls["draw_poly_lines_ex"]) == 1
    assert len(calls["draw_poly_lines"]) == 1
    assert len(calls["draw_poly"]) == 1

def test_canvas_draw_pixel(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list] = {
        "draw_pixel": [],
        "draw_pixel_v": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_pixel=lambda *args: calls["draw_pixel"].append(args),
        draw_pixel_v=lambda *args: calls["draw_pixel_v"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = Canvas

    canvas.draw_pixel(pos=(1, 2))
    assert len(calls["draw_pixel"]) == 1
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_pixel(pos=FakeVector2(1, 2))
    assert len(calls["draw_pixel_v"]) == 1

def test_canvas_gpu_state_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list] = {
        "begin_scissor_mode": [],
        "end_scissor_mode": [],
        "begin_blend_mode": [],
        "end_blend_mode": [],
        "begin_shader_mode": [],
        "end_shader_mode": [],
        "begin_texture_mode": [],
        "end_texture_mode": [],
    }

    fake_pr = SimpleNamespace(
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
        begin_scissor_mode=lambda *args: calls["begin_scissor_mode"].append(args),
        end_scissor_mode=lambda *args: calls["end_scissor_mode"].append(args),
        begin_blend_mode=lambda *args: calls["begin_blend_mode"].append(args),
        end_blend_mode=lambda *args: calls["end_blend_mode"].append(args),
        begin_shader_mode=lambda *args: calls["begin_shader_mode"].append(args),
        end_shader_mode=lambda *args: calls["end_shader_mode"].append(args),
        begin_texture_mode=lambda *args: calls["begin_texture_mode"].append(args),
        end_texture_mode=lambda *args: calls["end_texture_mode"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = Canvas

    canvas.begin_scissor_mode(10, 10, 100, 100)
    assert len(calls["begin_scissor_mode"]) == 1

    # Test scissor clamping (out of bounds)
    canvas.begin_scissor_mode(1000, 1000, 100, 100)
    assert calls["begin_scissor_mode"][-1] == (0, 0, 0, 0)

    canvas.end_scissor_mode()
    assert len(calls["end_scissor_mode"]) == 1

    canvas.begin_blend_mode(1)
    canvas.end_blend_mode()
    assert len(calls["begin_blend_mode"]) == 1
    assert len(calls["end_blend_mode"]) == 1

    shader = SimpleNamespace()
    # pyrefly: ignore [bad-argument-type]
    canvas.begin_shader_mode(shader)
    canvas.end_shader_mode()
    assert len(calls["begin_shader_mode"]) == 1
    assert len(calls["end_shader_mode"]) == 1

    texture = SimpleNamespace()
    # pyrefly: ignore [bad-argument-type]
    canvas.begin_texture_mode(texture)
    canvas.end_texture_mode()
    assert len(calls["begin_texture_mode"]) == 1
    assert len(calls["end_texture_mode"]) == 1
