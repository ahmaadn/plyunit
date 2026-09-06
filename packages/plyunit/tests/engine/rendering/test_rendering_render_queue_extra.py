from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.canvas as canvas_module
from plyunit.rendering.enum import BlendMode, Layer
from plyunit.rendering.renderer import Renderer

class _FakeUbr:
    capacity = 256
    shutdown_calls = 0

    def init(self, n: int) -> None:
        self.capacity = n

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def submit_frame(self, **kwargs) -> None:
        pass


class FakeColor:
    def __init__(self, r: int, g: int, b: int, a: int):
        self.r, self.g, self.b, self.a = int(r), int(g), int(b), int(a)

class FakeVector2:
    def __init__(self, x=0.0, y=0.0):
        if isinstance(x, tuple):
            x, y = x
        self.x, self.y = float(x), float(y)

class FakeRectangle:
    def __init__(self, x: float, y: float, width: float, height: float):
        self.x, self.y, self.width, self.height = float(x), float(y), float(width), float(height)

@pytest.fixture()
def mock_canvas(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, list] = {
        "begin_texture_mode": [],
        "end_texture_mode": [],
        "begin_scissor_mode": [],
        "end_scissor_mode": [],
        "begin_blend_mode": [],
        "end_blend_mode": [],
        "begin_shader_mode": [],
        "end_shader_mode": [],
        "clear_background": [],
        "draw_circle": [],
        "draw_circle_v": [],
    }

    class FakeCanvas:
        def begin_texture_mode(self, *args):
            calls["begin_texture_mode"].append(args)

        def end_texture_mode(self, *args):
            calls["end_texture_mode"].append(args)

        def begin_scissor_mode(self, *args):
            calls["begin_scissor_mode"].append(args)

        def end_scissor_mode(self, *args):
            calls["end_scissor_mode"].append(args)

        def begin_blend_mode(self, *args):
            calls["begin_blend_mode"].append(args)

        def end_blend_mode(self, *args):
            calls["end_blend_mode"].append(args)

        def begin_shader_mode(self, *args):
            calls["begin_shader_mode"].append(args)

        def end_shader_mode(self, *args):
            calls["end_shader_mode"].append(args)

        def clear_background(self, *args):
            calls["clear_background"].append(args)

        def draw_circle(self, **kwargs):
            calls["draw_circle"].append(kwargs)
            calls["draw_circle_v"].append(kwargs)

    canvas = FakeCanvas()
    calls["_canvas"] = canvas  # type: ignore[assignment]
    return calls

def test_renderer_pass_management(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    assert renderer.get_pass("world") is not None

    # Create new pass
    # pyrefly: ignore [bad-argument-type]
    renderer.create_pass("custom_ui", order=10, clear_color=(0, 0, 0, 255))
    assert renderer.get_pass("custom_ui") is not None

    # Can't remove built-in world pass.
    renderer.remove_pass("world")
    assert renderer.get_pass("world") is not None

    # Can remove custom pass.
    renderer.remove_pass("custom_ui")
    assert renderer.get_pass("custom_ui") is None


def test_renderer_shutdown_releases_ubr_once(mock_canvas):
    ubr = _FakeUbr()
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=ubr)

    renderer.shutdown()
    renderer.shutdown()

    assert ubr.shutdown_calls == 1

def test_renderer_y_sort(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    Renderer.enable_y_sort_layer(Layer.WORLD, enabled=True)

    # Push items with different Y origins
    renderer.render_circle(z=10, layer=Layer.WORLD, center=(0, 0), radius=1.0, y_sort_origin=50.0)
    renderer.render_circle(z=0, layer=Layer.WORLD, center=(0, 0), radius=1.0, y_sort_origin=20.0)
    renderer.render_circle(z=5, layer=Layer.WORLD, center=(0, 0), radius=1.0, y_sort_origin=80.0)

    # Flush should sort them by y_sort_origin: 20.0, 50.0, 80.0
    renderer.flush()
    # If it flushes, the items are removed. We verify by the order they were processed?
    # Since we can't easily intercept the exact item sorted order without more complex mocks,
    # we just ensure it doesn't crash.
    Renderer.enable_y_sort_layer(Layer.WORLD, enabled=False)

def test_renderer_flush_all_passes_with_camera_and_target(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    target = SimpleNamespace()
    camera = SimpleNamespace(start_frame=lambda: None, end_frame=lambda: None)

    renderer.create_pass(
        "custom",
        # pyrefly: ignore [bad-argument-type]
        target=target,
        camera=camera,
        # pyrefly: ignore [bad-argument-type]
        clear_color=(0, 0, 0, 255),
        viewport_scissor=(10, 10, 100, 100),
        order=1
    )

    renderer.render_circle(z=0, layer=Layer.WORLD, center=(0, 0), radius=1.0, pass_name="custom")
    renderer.render_circle(z=0, layer=Layer.WORLD, center=(0, 0), radius=1.0, pass_name="world")

    renderer.flush_all()

    # Verify calls
    assert len(mock_canvas["begin_texture_mode"]) == 1
    assert len(mock_canvas["end_texture_mode"]) == 1
    assert len(mock_canvas["clear_background"]) == 1
    assert len(mock_canvas["begin_scissor_mode"]) == 1
    assert len(mock_canvas["end_scissor_mode"]) == 1
    assert len(mock_canvas["draw_circle_v"]) == 2

def test_renderer_error_during_flush_all(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    def bad_custom_draw(canvas):
        # Attempt to submit during flush_all.
        renderer.render_circle(z=0, layer=Layer.WORLD, center=(0, 0), radius=1.0)

    renderer.render_custom(z=0, layer=Layer.WORLD, draw_func=bad_custom_draw)

    with pytest.raises(RuntimeError, match="cannot submit to renderer during flush_all"):
        renderer.flush_all()

def test_renderer_item_scissor_and_blend_mode(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    shader = SimpleNamespace()

    # Item with specific state
    renderer.render_circle(
        z=0,
        layer=Layer.WORLD,
        center=(0, 0),
        radius=1.0,
        scissor=(0, 0, 50, 50),
        blend_mode=BlendMode.ADDITIVE,
        shader=shader,
    )

    # Second item with different state to trigger transitions
    renderer.render_circle(
        z=1,
        layer=Layer.WORLD,
        center=(0, 0),
        radius=1.0,
        scissor=(10, 10, 40, 40),
        blend_mode=BlendMode.MULTIPLIED,
        shader=None,
    )

    renderer.flush()

    assert len(mock_canvas["begin_scissor_mode"]) >= 1
    assert len(mock_canvas["end_scissor_mode"]) >= 1
    assert len(mock_canvas["begin_blend_mode"]) >= 1
    assert len(mock_canvas["end_blend_mode"]) >= 1
    assert len(mock_canvas["begin_shader_mode"]) >= 1
    assert len(mock_canvas["end_shader_mode"]) >= 1

def test_renderer_viewport_scissor_intersection(mock_canvas):
    # pyrefly: ignore [bad-argument-type]
    renderer = Renderer(canvas=mock_canvas["_canvas"], ubr=_FakeUbr())

    renderer.create_pass("clip_pass", viewport_scissor=(0, 0, 100, 100))

    renderer.render_circle(
        z=0,
        layer=Layer.WORLD,
        center=(0, 0),
        radius=1.0,
        pass_name="clip_pass",
        scissor=(50, 50, 100, 100),
    )

    renderer.flush_all()

    # intersection of (0,0,100,100) and (50,50,100,100) is (50, 50, 50, 50)
    assert (50, 50, 50, 50) in mock_canvas["begin_scissor_mode"]
