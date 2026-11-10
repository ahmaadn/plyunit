from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from types import SimpleNamespace
from typing import cast

import pytest

import plyunit as pu
from plyunit.backends.physics.pymunk.debug_draw import _transform_point
from plyunit.backends.physics.pymunk.service import iter_shape_aabbs


class FakeRenderer:
    def __init__(self) -> None:
        self.passes = []
        self.primitives = []
        self.queued = []

    def create_pass(self, name: str, **kwargs) -> None:
        self.passes.append((name, kwargs))

    def render_custom(self, *, draw_func, **state) -> None:
        self.queued.append((draw_func, state))

    def flush(self) -> None:
        for draw_func, state in self.queued:
            self._state = state
            draw_func(self)
        self.queued.clear()

    def draw_circle(self, **kwargs) -> None:
        self.primitives.append(("circle", kwargs | self._state))

    def draw_rectangle(self, **kwargs) -> None:
        self.primitives.append(("rect", kwargs | self._state))

    def draw_line(self, **kwargs) -> None:
        self.primitives.append(("line", kwargs | self._state))


class FakeUnit(pu.NodeUnit):
    def __init__(self, service) -> None:
        super().__init__(name="debug-node")
        self.global_units = pu.UnitRegistry()
        self.global_units.register(service)
        self.window = None

    def one_or_none(self, unit_ref, *, scope: pu.QueryScope = "mixed"):
        if unit_ref == "@Window":
            return self.window
        return super().one_or_none(unit_ref, scope=scope)


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

    debug_draw.on_start()
    debug_draw.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())
    renderer.flush()

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

    debug_draw.on_start()
    debug_draw.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())
    renderer.flush()

    rect = next(payload for kind, payload in renderer.primitives if kind == "rect")
    assert rect["rect"] == (5.0, 15.0, 10.0, 20.0)
    assert rect["rotation"] == 22.5
    assert rect["outline_only"] is True

    service.destroy_body(handle)


def test_debug_callbacks_snapshot_each_shape_before_flush() -> None:
    shapes: list[pu.PhysicsShape] = [
        pu.CircleShape(radius=3, offset=(1, 2)),
        pu.CircleShape(radius=9, offset=(8, 7)),
        pu.PolygonShape(vertices=[(0, 0), (10, 0), (0, 10)]),
    ]
    debug = pu.PhysicsDebugDraw()
    renderer = FakeRenderer()
    debug._submit_shapes(
        cast(pu.Renderer, renderer),
        shapes,
        0,
        0,
        0,
        (50, 100, 150, 255),
        sensor_fill=False,
    )
    shapes.clear()
    renderer.flush()

    circles = [kw for kind, kw in renderer.primitives if kind == "circle"]
    assert [(kw["center"], kw["radius"]) for kw in circles] == [
        ((1, 2), 3),
        ((8, 7), 9),
    ]
    assert all(kw["outline_only"] for kw in circles)
    edges = [kw for kind, kw in renderer.primitives if kind == "line"][-3:]
    assert [(kw["start"], kw["end"]) for kw in edges] == [
        ((0, 0), (10, 0)),
        ((10, 0), (0, 10)),
        ((0, 10), (0, 0)),
    ]


@pytest.mark.parametrize("kind", ["body", "area", "static"])
@pytest.mark.parametrize(
    ("view_rect", "draw_aabb", "expected_reads", "visible"),
    [
        (None, False, 0, True),
        (None, True, 2, True),
        ((-10, -10, 100, 10), False, 1, True),
        ((-10, -10, 100, 10), True, 2, True),
        ((1000, 1000, 1010, 1010), False, 2, False),
        ((1000, 1000, 1010, 1010), True, 2, False),
    ],
)
def test_debug_bounds_are_lazy_and_reused(
    monkeypatch, kind, view_rect, draw_aabb, expected_reads, visible
):
    import pymunk

    service = pu.Physics(enable_spatial_hash=False)
    node = FakeUnit(service)
    shapes: list[pu.PhysicsShape] = [
        pu.CircleShape(radius=3),
        pu.CircleShape(radius=9, offset=(30, 0)),
    ]
    handle = None
    area = None
    if kind == "body":
        handle = service.create_body(shapes=shapes)
    elif kind == "area":
        area = node.add_component(pu.PhysicsArea())
        for shape in shapes:
            area.add_shape(shape)
        area.on_start()
    else:
        service.add_static(pu.StaticBody(shapes=shapes))

    debug = node.add_component(
        pu.PhysicsDebugDraw(draw_aabb=draw_aabb, draw_contacts=False)
    )
    debug.on_start()
    camera = (
        SimpleNamespace(get_view_rect=lambda: view_rect, viewport=(0, 0, 200, 200))
        if view_rect is not None
        else None
    )
    monkeypatch.setattr(debug, "_resolve_camera", lambda: camera)
    original_bb = pymunk.Shape.bb.fget
    assert original_bb is not None
    reads: Counter[int] = Counter()
    requests = []

    def counted_bb(shape):
        reads[id(shape)] += 1
        return original_bb(shape)

    def counted_bounds(pm_shapes) -> Iterable[pu.AABB]:
        requests.append(pm_shapes)
        return iter_shape_aabbs(pm_shapes)

    monkeypatch.setattr(pymunk.Shape, "bb", property(counted_bb))
    monkeypatch.setattr(
        "plyunit.backends.physics.pymunk.service.iter_shape_aabbs", counted_bounds
    )
    renderer = FakeRenderer()
    debug.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())
    renderer.flush()

    assert len(requests) == int(view_rect is not None or draw_aabb)
    assert sum(reads.values()) == expected_reads
    assert all(count == 1 for count in reads.values())
    circles = [payload for kind, payload in renderer.primitives if kind == "circle"]
    rectangles = [payload for kind, payload in renderer.primitives if kind == "rect"]
    assert len(circles) == (2 if visible else 0)
    assert len(rectangles) == (2 if visible and draw_aabb else 0)
    if rectangles:
        assert [payload["rect"] for payload in rectangles] == [
            (-3.0, -3.0, 6.0, 6.0),
            (21.0, -9.0, 18.0, 18.0),
        ]

    node.destroy_component(debug)
    if area is not None:
        node.destroy_component(area)
    if handle is not None:
        service.destroy_body(handle)
    service.clear_statics()


def test_debug_shape_cap_stops_remaining_static_bounds_requests(monkeypatch):
    service = pu.Physics(enable_spatial_hash=False)
    for x in (0, 20, 40):
        service.add_static(
            pu.StaticBody(position=(x, 0), shapes=[pu.CircleShape(radius=3)])
        )
    debug = pu.PhysicsDebugDraw(max_debug_shapes=1, draw_contacts=False)
    debug.unit = FakeUnit(service)
    debug.on_start()
    monkeypatch.setattr(debug, "_view_bb", lambda: (-100, -100, 100, 100))
    requests = []

    def counted_bounds(pm_shapes) -> Iterable[pu.AABB]:
        requests.append(pm_shapes)
        return iter_shape_aabbs(pm_shapes)

    monkeypatch.setattr(
        "plyunit.backends.physics.pymunk.service.iter_shape_aabbs", counted_bounds
    )
    renderer = FakeRenderer()
    debug.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())
    renderer.flush()
    assert len(requests) == 1
    assert sum(kind == "circle" for kind, _ in renderer.primitives) == 1
    service.clear_statics()
