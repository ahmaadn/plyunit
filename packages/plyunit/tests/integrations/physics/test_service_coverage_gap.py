from __future__ import annotations

import pytest

import plyunit as pu


def test_physics_service_collision_and_query_paths():
    service = pu.Physics(gravity=(0.0, 900.0), enable_spatial_hash=False)
    floor = pu.StaticBody(
        position=(0.0, 200.0),
        shapes=[pu.BoxShape(width=400, height=20)],
        filter=pu.CollisionFilter.world_static(),
    )
    service.add_static(floor)
    handle = service.create_body(
        position=(0.0, 0.0),
        shapes=[pu.CircleShape(radius=8.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )
    for _ in range(120):
        service.step(1 / 60)

    state = service.get_body_state(handle)
    assert state is not None
    assert 181.0 <= state[1] <= 183.0
    assert list(service.iter_body_states())[0].handle == handle
    assert service.point_query(0.0, 200.0) == [floor]
    assert floor in service.area_query(pu.AABB(-200, 190, 200, 210))
    assert list(service.iter_contact_points())

    service.destroy_body_batch([handle])
    service.remove_static(floor.id)
    assert service.body_count == service.static_count == 0
    assert service.point_query(0.0, 200.0) == []


def test_physics_body_component_forces():
    service = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    registry = pu.UnitRegistry()
    registry.register(service)
    node = pu.NodeUnit(name="force-node")
    node.global_units = registry
    body = node.add_component(pu.PhysicsBody.dynamic(mass=2.0))
    body.add_shape(pu.CircleShape(radius=6))
    body.on_start()

    assert body._registered is True
    assert body.velocity == (0.0, 0.0)
    body.velocity = (50.0, -10.0)
    assert body.velocity == (50.0, -10.0)
    body.angular_velocity = 90.0
    assert body.angular_velocity == pytest.approx(90.0)
    body.angular_velocity = 0.0
    body.apply_impulse(20.0, 0.0)
    assert body.velocity == (60.0, -10.0)
    body.apply_force(100.0, 0.0)
    service.step(0.1)
    assert body.velocity == pytest.approx((65.0, -10.0))
    body.apply_impulse_at_point(0.0, 20.0, 10.0, 0.0)
    assert body.angular_velocity != 0.0
    body.apply_force_at_point(0.0, 100.0, 10.0, 0.0)
    service.step(0.1)
    assert not body.is_sleeping
    body.sleep()
    assert body.is_sleeping
    body.wake()
    assert not body.is_sleeping

    node.destroy_component(body)
    assert service.body_count == 0
    assert body._pm_body is None
    assert body._registered is False
