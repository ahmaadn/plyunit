from __future__ import annotations

import pytest


def test_set_gravity_and_destroy_batch():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 100.0), enable_spatial_hash=False)
    svc.set_gravity(0.0, 500.0)
    handles = [
        svc.create_body(
            position=(float(i), 0.0),
            shapes=[pu.CircleShape(radius=3.0)],
            filter=pu.CollisionFilter.dynamic_actor(),
        )
        for i in range(5)
    ]
    if hasattr(svc, "destroy_body_batch"):
        svc.destroy_body_batch(handles)
    else:
        for h in handles:
            svc.destroy_body(h)
    assert svc.body_count == 0


def test_register_unregister_area_and_step():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    registry = pu.UnitRegistry()
    registry.register(svc)

    node = pu.NodeUnit(name="area-node")
    node.global_units = registry
    node.units = registry
    node.transform.set_position(50, 50)
    node.transform.recalc_world(None)

    area = node.add_component(PhysicsArea(name="zone"))
    area.add_shape(pu.BoxShape(width=30, height=30))
    area.add_shape(pu.CircleShape(radius=10))
    area.on_start()
    assert area._registered or area._physics_service is svc

    # dynamic body that might overlap
    h = svc.create_body(
        position=(50.0, 50.0),
        shapes=[pu.CircleShape(radius=5.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    for _ in range(3):
        svc.step(1 / 60)

    area.on_destroy()
    svc.destroy_body(h)


def test_kinematic_body_sync():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.core.components.physics import BodyType

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    registry = pu.UnitRegistry()
    registry.register(svc)
    node = pu.NodeUnit(name="kin")
    node.global_units = registry
    node.units = registry
    node.transform.set_position(0, 0)
    node.transform.recalc_world(None)
    node.transform.reset_interpolation()

    body = node.add_component(pu.PhysicsBody.kinematic())
    body.add_shape(pu.BoxShape(width=10, height=10))
    body.on_start()
    node.transform.set_position(40, 0)
    node.transform.recalc_world(None)
    svc.step(1 / 30)
    svc.step(1 / 30)
    node.destroy_component(body)


def test_static_segment_polygon_aabb():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    s1 = pu.StaticBody(
        position=(0, 0),
        shapes=[pu.SegmentShape(a=(-50, 0), b=(50, 0), radius=2)],
    )
    s2 = pu.StaticBody(
        position=(100, 100),
        shapes=[pu.PolygonShape(vertices=[(-10, -10), (10, -10), (0, 10)])],
    )
    svc.add_static(s1)
    svc.add_static(s2)
    svc.step(1 / 60)
    svc.remove_static(s1.id)
    svc.remove_static(s2.id)
