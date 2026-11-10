from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

import plyunit as pu
from plyunit.backends.physics.pymunk.debug_draw import PhysicsDebugDraw


class FakeRenderer:
    def __init__(self):
        self.primitives = []
        self.passes = []

    def create_pass(self, name, **kwargs):
        self.passes.append((name, kwargs))

    def render_custom(self, *, draw_func, **state):
        draw_func(self)

    def draw_circle(self, **kwargs):
        self.primitives.append(("circle", kwargs))

    def draw_rectangle(self, **kwargs):
        self.primitives.append(("rect", kwargs))

    def draw_line(self, **kwargs):
        self.primitives.append(("line", kwargs))


def test_debug_draw_visibility_and_camera():
    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    svc.add_static(
        pu.StaticBody(
            position=(0, 0),
            shapes=[
                pu.BoxShape(width=20, height=20),
                pu.CircleShape(radius=5),
                pu.SegmentShape(a=(-5, 0), b=(5, 0)),
                pu.PolygonShape(vertices=[(-3, -3), (3, -3), (0, 3)]),
            ],
        )
    )
    svc.add_static(
        pu.StaticBody(position=(1000, 1000), shapes=[pu.CircleShape(radius=7)])
    )
    handle = svc.create_body(
        position=(0, 0),
        shapes=[pu.BoxShape(width=10, height=10)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    svc.step(1 / 60)

    camera = SimpleNamespace(
        get_view_rect=lambda: (-100, -100, 100, 100),
        viewport=(0, 0, 200, 200),
    )
    registry = pu.UnitRegistry()
    registry.register(svc)

    class CameraApp(pu.Unit):
        def __init__(self):
            super().__init__(name="App", is_unique=True, register=False)
            self.camera = camera

    app = CameraApp()
    registry.register(app)
    node = pu.NodeUnit(name="debug-node")
    node.global_units = registry
    dbg = node.add_component(
        PhysicsDebugDraw(
            draw_bodies=True,
            draw_statics=True,
            draw_areas=True,
            draw_contacts=True,
            draw_aabb=True,
        )
    )
    dbg.on_start()
    renderer = FakeRenderer()
    dbg.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())

    assert renderer.passes[0][1]["camera"] is camera
    assert renderer.passes[0][1]["viewport_scissor"] == (0, 0, 200, 200)
    assert any(kind == "circle" for kind, _ in renderer.primitives)
    assert any(kind == "rect" for kind, _ in renderer.primitives)
    assert not any(
        kind == "circle" and payload["radius"] == 7
        for kind, payload in renderer.primitives
    )
    assert PhysicsDebugDraw._is_visible([], None) is True
    assert PhysicsDebugDraw._is_visible([], (-1, -1, 1, 1)) is False
    assert PhysicsDebugDraw._is_visible([pu.AABB(-10, -10, 10, 10)], (-5, -5, 5, 5))
    assert not PhysicsDebugDraw._is_visible([pu.AABB(10, 10, 20, 20)], (-5, -5, 5, 5))

    node.destroy_component(dbg)
    svc.destroy_body(handle)
    svc.clear_statics()


def test_debug_draw_start_requires_global_service():
    node = pu.NodeUnit(name="debug-node")
    node.global_units = pu.UnitRegistry()
    dbg = node.add_component(PhysicsDebugDraw())

    with pytest.raises(pu.NoResultFound, match="@Physics"):
        dbg.on_start()

    renderer = FakeRenderer()
    dbg.render_submit(cast(pu.Renderer, renderer), pu.RenderContext())
    assert renderer.passes == []
    assert renderer.primitives == []
    node.destroy_component(dbg)
