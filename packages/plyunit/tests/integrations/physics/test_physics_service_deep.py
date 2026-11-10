from __future__ import annotations

import importlib
from typing import cast

import pytest

from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


def test_clear_statics_and_body_batch_info():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.services.physics import PhysicsBodyCreateInfo

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    for i in range(5):
        svc.add_static(
            pu.StaticBody(
                position=(i * 50.0, 0.0),
                shapes=[
                    pu.BoxShape(width=10, height=10),
                    pu.CircleShape(radius=5),
                    pu.SegmentShape(a=(-5, 0), b=(5, 0), radius=1),
                    pu.PolygonShape(vertices=[(-2, -2), (2, -2), (0, 2)]),
                ],
            )
        )
    assert len(svc._statics) == 5
    svc.clear_statics()
    assert len(svc._statics) == 0

    infos = [
        PhysicsBodyCreateInfo(
            position=(float(i), 0.0),
            shapes=[pu.CircleShape(radius=2.0)],
            filter=pu.CollisionFilter.dynamic_actor(),
        )
        for i in range(4)
    ]
    handles = svc.create_body_batch(infos)
    assert len(handles) == 4
    for h in handles:
        st = svc.get_body_state(h)
        assert st is not None
        svc.destroy_body(h)


def test_step_zero_and_profile():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 900.0), enable_spatial_hash=False)
    svc.profile_enabled = True
    h = svc.create_body(
        position=(0.0, 0.0),
        shapes=[pu.CircleShape(radius=4.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    svc.step(0.0)  # no-op
    svc.step(1 / 60)
    assert svc.last_step_profile is not None
    svc.destroy_body(h)


def test_pre_solve_handler_and_attach():
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    calls = []

    def handler(arbiter, space, data):
        calls.append((arbiter, space))

    svc.add_pre_solve_handler(handler)
    svc.add_static(pu.StaticBody(shapes=[pu.CircleShape(radius=10)]))
    handle = svc.create_body(position=(15, 0), shapes=[pu.CircleShape(radius=10)])
    app = pu.App()
    app.on_fixed_update.emit(1 / 60)
    assert calls
    assert all(space is svc._space for _, space in calls)

    mover = svc.create_body(position=(100, 0), shapes=[pu.CircleShape(radius=2)])
    svc.set_body_state(mover, velocity=(10, 0))
    svc._detach_from_app(app)
    before = svc.get_body_state(mover)
    app.on_fixed_update.emit(1.0)
    assert svc.get_body_state(mover) == before
    svc._attach_to_app(app)
    svc._attach_to_app(app)
    app.on_fixed_update.emit(1.0)
    assert svc.get_position(mover) == pytest.approx((110.0, 0.0))
    svc.destroy_body_batch([handle, mover])
    svc.clear_statics()
    app.destroy()


def test_debug_draw_statics_and_areas():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    svc.add_static(
        pu.StaticBody(
            position=(0.0, 0.0),
            shapes=[
                pu.BoxShape(width=20, height=10),
                pu.CircleShape(radius=8),
                pu.SegmentShape(a=(-10, 0), b=(10, 0)),
            ],
        )
    )
    registry = pu.UnitRegistry()
    registry.register(svc)
    node = pu.NodeUnit(name="a")
    node.global_units = registry
    node.units = registry
    area = node.add_component(PhysicsArea(name="area"))
    area.add_shape(pu.CircleShape(radius=12))
    area.on_start()

    class FakeRenderer:
        def __init__(self):
            self.primitives = []
            self.passes = []

        def create_pass(self, name, **kw):
            self.passes.append(name)

        def render_custom(self, *, draw_func, **state):
            draw_func(self)

        def draw_circle(self, **kw):
            self.primitives.append(("c", kw))

        def draw_rectangle(self, **kw):
            self.primitives.append(("r", kw))

        def draw_line(self, **kw):
            self.primitives.append(("l", kw))

    dbg = node.add_component(
        pu.PhysicsDebugDraw(
            draw_bodies=True, draw_statics=True, draw_areas=True, draw_contacts=True
        )
    )
    dbg.on_start()
    r = FakeRenderer()
    dbg.render_submit(cast(pu.Renderer, r), pu.RenderContext())
    assert "physics_debug" in r.passes
    assert any(
        kind == "c" and payload["radius"] == 12 for kind, payload in r.primitives
    )
    node.destroy_component(dbg)
    node.destroy_component(area)
    assert svc.area_count == 0
    svc.clear_statics()
