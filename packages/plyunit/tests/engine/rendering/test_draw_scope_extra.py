from __future__ import annotations

from types import SimpleNamespace

import pytest

from plyunit.rendering.draw_scope import DrawScope
from plyunit.rendering.enum import BlendMode


class RecordingCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def begin_scissor_mode(self, x, y, w, h):
        self.calls.append(("scissor", x, y, w, h))

    def end_scissor_mode(self):
        self.calls.append(("end_scissor",))

    def begin_blend_mode(self, mode):
        self.calls.append(("blend", mode))

    def end_blend_mode(self):
        self.calls.append(("end_blend",))

    def begin_shader_mode(self, shader):
        self.calls.append(("shader", shader))

    def end_shader_mode(self):
        self.calls.append(("end_shader",))

    def begin_texture_mode(self, target):
        self.calls.append(("tex_begin", target))

    def end_texture_mode(self):
        self.calls.append(("tex_end",))

    def begin_stencil_mask(self):
        self.calls.append(("st_begin",))

    def end_stencil_mask(self):
        self.calls.append(("st_end",))

    def end_stencil_mask_inverse(self):
        self.calls.append(("st_end_inv",))

    def end_stencil_mode(self):
        self.calls.append(("st_mode_off",))

    def draw_circle(self, **kw):
        self.calls.append(("circle", kw))

    def draw_rectangle(self, **kw):
        self.calls.append(("rect", kw))

    def draw_line(self, **kw):
        self.calls.append(("line", kw))

    def draw_texture(self, **kw):
        self.calls.append(("texture", kw))


@pytest.fixture()
def scope():
    canvas = RecordingCanvas()
    renderer = SimpleNamespace(canvas=canvas, _immediate_active=True)
    # pyrefly: ignore [bad-argument-type]
    return DrawScope(renderer), canvas


def test_scissor_nested_restore(scope):
    draw, canvas = scope
    with draw.scissor(0, 0, 100, 50):
        with draw.scissor(10, 10, 20, 20):
            draw.circle(1, 2, 3)
    # outer re-applied after inner
    assert ("scissor", 0, 0, 100, 50) in canvas.calls
    assert ("end_scissor",) in canvas.calls


def test_blend_nested(scope):
    draw, canvas = scope
    with draw.blend(BlendMode.ADDITIVE):
        with draw.blend(BlendMode.MULTIPLIED):
            draw.rect((0, 0, 1, 1))
    assert any(c[0] == "blend" for c in canvas.calls)


def test_shader_and_texture_mode(scope):
    draw, canvas = scope
    shader = SimpleNamespace(id=1)
    target = SimpleNamespace(id=2)
    with draw.shader(shader):
        draw.line((0, 0), (1, 1))
    with draw.texture_mode(target):
        draw.texture(texture=SimpleNamespace(id=3), pos=(0, 0))
    assert ("shader", shader) in canvas.calls
    assert ("tex_begin", target) in canvas.calls
    assert ("tex_end",) in canvas.calls


def test_force_reset_all(scope):
    draw, canvas = scope
    draw.canvas.begin_blend_mode(1)
    draw._active_blend = 1
    draw.canvas.begin_scissor_mode(0, 0, 1, 1)
    draw._active_scissor = (0, 0, 1, 1)
    draw.canvas.begin_shader_mode("s")
    draw._active_shader = "s"
    draw.canvas.begin_texture_mode("t")
    draw._active_texture = "t"
    draw.canvas.begin_stencil_mask()
    draw._stencil_active = True
    draw.force_reset()
    assert draw._active_blend is None
    assert draw._active_scissor is None
    assert draw._active_shader is None
    assert draw._active_texture is None
    assert draw._stencil_active is False


def test_draw_scope_usable_without_immediate_flag():
    """The immediate-phase gate is gone — DrawScope is a canvas helper."""
    canvas = RecordingCanvas()
    renderer = SimpleNamespace(canvas=canvas)
    # pyrefly: ignore [bad-argument-type]
    draw = DrawScope(renderer)
    draw.circle(0, 0, 1)
    assert any(c[0] == "circle" for c in canvas.calls)
