from __future__ import annotations

import pytest


def test_physics_service_static_and_query():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    s = pu.StaticBody(
        position=(100.0, 100.0),
        shapes=[pu.BoxShape(width=40, height=20)],
    )
    svc.add_static(s)
    svc.add_static_batch(
        [
            pu.StaticBody(
                position=(200.0, 200.0),
                shapes=[pu.CircleShape(radius=10.0)],
            )
        ]
    )
    h = svc.create_body(
        position=(0.0, 0.0),
        shapes=[pu.CircleShape(radius=5.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    svc.step(1 / 60)
    state = svc.get_body_state(h)
    assert state is not None
    assert svc.body_count >= 1
    svc.remove_static(s.id)
    svc.destroy_body(h)


def test_physics_service_configure_and_step():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 500.0), enable_spatial_hash=True)
    handles = []
    for i in range(3):
        h = svc.create_body(
            position=(i * 10.0, 0.0),
            shapes=[pu.CircleShape(radius=3.0)],
            filter=pu.CollisionFilter.dynamic_actor(),
        )
        handles.append(h)
    svc.configure_space(iterations=4, damping=0.95)
    svc.step(0.016)
    for h in handles:
        svc.destroy_body(h)


def test_physics_area_register_via_service():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    registry = pu.UnitRegistry()
    registry.register(svc)
    node = pu.NodeUnit(name="area-node")
    node.global_units = registry
    node.units = registry
    area = node.add_component(PhysicsArea(name="z"))
    area.add_shape(pu.BoxShape(width=20, height=20))
    area.on_start()
    assert area._physics_service is not None or area._registered
    area.on_destroy()
