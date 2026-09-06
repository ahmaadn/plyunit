from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_debug_draw_visibility_and_camera():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.backends.physics.pymunk.debug_draw import PhysicsDebugDraw

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
    h = svc.create_body(
        position=(0, 0),
        shapes=[pu.BoxShape(width=10, height=10)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    svc.step(1 / 60)

    camera = SimpleNamespace(
        get_view_rect=lambda: (-100, -100, 100, 100),
        viewport=(0, 0, 200, 200),
    )

    class Unit:
        def one_or_none(self, ref, scope="mixed"):
            if "Physics" in str(ref):
                return svc
            if "Camera" in str(ref):
                return camera
            if "App" in str(ref):
                return SimpleNamespace(camera=camera)
            return None

        time = None

    class FakeRenderer:
        def __init__(self):
            self.primitives = []
            self.passes = []

        def create_pass(self, name, **kw):
            self.passes.append((name, kw))

        def render_circle(self, **kw):
            self.primitives.append(("c", kw))

        def render_rect(self, **kw):
            self.primitives.append(("r", kw))

        def render_line(self, **kw):
            self.primitives.append(("l", kw))

    dbg = PhysicsDebugDraw(
        draw_bodies=True,
        draw_statics=True,
        draw_areas=True,
        draw_contacts=True,
        draw_aabb=True,
    )
    # pyrefly: ignore [bad-assignment]
    dbg.unit = Unit()
    r = FakeRenderer()
    # pyrefly: ignore [bad-argument-type]
    dbg.render_submit(r, object())
    assert r.primitives or r.passes

    # visibility helper
    assert PhysicsDebugDraw._is_visible([], None) is True
    assert PhysicsDebugDraw._is_visible([], (-1, -1, 1, 1)) is False
    shape = SimpleNamespace(
        bb=SimpleNamespace(left=-10, right=10, top=-10, bottom=10)
    )
    assert PhysicsDebugDraw._is_visible([shape], (-5, -5, 5, 5)) is True

    svc.destroy_body(h)


def test_debug_draw_without_service():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.debug_draw import PhysicsDebugDraw

    class Unit:
        def one_or_none(self, *a, **k):
            return None

        time = None

    class FakeRenderer:
        def create_pass(self, *a, **k):
            pass

        def render_circle(self, **k):
            pass

        def render_rect(self, **k):
            pass

        def render_line(self, **k):
            pass

    dbg = PhysicsDebugDraw()
    # pyrefly: ignore [bad-assignment]
    dbg.unit = Unit()
    # pyrefly: ignore [bad-argument-type]
    dbg.render_submit(FakeRenderer(), object())
