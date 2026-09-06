from __future__ import annotations

from types import SimpleNamespace

from plyunit.rendering.enum import PrimitiveKind
from plyunit.rendering.queue import PrimitiveItem


class FakeCanvas:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def draw_pixel(self, **kw):
        self.calls.append("pixel")

    def draw_line(self, **kw):
        self.calls.append("line")

    def draw_circle(self, **kw):
        self.calls.append("circle")

    def draw_ellipse(self, **kw):
        self.calls.append("ellipse")

    def draw_ring(self, **kw):
        self.calls.append("ring")

    def draw_rectangle(self, **kw):
        self.calls.append("rect")

    def draw_triangle(self, **kw):
        self.calls.append("tri")

    def draw_poly(self, **kw):
        self.calls.append("poly")

    def draw_rectangle_batch(self, **kw):
        self.calls.append("rects")

    def draw_circle_batch(self, **kw):
        self.calls.append("circles")

    def draw_line_batch(self, **kw):
        self.calls.append("lines")

    def draw_triangle_batch(self, **kw):
        self.calls.append("tris")

