from __future__ import annotations

import math

import plyunit as pu
from plyunit.backends.physics.pymunk.debug_draw import _transform_point


class FakeRenderer:
    def __init__(self) -> None:
        self.passes = []
        self.primitives = []

    def create_pass(self, name: str, **kwargs) -> None:
        self.passes.append((name, kwargs))

    def render_circle(self, **kwargs) -> None:
        self.primitives.append(("circle", kwargs))

    def render_rect(self, **kwargs) -> None:
        self.primitives.append(("rect", kwargs))

    def render_line(self, **kwargs) -> None:
        self.primitives.append(("line", kwargs))


class FakeUnit:
    def __init__(self, service) -> None:
        self.service = service
        self.window = None

    def one_or_none(self, unit_ref, *, scope="mixed"):
        if unit_ref in {"@Physics", "Physics"}:
            return self.service
        if unit_ref == "@Window":
            return self.window
        return None


def test_physics_debug_draw_imports_from_public_modules() -> None:
    assert pu.PhysicsDebugDraw is not None


def test_transform_point_rotates_local_points() -> None:
    x, y = _transform_point(10.0, 20.0, 4.0, 2.0, 90.0)

    assert math.isclose(x, 8.0, abs_tol=1e-6)
    assert math.isclose(y, 24.0, abs_tol=1e-6)


def test_render_submit_accepts_context_and_uses_typed_debug_state() -> None:
    service = pu.Physics(gravity=(0.0, 0.0))
    service.add_static(
        pu.StaticBody(
            position=(10.0, 20.0),
            shapes=[pu.CircleShape(radius=5.0)],
        )
    )
    debug_draw = pu.PhysicsDebugDraw(draw_bodies=False, draw_areas=False)
    debug_draw.unit = FakeUnit(service)
    renderer = FakeRenderer()

    debug_draw.render_submit(renderer, object())

    assert renderer.passes
    pass_name, pass_kwargs = renderer.passes[0]
    assert pass_name == "physics_debug"
    assert pass_kwargs["min_layer"] == pu.Layer.DEBUG
    assert pass_kwargs["max_layer"] == pu.Layer.DEBUG
    assert pass_kwargs["screen_space"] is False
    assert renderer.primitives

    for _kind, payload in renderer.primitives:
        assert payload["pass_name"] == "physics_debug"
        assert payload["layer"] == pu.Layer.DEBUG
        assert payload["screen_space"] is False
        assert payload["blend_mode"] == pu.BlendMode.ALPHA


def test_debug_draw_interpolates_body_records_with_render_alpha() -> None:
    service = pu.Physics(gravity=(0.0, 0.0))
    handle = service.create_body(
        position=(0.0, 0.0),
        rotation=0.0,
        shapes=[pu.BoxShape(width=10.0, height=20.0)],
    )
    record = next(service.iter_body_states())
    record.prev_x = 0.0
    record.prev_y = 10.0
    record.prev_angle = 0.0
    record.x = 20.0
    record.y = 30.0
    record.angle = 90.0

    window = type("Window", (), {"alpha": 0.25})()
    unit = FakeUnit(service)
    unit.window = window

    debug_draw = pu.PhysicsDebugDraw(
        draw_statics=False,
        draw_areas=False,
        draw_contacts=False,
    )
    debug_draw.unit = unit
    renderer = FakeRenderer()

    debug_draw.render_submit(renderer, object())

    rect = next(payload for kind, payload in renderer.primitives if kind == "rect")
    assert rect["rect"] == (5.0, 15.0, 10.0, 20.0)
    assert rect["rotation"] == 22.5

    service.destroy_body(handle)
