from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.rendering.renderer as renderer_module
import plyunit.backends.integrations.raylib.drawing.canvas as canvas_module

unit_module = importlib.import_module("plyunit.core.units.unit")

class _FakeUbr:
    capacity = 256
    def init(self, n: int) -> None:
        self.capacity = n
    def shutdown(self) -> None:
        pass
    def submit_frame(self, **kwargs) -> None:
        pass


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


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


def test_canvas_draw_texture_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[tuple[object, ...]]] = {
        "draw_texture_v": [],
        "draw_texture_ex": [],
        "draw_texture_pro": [],
        "draw_texture_rec": [],
        "draw_texture_n_patch": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_texture_v=lambda *args: calls["draw_texture_v"].append(args),
        draw_texture_ex=lambda *args: calls["draw_texture_ex"].append(args),
        draw_texture_pro=lambda *args: calls["draw_texture_pro"].append(args),
        draw_texture_rec=lambda *args: calls["draw_texture_rec"].append(args),
        draw_texture_n_patch=lambda *args: calls["draw_texture_n_patch"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas_module._cache_color.clear()
    canvas = canvas_module

    texture = SimpleNamespace(width=16, height=8)

    # pyrefly: ignore [bad-argument-type]
    canvas.draw_texture(texture=texture, pos=(10.2, 20.9), tint=(1, 2, 3, 4))
    canvas.draw_texture(
        # pyrefly: ignore [bad-argument-type]
        texture=texture,
        pos=(2.0, 3.0),
        rotation=45.0,
        scale=2.0,
        tint=(5, 6, 7, 8),
    )
    canvas.draw_texture(
        # pyrefly: ignore [bad-argument-type]
        texture=texture,
        pos=(2.0, 3.0),
        source=(0.0, 0.0, 8.0, 4.0),
        dest=(1.0, 2.0, 8.0, 4.0),
        origin=(1.0, 2.0),
        rotation=10.0,
        tint=(5, 6, 7, 8),
    )
    canvas.draw_texture(
        # pyrefly: ignore [bad-argument-type]
        texture=texture,
        pos=(2.0, 3.0),
        source=(0.0, 0.0, 8.0, 4.0),
        # pyrefly: ignore [bad-argument-type]
        dest=None,
        tint=(5, 6, 7, 8),
    )
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_texture(texture=None, pos=(0.0, 0.0))

    assert len(calls["draw_texture_v"]) == 1
    assert len(calls["draw_texture_ex"]) == 1
    # source without dest → pro; source+dest → pro (both use draw_texture_pro)
    assert len(calls["draw_texture_pro"]) >= 1
    assert len(calls["draw_texture_n_patch"]) == 0


def test_canvas_primitives_and_color_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, list[tuple[object, ...]]] = {
        "draw_rectangle_rec": [],
        "draw_rectangle_pro": [],
        "draw_circle_v": [],
        "draw_line_ex": [],
        "draw_line_bezier": [],
        "draw_text_ex": [],
        "draw_text_codepoints": [],
        "draw_text": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_rectangle_rec=lambda *args: calls["draw_rectangle_rec"].append(args),
        draw_rectangle_pro=lambda *args: calls["draw_rectangle_pro"].append(args),
        draw_circle_v=lambda *args: calls["draw_circle_v"].append(args),
        draw_line_ex=lambda *args: calls["draw_line_ex"].append(args),
        draw_line_bezier=lambda *args: calls["draw_line_bezier"].append(args),
        draw_text_ex=lambda *args: calls["draw_text_ex"].append(args),
        draw_text_codepoints=lambda *args: calls["draw_text_codepoints"].append(args),
        draw_text=lambda *args: calls["draw_text"].append(args),
        get_font_default=lambda: "font",
        gui_get_font=lambda: "font",
        rl_push_matrix=lambda: None,
        rl_pop_matrix=lambda: None,
        rl_translatef=lambda *args: None,
        rl_rotatef=lambda *args: None,
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas_module._cache_color.clear()
    canvas = canvas_module

    canvas.draw_rectangle(rect=(1.0, 2.0, 3.0, 4.0), color=(255, 0, 0, 255))
    canvas.draw_rectangle(
        rect=(1.0, 2.0, 3.0, 4.0), color=(255, 0, 0, 255), rotation=10.0
    )

    canvas.draw_circle(center=(10.0, 11.0), radius=12.0, color=(0, 255, 0, 255))

    canvas.draw_line(
        start=(1.0, 1.0),
        end=(2.0, 2.0),
        color=(10, 10, 10, 255),
        thickness=2.0,
    )
    canvas.draw_line(
        start=(3.0, 3.0),
        end=(4.0, 4.0),
        color=(11, 11, 11, 255),
        thickness=9.0,
        bezier=True,
    )

    canvas.draw_text(
        text="hello",
        pos=(5.0, 6.0),
        font_size=20,
        color=(1, 1, 1, 255),
        # pyrefly: ignore [bad-argument-type]
        font="font",
        spacing=2.0,
    )
    canvas.draw_text(
        text="fallback",
        pos=(7.0, 8.0),
        font_size=18,
        color=(2, 2, 2, 255),
    )
    canvas.draw_text(
        text="ignored",
        pos=(9.0, 10.0),
        font_size=16,
        color=(3, 3, 3, 255),
        codepoints=[65, 66],
        # pyrefly: ignore [bad-argument-type]
        font="font",
    )

    first_color = canvas.color((3, 4, 5, 6))
    second_color = canvas.color((3, 4, 5, 6))
    assert first_color is second_color

    assert isinstance(canvas.rgb(1, 2, 3), FakeColor)
    assert isinstance(canvas.rgba(1, 2, 3, 4), FakeColor)
    assert isinstance(canvas_module.color((5, 6, 7, 8)), FakeColor)
    assert isinstance(canvas_module.rgb(5, 6, 7), FakeColor)
    assert isinstance(canvas_module.rgba(5, 6, 7, 8), FakeColor)

    assert canvas.draw_rectangle is not None

    assert len(calls["draw_rectangle_rec"]) == 2
    assert len(calls["draw_rectangle_pro"]) == 0
    assert len(calls["draw_circle_v"]) == 1
    assert len(calls["draw_line_ex"]) == 1
    assert len(calls["draw_line_bezier"]) == 1
    assert len(calls["draw_text_ex"]) == 2
    assert len(calls["draw_text_codepoints"]) == 1


def test_canvas_module_is_canvas_backend() -> None:
    canvas_module._cache_color.clear()
    assert canvas_module.draw_texture is not None
    assert hasattr(canvas_module, "_cache_color")


def test_renderer_flush_orders_by_layer_and_z(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    calls: list[str] = []

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_circle_v=lambda *args: calls.append("circle"),
        # draw_text=lambda *args: calls.append("text"),
        draw_rectangle_rec=lambda *args: calls.append("rectangle"),
        get_font_default=lambda: "font",
        gui_get_font=lambda: "font",
        draw_text_ex=lambda *args: calls.append("text_ex"),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)

    # pyrefly: ignore [bad-argument-type]
    renderer = renderer_module.Renderer(canvas=canvas_module, ubr=_FakeUbr())

    renderer.render_text(
        z=1,
        layer=renderer_module.Layer.WORLD,
        text="HP",
        pos=(1.0, 2.0),
        font_size=14,
        color=(255, 255, 255, 255),
    )
    renderer.render_circle(
        z=0,
        layer=renderer_module.Layer.WORLD,
        center=(0.0, 0.0),
        radius=2.0,
        color=(1, 1, 1, 255),
    )

    def custom_draw(canvas):
        calls.append("custom")
        assert canvas is canvas_module

    renderer.render_custom(
        z=0,
        layer=renderer_module.Layer.UI,
        draw_func=custom_draw,
    )
    renderer.render_rect(
        z=2,
        layer=renderer_module.Layer.UI,
        rect=(0.0, 0.0, 1.0, 1.0),
        color=(2, 2, 2, 255),
    )

    renderer.flush()

    assert calls == ["circle", "text_ex", "custom", "rectangle"]


def test_renderer_partial_flush_keeps_ui_layers_for_later(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    calls: list[str] = []

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_circle_v=lambda *args: calls.append("circle"),
        draw_rectangle_rec=lambda *args: calls.append("rectangle"),
        get_font_default=lambda: "font",
        gui_get_font=lambda: "font",
        draw_text_ex=lambda *args: calls.append("text_ex"),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)

    # pyrefly: ignore [bad-argument-type]
    renderer = renderer_module.Renderer(canvas=canvas_module, ubr=_FakeUbr())

    renderer.render_circle(
        z=0,
        layer=renderer_module.Layer.WORLD,
        center=(0.0, 0.0),
        radius=2.0,
        color=(1, 1, 1, 255),
    )
    renderer.render_text(
        z=1,
        layer=renderer_module.Layer.UI_WORLD,
        text="HP",
        pos=(1.0, 2.0),
        font_size=14,
        color=(255, 255, 255, 255),
    )
    renderer.render_custom(
        z=0,
        layer=renderer_module.Layer.UI,
        draw_func=lambda canvas: calls.append("custom"),
    )

    renderer.flush(max_layer=renderer_module.Layer.UI_WORLD)
    assert calls == ["circle", "text_ex"]

    renderer.flush(min_layer=renderer_module.Layer.UI)
    assert calls == ["circle", "text_ex", "custom"]


def test_renderer_missing_required_submit_argument_raises(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    # pyrefly: ignore [bad-argument-type]
    renderer = renderer_module.Renderer(canvas=canvas_module, ubr=_FakeUbr())

    with pytest.raises(TypeError):
        renderer.render_circle(z=0, layer=renderer_module.Layer.UI)  # type: ignore[call-arg]


def test_canvas_batch_draw_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[tuple[object, ...]]] = {
        "draw_rectangle_rec": [],
        "draw_circle_v": [],
        "draw_line_v": [],
        "draw_triangle": [],
    }

    fake_pr = SimpleNamespace(
        BLACK=(0, 0, 0, 255),
        WHITE=(255, 255, 255, 255),
        Color=FakeColor,
        Rectangle=FakeRectangle,
        Vector2=FakeVector2,
        draw_rectangle_rec=lambda *args: calls["draw_rectangle_rec"].append(args),
        draw_circle_v=lambda *args: calls["draw_circle_v"].append(args),
        draw_line_v=lambda *args: calls["draw_line_v"].append(args),
        draw_triangle=lambda *args: calls["draw_triangle"].append(args),
    )

    monkeypatch.setattr(canvas_module, "pr", fake_pr)
    canvas = canvas_module

    # Test rectangle batch
    canvas.draw_rectangle_batch(
        rects=[(0, 0, 10, 10), (10, 10, 20, 20)],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_rectangle_batch(rects=None, colors=None)

    # Test circle batch
    canvas.draw_circle_batch(
        centers=[(0, 0), (10, 10)],
        radii=[5.0, 10.0],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_circle_batch(centers=None, radii=None, colors=None)

    # Test line batch
    canvas.draw_line_batch(
        starts=[(0, 0), (5, 5)],
        ends=[(10, 10), (15, 15)],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_line_batch(starts=None, ends=None, colors=None)

    # Test triangle batch
    canvas.draw_triangle_batch(
        v1s=[(0, 0), (5, 5)],
        v2s=[(10, 0), (15, 5)],
        v3s=[(5, 10), (10, 15)],
        colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
    )
    # pyrefly: ignore [bad-argument-type]
    canvas.draw_triangle_batch(v1s=None, v2s=None, v3s=None, colors=None)

    assert len(calls["draw_rectangle_rec"]) == 2
    assert len(calls["draw_circle_v"]) == 2
    assert len(calls["draw_line_v"]) == 2
    assert len(calls["draw_triangle"]) == 2

