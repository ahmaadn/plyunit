from __future__ import annotations

import importlib

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
    from plyunit.backends.physics.pymunk.service import PhysicsBodyCreateInfo

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
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    calls = []

    def handler(arbiter, space, data):
        calls.append(1)

    svc.add_pre_solve_handler(handler)

    class FakeApp:
        def __init__(self):
            self.on_fixed_update = pu.Signal("on_fixed_update")

    app = FakeApp()
    if hasattr(svc, "on_attach"):
        svc.on_attach(app)
        app.on_fixed_update.emit(1 / 60)
    svc.step(1 / 60)


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

        def render_circle(self, **kw):
            self.primitives.append(("c", kw))

        def render_rect(self, **kw):
            self.primitives.append(("r", kw))

        def render_line(self, **kw):
            self.primitives.append(("l", kw))

    dbg = pu.PhysicsDebugDraw(
        draw_bodies=True, draw_statics=True, draw_areas=True, draw_contacts=True
    )
    dbg.unit = type(
        "U",
        (),
        {
            "one_or_none": lambda self, ref, scope="mixed": svc
            if "Physics" in str(ref)
            else None,
            "time": None,
        },
    )()
    r = FakeRenderer()
    dbg.render_submit(r, object())
    assert r.passes or r.primitives
    area.on_destroy()
