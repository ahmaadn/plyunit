from __future__ import annotations

import math

import plyunit as pu


def test_handle_body_steps_without_nodeunit() -> None:
    service = pu.Physics(gravity=(0.0, 100.0), enable_spatial_hash=False)
    handle = service.create_body(
        position=(10.0, 20.0),
        shapes=[pu.CircleShape(radius=4.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
    )

    service.step(1.0 / 30.0)
    service.step(1.0 / 30.0)

    state = service.get_body_state(handle)
    assert state is not None
    assert state[1] > 20.0
    assert service.body_count == 1

    service.destroy_body(handle)
    assert service.body_count == 0


def test_component_body_registers_and_syncs_owner_node() -> None:
    service = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    node = pu.NodeUnit(name="body-node")
    registry = pu.UnitRegistry()
    registry.register(service)
    node.global_units = registry
    node.units = registry
    node.transform.set_position(5.0, 6.0)
    body = node.add_component(pu.PhysicsBody.dynamic())
    body.add_shape(pu.CircleShape(radius=6.0))

    body.on_start()
    assert body._registered is True
    assert service.body_count == 1

    body.velocity = (30.0, 0.0)
    service.step(1.0)

    assert node.transform.local.position[0] > 5.0

    node.destroy_component(body)
    assert service.body_count == 0


def test_dynamic_body_updates_world_transform_after_step() -> None:
    service = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    node = pu.NodeUnit(name="body-node")
    registry = pu.UnitRegistry()
    registry.register(service)
    node.global_units = registry
    node.units = registry
    node.transform.set_position(5.0, 6.0)
    node.transform.recalc_world(parent_world=None)
    node.transform.reset_interpolation()
    body = node.add_component(pu.PhysicsBody.dynamic())
    body.add_shape(pu.CircleShape(radius=6.0))
    body.on_start()

    body.velocity = (30.0, 0.0)
    service.step(1.0)

    assert node.transform.dirty is False
    assert node.transform.world.position == (body._pm_body.position.x, body._pm_body.position.y)
    assert node.world_transform_lerp(1.0).position == node.transform.world.position

    node.destroy_component(body)


def test_collision_filter_helpers_default_dynamic_static() -> None:
    dynamic_filter = pu.CollisionFilter.dynamic_actor()
    static_filter = pu.CollisionFilter.world_static()
    dynamic_filter_2 = pu.CollisionFilter.dynamic_actor()

    assert dynamic_filter.can_collide_with(static_filter)
    assert not dynamic_filter.can_collide_with(dynamic_filter_2)
    assert pu.CollisionFilter.dynamic_actor(collide_with_dynamic=True).can_collide_with(
        dynamic_filter_2
    )


def test_runtime_space_configuration_applies_to_pymunk() -> None:
    service = pu.Physics(iterations=8, damping=0.9, enable_spatial_hash=False)

    assert service.backend.iterations == 8
    assert math.isclose(service.backend.damping, 0.9)

    service.configure_space(iterations=5, damping=0.8, collision_slop=0.2)

    assert service.backend.iterations == 5
    assert math.isclose(service.backend.damping, 0.8)
    assert math.isclose(service.backend.collision_slop, 0.2)
