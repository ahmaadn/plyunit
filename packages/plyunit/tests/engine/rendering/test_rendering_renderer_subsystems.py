from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as canvas_module
import plyunit.rendering.renderer as renderer_module
from plyunit.rendering.enum import BlendMode
from plyunit.rendering.render_state import RenderContext, RenderStateCache


class FakeVector2:
    def __init__(self, x=0.0, y=0.0):
        if isinstance(x, tuple):
            x, y = x
        self.x = float(x)
        self.y = float(y)


class FakeRectangle:
    def __init__(self, x=0.0, y=0.0, width=0.0, height=0.0):
        self.x = float(x)
        self.y = float(y)
        self.width = float(width)
        self.height = float(height)


class FakeColor:
    def __init__(self, r=0, g=0, b=0, a=255):
        self.r = int(r)
        self.g = int(g)
        self.b = int(b)
        self.a = int(a)


def test_render_context_and_state_cache_paths() -> None:
    context = RenderContext(layer=1, z=2.0)
    child = context.derive(layer=3, y_sort=True)

    assert context.layer == 1
    assert child.layer == 3
    assert child.y_sort is True

    cache = RenderStateCache()
    default_id = cache.intern()
    shader = SimpleNamespace(id=9)
    custom_id = cache.intern(
        # pyrefly: ignore [bad-argument-type]
        scissor=(1, 2, 3, 4), blend_mode=BlendMode.ADDITIVE, shader=shader
    )
    same_id = cache.intern(
        # pyrefly: ignore [bad-argument-type]
        scissor=(1, 2, 3, 4), blend_mode=BlendMode.ADDITIVE, shader=shader
    )

    assert default_id == 0
    assert custom_id == same_id
    assert cache.get(custom_id).shader is shader

    cache.clear()
    assert cache.intern() == 0


def test_renderer_typed_subsystems_submit_and_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        BLANK=(0, 0, 0, 0),
        Color=FakeColor,
        Vector2=FakeVector2,
        Rectangle=FakeRectangle,
        RL_QUADS=7,
        get_screen_width=lambda: 800,
        get_screen_height=lambda: 600,
        clear_background=lambda color: calls.append(("clear", color)),
        draw_rectangle_rec=lambda rect, color: calls.append(("rect", rect)),
        draw_texture_v=lambda texture, pos, tint: calls.append(("texture_batch", pos)),
        draw_circle_v=lambda center, radius, color: calls.append(("circle", radius)),
        draw_line_v=lambda start, end, color: calls.append(("line", start)),
        draw_triangle=lambda v1, v2, v3, color: calls.append(("tri", v1)),
        gui_get_font=lambda: "font",
        draw_text_ex=lambda *args: calls.append(("text", args[1])),
        begin_scissor_mode=lambda *args: calls.append(("scissor_begin", args)),
        end_scissor_mode=lambda: calls.append(("scissor_end", None)),
        begin_blend_mode=lambda mode: calls.append(("blend_begin", mode)),
        end_blend_mode=lambda: calls.append(("blend_end", None)),
        begin_shader_mode=lambda shader: calls.append(("shader_begin", shader)),
        end_shader_mode=lambda: calls.append(("shader_end", None)),
        begin_texture_mode=lambda target: calls.append(("target_begin", target)),
        end_texture_mode=lambda: calls.append(("target_end", None)),
    )
    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    monkeypatch.setitem(__import__("sys").modules, "pyray", fake_pr)

    class FakeUbr:
        capacity = 256

        def init(self, n: int) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def submit_frame(self, **kwargs) -> None:
            calls.append(("ubr_submit", kwargs.get("n_sprites")))

    class FakeCanvasMod:
        """Stand-in module-as-canvas used by draw_primitive."""

        @staticmethod
        def draw_rectangle(**kwargs):
            calls.append(("rect", kwargs.get("rect")))

        @staticmethod
        def draw_circle(**kwargs):
            calls.append(("circle", kwargs.get("radius")))

        @staticmethod
        def draw_line(**kwargs):
            calls.append(("line", kwargs.get("start")))

        @staticmethod
        def draw_triangle(**kwargs):
            calls.append(("tri", kwargs.get("v1")))

        @staticmethod
        def draw_text(**kwargs):
            calls.append(("text", kwargs.get("text")))

        @staticmethod
        def begin_scissor_mode(*args):
            calls.append(("scissor_begin", args))

        @staticmethod
        def end_scissor_mode():
            calls.append(("scissor_end", None))

        @staticmethod
        def begin_blend_mode(mode):
            calls.append(("blend_begin", mode))

        @staticmethod
        def end_blend_mode():
            calls.append(("blend_end", None))

        @staticmethod
        def begin_shader_mode(shader):
            calls.append(("shader_begin", shader))

        @staticmethod
        def end_shader_mode():
            calls.append(("shader_end", None))

        @staticmethod
        def begin_texture_mode(target):
            calls.append(("target_begin", target))

        @staticmethod
        def end_texture_mode():
            calls.append(("target_end", None))

        @staticmethod
        def clear_background(color):
            calls.append(("clear", color))

    renderer = renderer_module.Renderer(
        # pyrefly: ignore [bad-argument-type]
        canvas=FakeCanvasMod,
        ubr=FakeUbr(),
        max_sprites=256,
    )
    texture = SimpleNamespace(id=1, width=8, height=8)
    shader = SimpleNamespace(id=2)
    target = SimpleNamespace(texture=texture)
    camera = SimpleNamespace(
        viewport=(0, 0, 100, 100),
        start_frame=lambda: calls.append(("camera_begin", None)),
        end_frame=lambda: calls.append(("camera_end", None)),
        draw_letterbox=lambda: calls.append(("letterbox", None)),
    )

    # pyrefly: ignore [bad-argument-type]
    renderer.create_pass("target", target=target, clear_color=(1, 2, 3, 255), order=-1)
    # pyrefly: ignore [bad-argument-type]
    renderer.render_sprite(texture=texture, pos=(1.0, 2.0), pass_name="target")
    # pyrefly: ignore [bad-argument-type]
    renderer.render_batch(texture=texture, positions=[(8.0, 8.0), (9.0, 9.0)])
    renderer.render_sprite(texture=texture, pos=(3.0, 4.0))
    renderer.render_sprite(texture=texture, dest=(0.0, 0.0, 16.0, 16.0))
    renderer.render_rect(rect=(0, 0, 10, 10), color=(255, 0, 0, 255))
    renderer.render_circle(center=(4, 4), radius=2, color=(0, 255, 0, 255))
    renderer.render_line(start=(0, 0), end=(1, 1), color=(0, 0, 255, 255))
    renderer.render_triangle(v1=(0, 0), v2=(1, 0), v3=(0, 1), color=(255, 255, 0, 255))
    renderer.render_text(text="world", pos=(5, 5), layer=renderer_module.Layer.WORLD)
    renderer.render_custom(draw_func=lambda canvas: calls.append(("custom", canvas)))
    renderer.render_rect(
        rect=(2, 2, 3, 3),
        color=(255, 255, 255, 255),
        scissor=(5, 5, 20, 20),
        blend_mode=BlendMode.ADDITIVE,
        shader=shader,
    )

    renderer.flush_all(camera=camera)

    labels = [label for label, _ in calls]
    assert "target_begin" in labels
    assert "target_end" in labels
    assert "camera_begin" in labels
    assert "camera_end" in labels
    assert "letterbox" in labels
    assert "ubr_submit" in labels
    assert "rect" in labels
    assert "circle" in labels
    assert "line" in labels
    assert "tri" in labels
    assert "text" in labels
    assert "custom" in labels
    assert "blend_begin" in labels
    assert renderer._items == []
    assert renderer._frame_buffer.count == 0

    calls.clear()
    renderer.render_rect(rect=(0, 0, 2, 2), color=(255, 255, 255, 255))
    renderer.flush_all(camera=None)

    labels = [label for label, _ in calls]
    assert "camera_begin" not in labels
    assert "camera_end" not in labels
    assert "letterbox" not in labels
    assert renderer._render_passes["world"].camera is None
    assert renderer._render_passes["world"].viewport_scissor is None


def test_renderer_bulk_and_direct_alias_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUbr:
        capacity = 64

        def init(self, n: int) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def submit_frame(self, **kwargs) -> None:
            pass

    class FakeCanvasMod:
        @staticmethod
        def draw_rectangle(**kwargs):
            pass

        @staticmethod
        def draw_circle(**kwargs):
            pass

        @staticmethod
        def draw_line(**kwargs):
            pass

        @staticmethod
        def draw_triangle(**kwargs):
            pass

        @staticmethod
        def draw_text(**kwargs):
            pass

        @staticmethod
        def begin_scissor_mode(*a):
            pass

        @staticmethod
        def end_scissor_mode():
            pass

        @staticmethod
        def begin_blend_mode(m):
            pass

        @staticmethod
        def end_blend_mode():
            pass

        @staticmethod
        def begin_shader_mode(s):
            pass

        @staticmethod
        def end_shader_mode():
            pass

        @staticmethod
        def begin_texture_mode(t):
            pass

        @staticmethod
        def end_texture_mode():
            pass

        @staticmethod
        def clear_background(c):
            pass

    # pyrefly: ignore [bad-argument-type]
    renderer = renderer_module.Renderer(
        canvas=FakeCanvasMod, ubr=FakeUbr(), max_sprites=64
    )
    texture = SimpleNamespace(id=3, width=4, height=4)

    renderer.render_rects(rects=[(0, 0, 1, 1)], colors=[(1, 2, 3, 4)])
    renderer.render_circles(centers=[(0, 0)], radii=[1.0], colors=[(1, 2, 3, 4)])
    renderer.render_lines(starts=[(0, 0)], ends=[(1, 1)], colors=[(1, 2, 3, 4)])
    renderer.render_triangles(
        v1s=[(0, 0)], v2s=[(1, 0)], v3s=[(0, 1)], colors=[(1, 2, 3, 4)]
    )
    # pyrefly: ignore [bad-argument-type]
    renderer.render_batch(texture=texture, positions=[])
    renderer.render_sprite(texture=texture)
    renderer.render_sprite(texture=texture)

    assert len(renderer._items) == 4
    assert renderer._frame_buffer.count == 2
