"""Canvas texture-creation API (bake primitive -> Texture2D), without a GPU."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as canvas_mod
from plyunit.backends.integrations.raylib.drawing.canvas import (
    create_circle,
    create_circles,
    create_line,
    create_lines,
    create_poly,
    create_polys,
    create_rect,
    create_rects,
    create_triangle,
    create_triangles,
)


class FakeVec:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class FakeRect:
    def __init__(self, x, y, w, h):
        self.x = float(x)
        self.y = float(y)
        self.width = float(w)
        self.height = float(h)


class FakeCol:
    def __init__(self, r, g, b, a):
        self.r = int(r)
        self.g = int(g)
        self.b = int(b)
        self.a = int(a)


class FakeBakePr:
    """Fake pyray that records the render-texture bake lifecycle."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._next_id = 500

    # -- constructors -------------------------------------------------
    def Color(self, r, g, b, a):
        return FakeCol(r, g, b, a)

    def Vector2(self, x, y):
        return FakeVec(x, y)

    def Rectangle(self, x, y, w, h):
        return FakeRect(x, y, w, h)

    # -- constants ----------------------------------------------------
    BLANK = ("blank",)
    BLACK = ("black",)
    WHITE = ("white",)

    # -- render texture lifecycle -------------------------------------
    def load_render_texture(self, w, h):
        self.calls.append(("rt_load", int(w), int(h)))
        return SimpleNamespace(
            id=1, texture=SimpleNamespace(id=101, width=int(w), height=int(h))
        )

    def unload_render_texture(self, target):
        self.calls.append(("rt_unload", target.texture.id))

    def begin_texture_mode(self, target):
        self.calls.append(("rt_begin", target.texture.id))

    def end_texture_mode(self):
        self.calls.append(("rt_end",))

    def clear_background(self, color):
        self.calls.append(("clear", color))

    # -- readback / upload ---------------------------------------------
    def load_image_from_texture(self, texture):
        self.calls.append(("readback", texture.id))
        return SimpleNamespace(width=texture.width, height=texture.height)

    def image_flip_vertical(self, image):
        self.calls.append(("flip", image.width, image.height))

    def load_texture_from_image(self, image):
        self._next_id += 1
        texture = SimpleNamespace(
            id=self._next_id, width=image.width, height=image.height
        )
        self.calls.append(("upload", texture.id, image.width, image.height))
        return texture

    def unload_image(self, image):
        self.calls.append(("image_unload", image.width, image.height))

    # -- primitive draw (hot paths) ------------------------------------
    def draw_rectangle_rec(self, rect, color):
        self.calls.append(("draw_rect", rect, color))

    def draw_circle_v(self, center, radius, color):
        self.calls.append(("draw_circle", center, radius, color))

    def draw_line_v(self, start, end, color):
        self.calls.append(("draw_line", start, end, color))

    def draw_line_ex(self, start, end, thickness, color):
        self.calls.append(("draw_line_ex", start, end, thickness, color))

    def draw_triangle(self, v1, v2, v3, color):
        self.calls.append(("draw_triangle", v1, v2, v3, color))

    def draw_poly(self, center, sides, radius, rotation, color):
        self.calls.append(("draw_poly", center, sides, radius, rotation, color))

    def draw_poly_lines_ex(self, center, sides, radius, rotation, thickness, color):
        self.calls.append((
            "draw_poly_lines_ex",
            center,
            sides,
            radius,
            rotation,
            thickness,
            color,
        ))


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch) -> FakeBakePr:
    fake = FakeBakePr()
    monkeypatch.setattr(canvas_mod, "pr", fake)
    return fake


def test_create_rect_bakes_standalone_texture(fake_pr: FakeBakePr) -> None:
    texture = create_rect(rect=(5, 6, 20, 10), color=(255, 0, 0, 255))

    # RT dialokasikan seukuran rect (offset x/y dinormalisasi ke 0,0).
    assert ("rt_load", 20, 10) in fake_pr.calls
    assert ("clear", fake_pr.BLANK) in fake_pr.calls
    draw_calls = [c for c in fake_pr.calls if c[0] == "draw_rect"]
    assert len(draw_calls) == 1
    rect = draw_calls[0][1]
    assert (rect.x, rect.y, rect.width, rect.height) == (0.0, 0.0, 20.0, 10.0)

    # Hasil: readback -> flip -> upload mandiri; RT dan image dibebaskan.
    assert ("readback", 101) in fake_pr.calls
    assert ("flip", 20, 10) in fake_pr.calls
    assert texture.id > 500
    assert texture.width == 20 and texture.height == 10
    assert ("image_unload", 20, 10) in fake_pr.calls
    assert ("rt_unload", 101) in fake_pr.calls
    # The upload happens before the RT is unloaded.
    assert fake_pr.calls.index(("readback", 101)) < fake_pr.calls.index((
        "rt_unload",
        101,
    ))


def test_create_rect_clamps_min_size(fake_pr: FakeBakePr) -> None:
    texture = create_rect(rect=(0, 0, 0, 0))
    assert ("rt_load", 1, 1) in fake_pr.calls
    assert texture.width == 1 and texture.height == 1


def test_create_rects_returns_texture_per_rect(fake_pr: FakeBakePr) -> None:
    textures = create_rects(
        rects=[(0, 0, 4, 4), (0, 0, 8, 2)],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )

    assert isinstance(textures, list)
    assert len(textures) == 2
    assert textures[0] is not textures[1]
    assert textures[0].width == 4 and textures[0].height == 4
    assert textures[1].width == 8 and textures[1].height == 2
    rt_loads = [c for c in fake_pr.calls if c[0] == "rt_load"]
    assert rt_loads == [("rt_load", 4, 4), ("rt_load", 8, 2)]
    # Dua siklus bake lengkap (upload + unload per rect).
    assert len([c for c in fake_pr.calls if c[0] == "upload"]) == 2
    assert len([c for c in fake_pr.calls if c[0] == "rt_unload"]) == 2


def test_create_rects_empty_inputs(fake_pr: FakeBakePr) -> None:
    assert create_rects(rects=None, colors=None) == []
    assert create_rects(rects=[], colors=[]) == []


def test_create_circle_bakes_2r_box(fake_pr: FakeBakePr) -> None:
    texture = create_circle(radius=8.0, color=(0, 0, 255, 255))

    assert ("rt_load", 16, 16) in fake_pr.calls
    circles = [c for c in fake_pr.calls if c[0] == "draw_circle"]
    assert len(circles) == 1
    center, radius, _color = circles[0][1:]
    assert (center.x, center.y) == (8.0, 8.0)
    assert radius == 8.0
    assert texture.width == 16 and texture.height == 16


def test_create_circles_per_radius(fake_pr: FakeBakePr) -> None:
    textures = create_circles(radii=[4.0, 2.0], colors=None)

    assert [t.width for t in textures] == [8, 4]
    rt_loads = [c for c in fake_pr.calls if c[0] == "rt_load"]
    assert rt_loads == [("rt_load", 8, 8), ("rt_load", 4, 4)]


def test_create_line_pads_thickness(fake_pr: FakeBakePr) -> None:
    texture = create_line(start=(2, 3), end=(12, 3), color=None, thickness=4.0)

    # Bounding box 10 + margin thickness/2 on both sides = 14.
    assert ("rt_load", 14, 4) in fake_pr.calls
    lines = [c for c in fake_pr.calls if c[0] == "draw_line_ex"]
    assert len(lines) == 1
    start, end, thickness, _color = lines[0][1:]
    assert (start.x, start.y) == (2.0, 2.0)
    assert (end.x, end.y) == (12.0, 2.0)
    assert thickness == 4.0
    assert texture.width == 14 and texture.height == 4


def test_create_lines_translates_each_segment(fake_pr: FakeBakePr) -> None:
    textures = create_lines(
        starts=[(0, 0), (5, 5)],
        ends=[(10, 0), (5, 15)],
        colors=[(1, 2, 3, 4), (5, 6, 7, 8)],
    )

    assert len(textures) == 2
    rt_loads = [c for c in fake_pr.calls if c[0] == "rt_load"]
    # First line: bbox 10x0 (+0.5 thin margin of 1.0) -> 11x1.
    assert rt_loads[0] == ("rt_load", 11, 1)
    # Second line: vertical 0x10 (+0.5 margin) -> 1x11.
    assert rt_loads[1] == ("rt_load", 1, 11)


def test_create_triangle_bakes_vertex_bbox(fake_pr: FakeBakePr) -> None:
    texture = create_triangle(
        v1=(0, 0), v2=(10, 0), v3=(0, 6), color=(255, 255, 0, 255)
    )

    assert ("rt_load", 10, 6) in fake_pr.calls
    tris = [c for c in fake_pr.calls if c[0] == "draw_triangle"]
    assert len(tris) == 1
    v1, v2, v3, _color = tris[0][1:]
    assert (v1.x, v1.y) == (0.0, 0.0)
    assert (v2.x, v2.y) == (10.0, 0.0)
    assert (v3.x, v3.y) == (0.0, 6.0)
    assert texture.width == 10 and texture.height == 6


def test_create_triangles_batch(fake_pr: FakeBakePr) -> None:
    textures = create_triangles(
        v1s=[(0, 0), (1, 1)],
        v2s=[(4, 0), (3, 1)],
        v3s=[(0, 4), (1, 3)],
        colors=None,
    )

    assert len(textures) == 2
    rt_loads = [c for c in fake_pr.calls if c[0] == "rt_load"]
    assert rt_loads == [("rt_load", 4, 4), ("rt_load", 2, 2)]


def test_create_poly_and_polys_bake_polygon_textures(fake_pr: FakeBakePr) -> None:
    texture = create_poly(
        sides=6,
        radius=10.0,
        border_color=(255, 0, 255, 255),
        outline_only=True,
        thickness=2.0,
    )
    textures = create_polys(sides=[3, 4], radii=[4.0, 5.0])

    assert texture.width == 22 and texture.height == 22
    assert len(textures) == 2
    assert ("rt_load", 22, 22) in fake_pr.calls
    assert any(call[0] == "draw_poly_lines_ex" for call in fake_pr.calls)


def test_create_triangle_outline_pads_half_thickness(
    fake_pr: FakeBakePr,
) -> None:
    create_triangle(v1=(0, 0), v2=(8, 0), v3=(0, 8), outline_only=True, thickness=4.0)

    # Bounding box 8x8 + margin 2.0 (thickness/2) = 12x12.
    assert ("rt_load", 12, 12) in fake_pr.calls


def test_create_circle_sector_and_border_paths(fake_pr: FakeBakePr) -> None:
    fake_pr.draw_ring = lambda *a: fake_pr.calls.append(("ring", a))
    create_circle(
        radius=6.0,
        border_color=(0, 0, 0, 255),
        thickness=2.0,
        sector_angles=(0.0, 180.0),
        segments=12,
    )
    assert ("rt_load", 12, 12) in fake_pr.calls
    assert any(c[0] == "ring" for c in fake_pr.calls)
