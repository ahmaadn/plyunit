from __future__ import annotations

import gc
import importlib
import math
import weakref

import pytest

import plyunit as pu


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    registry = pu.UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", registry
    )
    return registry


def test_physics_service_implements_neutral_port():
    service: pu.ports.IPhysics[pu.PhysicsBody, pu.PhysicsArea] = pu.Physics(
        enable_spatial_hash=False
    )
    handle = service.create_body(shapes=[pu.CircleShape(radius=4)])
    state = next(service.iter_body_states())
    assert state.handle == handle
    assert state.state() == (0.0, 0.0, 0.0)
    assert service.point_query(0, 0) == [state]
    assert service.query_aabb_fast(pu.AABB(-5, -5, 5, 5)) == [state]
    service.destroy_body(handle)
    assert service.body_count == 0


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
    pm_body = body._pm_body
    assert pm_body is not None
    assert node.transform.world.position == (pm_body.position.x, pm_body.position.y)
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

    assert service._space.iterations == 8
    assert math.isclose(service._space.damping, 0.9)

    service.configure_space(iterations=5, damping=0.8, collision_slop=0.2)

    assert service._space.iterations == 5
    assert math.isclose(service._space.damping, 0.8)
    assert math.isclose(service._space.collision_slop, 0.2)


def _component_node[C: pu.PhysicsBody | pu.PhysicsArea](
    service, component: C, position=(0.0, 0.0)
) -> tuple[pu.NodeUnit, C]:
    node = pu.NodeUnit(name=component.name)
    registry = pu.UnitRegistry()
    registry.register(service)
    node.global_units = registry
    node.transform.set_position(*position)
    node.add_component(component)
    component.add_shape(pu.CircleShape(radius=10))
    component.on_start()
    return node, component


@pytest.mark.parametrize("kind", ["body", "area"])
def test_registered_shape_changes_keep_unique_native_shapes(kind):
    service = pu.Physics(enable_spatial_hash=False)
    node, component = _component_node(
        service, pu.PhysicsBody.dynamic() if kind == "body" else pu.PhysicsArea()
    )
    records = service.iter_body_states if kind == "body" else service.iter_area_states
    record = next(records())
    retained_shape = component._pm_shapes[0]

    for _ in range(2):
        if isinstance(component, pu.PhysicsBody):
            service.sync_body_shapes(component)
        else:
            service.sync_area_shapes(component)
        assert component._pm_shapes is record.pm_shapes
        assert len(record.pm_shapes) == len(service._space.shapes) == 1
        assert len(list(record.shape_bounds)) == 1
    extra = component.add_shape(pu.BoxShape(width=4, height=8))
    assert len(record.pm_shapes) == len(service._space.shapes) == 2
    assert len({id(shape) for shape in record.pm_shapes}) == 2
    component.remove_shape(extra)
    assert len(record.pm_shapes) == len(service._space.shapes) == 1
    component.clear_shapes()
    assert record.pm_shapes == []
    assert list(record.shape_bounds) == []
    assert len(service._space.shapes) == 0
    component.add_shape(pu.CircleShape(radius=3))
    assert len(record.pm_shapes) == 1
    assert retained_shape.space is None

    handle = component._physics_handle
    assert handle is not None
    node.destroy_component(component)
    assert component._registered is False
    assert component._pm_body is None
    assert len(service._space.bodies) == len(service._space.shapes) == 0
    assert service.body_count == service.area_count == 0
    destroy = service.destroy_body if kind == "body" else service.destroy_area
    destroy(handle)


@pytest.mark.parametrize("kind", ["handle", "body", "area", "static"])
@pytest.mark.parametrize("valid_shapes_before_error", [0, 1])
def test_failed_shape_creation_leaves_no_native_or_query_ghosts(
    kind, valid_shapes_before_error
):
    service = pu.Physics(enable_spatial_hash=False)
    shapes: list[pu.PhysicsShape] = [
        pu.CircleShape(radius=4) for _ in range(valid_shapes_before_error)
    ]
    shapes.append(pu.PolygonShape(vertices=[(0, 0), (1, 0)]))
    node = pu.NodeUnit(name="invalid-shape-node")
    node.global_units = pu.UnitRegistry()
    node.global_units.register(service)

    static = None
    component = None
    if kind == "handle":
        create = lambda: service.create_body(shapes=shapes)
    elif kind == "static":
        static = pu.StaticBody(shapes=shapes)
        create = lambda: service.add_static(static)
    else:
        component = node.add_component(
            pu.PhysicsBody.dynamic() if kind == "body" else pu.PhysicsArea()
        )
        for shape in shapes:
            component.add_shape(shape)
        create = component.on_start

    with pytest.raises(ValueError, match="at least 3 vertices"):
        create()

    assert service.body_count == service.area_count == service.static_count == 0
    assert len(service._space.bodies) == len(service._space.shapes) == 0
    assert service._body_handle_to_index == {}
    assert service._area_handle_to_index == {}
    assert service.point_query(0, 0) == []
    assert service.area_query(pu.AABB(-10, -10, 10, 10)) == []
    assert service.query_aabb_fast(pu.AABB(-10, -10, 10, 10)) == []

    if kind == "handle":
        handle = service.create_body(shapes=[pu.CircleShape(radius=4)])
        assert service.get_position(handle) == (0.0, 0.0)
        service.destroy_body(handle)
    elif kind == "static":
        assert static is not None
        static.shapes = [pu.CircleShape(radius=4)]
        service.add_static(static)
        assert service.point_query(0, 0) == [static]
        service.remove_static(static.id)
    else:
        assert component is not None
        assert component._registered is False
        assert component._pm_body is None
        component.clear_shapes()
        component.add_shape(pu.CircleShape(radius=4))
        component.on_start()
        assert service.point_query(0, 0) == [component]
        node.destroy_component(component)
    assert len(service._space.bodies) == len(service._space.shapes) == 0


def test_fixed_rotation_survives_shape_resync():
    service = pu.Physics(enable_spatial_hash=False)
    node = pu.NodeUnit(name="fixed-body-node")
    node.global_units = pu.UnitRegistry()
    node.global_units.register(service)
    body = node.add_component(pu.PhysicsBody.dynamic())
    body.fixed_rotation = True
    body.add_shape(pu.CircleShape(radius=4))
    body.on_start()
    body.add_shape(pu.BoxShape(width=8, height=4))
    pm_body = body._pm_body
    assert pm_body is not None
    assert math.isinf(pm_body.moment)
    body.apply_impulse_at_point(0, 10, 10, 0)
    service.step(0.1)
    assert body.angular_velocity == 0.0
    assert node.transform.world.rotation == 0.0
    node.destroy_component(body)


@pytest.mark.parametrize("rotation", [0.0, 90.0, 180.0])
@pytest.mark.parametrize("gravity_scale", [0.0, 0.5, 1.0, 2.0])
def test_gravity_scale_is_independent_of_body_rotation(rotation, gravity_scale):
    service = pu.Physics(gravity=(20.0, 100.0), enable_spatial_hash=False)
    handle = service.create_body(
        rotation=rotation,
        mass=2.0,
        gravity_scale=gravity_scale,
        shapes=[pu.CircleShape(radius=4)],
    )
    record = next(service.iter_body_states())
    service.step(0.1)
    assert tuple(record.pm_body.velocity) == pytest.approx(
        (2.0 * gravity_scale, 10.0 * gravity_scale), abs=1e-8
    )
    assert record.pm_body.angular_velocity == pytest.approx(0.0)
    service.destroy_body(handle)


@pytest.mark.parametrize("enable_spatial_hash", [False, True])
def test_ray_cast_keeps_nearest_shape_hit_per_body(enable_spatial_hash):
    service = pu.Physics(enable_spatial_hash=enable_spatial_hash)
    handle = service.create_body(
        shapes=[
            pu.CircleShape(radius=11, offset=(-3, 3)),
            pu.CircleShape(radius=28, offset=(15, -2)),
        ]
    )
    static = pu.StaticBody(position=(60, 0), shapes=[pu.CircleShape(radius=4)])
    service.add_static(static)
    record = next(service.iter_body_states())
    start, end = (-70, 0), (70, 0)
    native_hits = service._space.segment_query(start, end, 0, service._pm_filter(None))
    closest = min(
        (hit for hit in native_hits if hit.shape.body is record.pm_body),
        key=lambda hit: hit.alpha,
    )
    hits = service.ray_cast(start, end)
    assert len(hits) == 2
    assert hits[0][0] is record
    assert hits[0][1] == pytest.approx(closest.alpha)
    assert hits[0][2] == pytest.approx(tuple(closest.normal))
    assert hits[1][0] is static
    assert hits[0][1] < hits[1][1]
    service.destroy_body(handle)
    service.remove_static(static.id)


@pytest.mark.parametrize("enable_spatial_hash", [False, True])
def test_teleport_reindexes_bounds_and_queries_without_stepping(enable_spatial_hash):
    service = pu.Physics(enable_spatial_hash=enable_spatial_hash)
    handle = service.create_body(shapes=[pu.BoxShape(width=20, height=4)])
    record = next(service.iter_body_states())
    service.set_body_state(handle, position=(100, 0), rotation=90)
    assert record.state() == (100.0, 0.0, 90.0)
    assert record.interpolated(0.5) == record.state()
    bounds = next(iter(record.shape_bounds))
    assert (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y) == pytest.approx((
        98.0,
        -10.0,
        102.0,
        10.0,
    ))
    assert service.point_query(0, 0) == []
    assert service.point_query(100, 8) == [record]
    assert service.area_query(pu.AABB(97, 7, 103, 9)) == [record]
    assert service.query_aabb_fast(pu.AABB(97, 7, 103, 9)) == [record]
    assert service.ray_cast((90, 8), (110, 8))[0][0] is record
    service.destroy_body(handle)


def test_nested_collision_exit_destruction_preserves_surviving_body_handle():
    service = pu.Physics(enable_spatial_hash=False)
    node_b, body_b = _component_node(service, pu.PhysicsBody.dynamic())
    node_c, body_c = _component_node(service, pu.PhysicsBody.dynamic(), (100, 0))
    node_a, body_a = _component_node(service, pu.PhysicsBody.dynamic(), (15, 0))
    handle_b, handle_c, handle_a = (
        body_b._physics_handle,
        body_c._physics_handle,
        body_a._physics_handle,
    )
    assert handle_b is not None
    assert handle_c is not None
    assert handle_a is not None
    exits = []

    def destroy_other(other):
        exits.append(other)
        service.destroy_body(handle_b)

    body_a.on_collision_exit.connect(destroy_other)
    service.step(1 / 60)
    assert service._active_collisions
    survivor_state = service.get_body_state(handle_c)
    service.destroy_body(handle_a)
    assert exits == [body_b]
    assert service.get_body_state(handle_a) is None
    assert service.get_body_state(handle_b) is None
    assert service.get_body_state(handle_c) == survivor_state
    assert service._body_handle_to_index == {handle_c: 0}
    assert service.body_count == len(service._space.bodies) == 1
    assert service._active_collisions == {}
    for node, component in ((node_a, body_a), (node_b, body_b), (node_c, body_c)):
        node.destroy_component(component)


def test_nested_overlap_exit_destruction_preserves_surviving_area_handle():
    service = pu.Physics(enable_spatial_hash=False)
    node_b, area_b = _component_node(service, pu.PhysicsArea(), (-100, 0))
    node_c, area_c = _component_node(service, pu.PhysicsArea(), (100, 0))
    node_a, area_a = _component_node(service, pu.PhysicsArea())
    node_body, body = _component_node(service, pu.PhysicsBody.dynamic())
    handle_b, handle_c, handle_a = (
        area_b._physics_handle,
        area_c._physics_handle,
        area_a._physics_handle,
    )
    assert handle_b is not None
    assert handle_c is not None
    assert handle_a is not None
    exits = []

    def destroy_other(other):
        exits.append(other)
        service.destroy_area(handle_b)

    area_a.on_body_exited.connect(destroy_other)
    service.step(1 / 60)
    assert area_a.get_overlapping_bodies() == [body]
    service.destroy_area(handle_a)
    assert exits == [body]
    assert [record.handle for record in service.iter_area_states()] == [handle_c]
    assert service._area_handle_to_index == {handle_c: 0}
    assert service.area_count == 1
    assert service._active_overlaps == {}
    for node, component in (
        (node_a, area_a),
        (node_b, area_b),
        (node_c, area_c),
        (node_body, body),
    ):
        node.destroy_component(component)
    assert len(service._space.bodies) == len(service._space.shapes) == 0


def test_physics_writeback_refreshes_the_indexed_node():
    service = pu.Physics(enable_spatial_hash=False)
    spatial = pu.SpatialIndex(cell_size=32)
    registry = pu.UnitRegistry()
    registry.register(service)
    registry.register(spatial)
    service.global_units = registry
    node = pu.NodeUnit(name="indexed-body-node")
    node.global_units = registry
    body = node.add_component(pu.PhysicsBody.dynamic())
    body.add_shape(pu.CircleShape(radius=4))
    body.on_start()
    spatial.attach(node)
    assert spatial.query_aabb(-1, -1, 1, 1) == [node]
    body.velocity = (100, 0)
    service.step(1.0)
    assert node.transform.dirty is False
    assert spatial.query_aabb(-1, -1, 1, 1) == []
    assert spatial.query_aabb(99, -1, 101, 1) == [node]
    spatial.detach(node)
    node.destroy_component(body)


def test_physics_body_start_requires_global_service():
    node = pu.NodeUnit(name="body-node")
    node.global_units = pu.UnitRegistry()
    body = node.add_component(pu.PhysicsBody.dynamic())
    with pytest.raises(pu.NoResultFound, match="@Physics"):
        body.on_start()
    assert body._registered is False
    assert body._physics_service is None
    node.destroy_component(body)


@pytest.mark.parametrize("enable_spatial_hash", [False, True])
@pytest.mark.parametrize("change", ["position", "rotation", "both", "destroy"])
def test_callback_teleport_reindexes_after_space_unlocks(
    monkeypatch, enable_spatial_hash, change
):
    service = pu.Physics(enable_spatial_hash=enable_spatial_hash)
    static = pu.StaticBody(shapes=[pu.CircleShape(radius=10)])
    service.add_static(static)
    handle = service.create_body(
        position=(15, 0), shapes=[pu.BoxShape(width=20, height=4)]
    )
    record = next(service.iter_body_states())
    original_reindex = service._space.reindex_shapes_for_body
    reindexed = []

    def checked_reindex(body):
        assert service._space._locked is False
        reindexed.append(body)
        original_reindex(body)

    monkeypatch.setattr(service._space, "reindex_shapes_for_body", checked_reindex)
    calls = []

    def teleport(arbiter, space, data):
        if calls:
            return
        calls.append(True)
        assert space._locked is True
        if change in {"position", "both", "destroy"}:
            service.set_body_state(handle, position=(100, 0))
        if change in {"rotation", "both", "destroy"}:
            service.set_body_state(handle, rotation=90)
        if change == "destroy":
            service.destroy_body(handle)
        arbiter.process_collision = False

    service.add_pre_solve_handler(teleport)
    service.step(1 / 60)
    assert calls == [True]
    assert service._pending_reindexes == set()
    if change == "destroy":
        assert reindexed == []
        assert service.get_body_state(handle) is None
        assert len(service._space.bodies) == len(service._space.shapes) == 1
        assert service.point_query(100, 0) == []
    else:
        assert reindexed == [record.pm_body]
        point = (100, 8) if change == "both" else (100, 0)
        if change == "rotation":
            point = (15, 8)
        assert service.point_query(*point) == [record]
        assert service.query_aabb_fast(
            pu.AABB(point[0] - 1, point[1] - 1, point[0] + 1, point[1] + 1)
        ) == [record]
        service.destroy_body(handle)
    service.remove_static(static.id)


def test_collision_exit_teleport_reindexes_before_removal_returns(monkeypatch):
    service = pu.Physics(enable_spatial_hash=False)
    node_a, body_a = _component_node(service, pu.PhysicsBody.dynamic())
    node_b, body_b = _component_node(service, pu.PhysicsBody.dynamic(), (15, 0))
    handle = body_b._physics_handle
    assert handle is not None
    service.step(1 / 60)
    original_reindex = service._space.reindex_shapes_for_body

    def checked_reindex(body):
        assert service._space._locked is False
        original_reindex(body)

    monkeypatch.setattr(service._space, "reindex_shapes_for_body", checked_reindex)
    calls = []

    def teleport(other):
        calls.append(other)
        service.set_body_state(handle, position=(100, 0), rotation=90)

    body_a.on_collision_exit.connect(teleport)
    node_a.destroy_component(body_a)
    assert calls == [body_b]
    assert service._pending_reindexes == set()
    assert service.point_query(100, 0) == [body_b]
    node_b.destroy_component(body_b)


@pytest.mark.parametrize("kind", ["handle", "body", "area", "static"])
def test_callback_create_then_destroy_cancels_pending_native_additions(kind):
    service = pu.Physics(enable_spatial_hash=False)
    floor = pu.StaticBody(shapes=[pu.CircleShape(radius=10)])
    service.add_static(floor)
    handle = service.create_body(position=(15, 0), shapes=[pu.CircleShape(radius=10)])
    node = pu.NodeUnit(name="callback-object")
    node.global_units = pu.UnitRegistry()
    node.global_units.register(service)
    calls = []

    def create_destroy(arbiter, space, data):
        if calls:
            return
        calls.append(True)
        if kind == "handle":
            pending = service.create_body(
                position=(100, 0), shapes=[pu.CircleShape(radius=4)]
            )
            service.destroy_body(pending)
            assert service.get_body_state(pending) is None
        elif kind == "static":
            static = pu.StaticBody(position=(100, 0), shapes=[pu.CircleShape(radius=4)])
            service.add_static(static)
            service.remove_static(static.id)
        else:
            node.transform.set_position(100, 0)
            component = node.add_component(
                pu.PhysicsBody.dynamic() if kind == "body" else pu.PhysicsArea()
            )
            component.add_shape(pu.CircleShape(radius=4))
            component.on_start()
            node.destroy_component(component)
        assert len(space._add_later) == 0

    service.add_pre_solve_handler(create_destroy)
    service.step(1 / 60)
    assert calls == [True]
    assert service.body_count == service.static_count == 1
    assert service.area_count == 0
    assert len(service._space.bodies) == len(service._space.shapes) == 2
    assert service.point_query(100, 0) == []
    assert service.area_query(pu.AABB(95, -5, 105, 5)) == []
    assert service.query_aabb_fast(pu.AABB(95, -5, 105, 5)) == []
    service.destroy_body(handle)
    service.remove_static(floor.id)


@pytest.mark.parametrize("kind", ["handle", "body", "area", "static"])
def test_callback_failed_creation_rolls_back_pending_native_additions(kind):
    service = pu.Physics(enable_spatial_hash=False)
    floor = pu.StaticBody(shapes=[pu.CircleShape(radius=10)])
    service.add_static(floor)
    handle = service.create_body(position=(15, 0), shapes=[pu.CircleShape(radius=10)])
    node = pu.NodeUnit(name="invalid-callback-object")
    node.global_units = pu.UnitRegistry()
    node.global_units.register(service)
    calls = []

    def invalid_create(arbiter, space, data):
        if calls:
            return
        calls.append(True)
        shapes: list[pu.PhysicsShape] = [
            pu.CircleShape(radius=4),
            pu.PolygonShape(vertices=[(0, 0), (1, 0)]),
        ]
        with pytest.raises(ValueError, match="at least 3 vertices"):
            if kind == "handle":
                service.create_body(position=(100, 0), shapes=shapes)
            elif kind == "static":
                service.add_static(pu.StaticBody(position=(100, 0), shapes=shapes))
            else:
                node.transform.set_position(100, 0)
                component = node.add_component(
                    pu.PhysicsBody.dynamic() if kind == "body" else pu.PhysicsArea()
                )
                for shape in shapes:
                    component.add_shape(shape)
                component.on_start()
        assert len(space._add_later) == 0

    service.add_pre_solve_handler(invalid_create)
    service.step(1 / 60)
    assert calls == [True]
    assert service.body_count == service.static_count == 1
    assert service.area_count == 0
    assert len(service._space.bodies) == len(service._space.shapes) == 2
    assert service.point_query(100, 0) == []
    assert service.area_query(pu.AABB(95, -5, 105, 5)) == []
    node.destroy()
    service.destroy_body(handle)
    service.remove_static(floor.id)


def test_contact_iterator_copies_native_data_inside_arbiter_callback(monkeypatch):
    import pymunk

    service = pu.Physics(enable_spatial_hash=False)
    handles = []
    for x in (0, 100, 200):
        service.add_static(
            pu.StaticBody(position=(x, 0), shapes=[pu.CircleShape(radius=10)])
        )
        handles.append(
            service.create_body(
                position=(x + 15, 0), shapes=[pu.CircleShape(radius=10)]
            )
        )
    service.step(1 / 60)
    original_each_arbiter = pymunk.Body.each_arbiter
    original_shapes = pymunk.Arbiter.shapes.fget
    original_contacts = pymunk.Arbiter.contact_point_set.fget
    assert original_shapes is not None
    assert original_contacts is not None
    active_arbiters = set()

    def checked_shapes(arbiter):
        assert id(arbiter) in active_arbiters
        return original_shapes(arbiter)

    def checked_contacts(arbiter):
        assert id(arbiter) in active_arbiters
        return original_contacts(arbiter)

    def each_arbiter(body, callback, *args, **kwargs):
        def within_callback(arbiter):
            active_arbiters.add(id(arbiter))
            try:
                callback(arbiter, *args, **kwargs)
            finally:
                active_arbiters.remove(id(arbiter))

        original_each_arbiter(body, within_callback)

    monkeypatch.setattr(pymunk.Body, "each_arbiter", each_arbiter)
    monkeypatch.setattr(pymunk.Arbiter, "shapes", property(checked_shapes))
    monkeypatch.setattr(pymunk.Arbiter, "contact_point_set", property(checked_contacts))
    points = service.iter_contact_points()
    expected = list(service.iter_contact_points())
    first = next(points)
    snapshot = service.iter_contact_points()
    native_refs = [weakref.ref(shape) for shape in service._space.shapes]
    monkeypatch.setattr(pymunk.Arbiter, "shapes", property(original_shapes))
    monkeypatch.setattr(
        pymunk.Arbiter, "contact_point_set", property(original_contacts)
    )
    service.destroy_body_batch(handles)
    service.clear_statics()
    service.step(1 / 60)
    gc.collect()
    monkeypatch.setattr(pymunk.Arbiter, "shapes", property(checked_shapes))
    monkeypatch.setattr(pymunk.Arbiter, "contact_point_set", property(checked_contacts))

    assert any(ref() is None for ref in native_refs)
    assert [first, *points] == expected
    assert list(snapshot) == expected
    assert len(expected) == 3
    assert len(set(expected)) == 3
    assert list(service.iter_contact_points()) == []


@pytest.mark.parametrize("api", ["method", "property"])
@pytest.mark.parametrize("enable_spatial_hash", [False, True])
def test_enabling_gravity_wakes_sleeping_handle_and_component_bodies(
    api, enable_spatial_hash
):
    service = pu.Physics(gravity=(0, 0), enable_spatial_hash=enable_spatial_hash)
    handle = service.create_body(
        position=(100, 100), shapes=[pu.BoxShape(width=20, height=20)]
    )
    record = next(service.iter_body_states())
    node, body = _component_node(service, pu.PhysicsBody.dynamic(), (200, 100))
    for _ in range(60):
        service.step(1 / 60)
    assert record.is_sleeping
    assert body.is_sleeping
    assert record.state() == (100.0, 100.0, 0.0)
    assert node.transform.world.position == (200.0, 100.0)

    if api == "method":
        service.set_gravity(0, 900)
    else:
        service.gravity = (0, 900)
    assert not record.is_sleeping
    assert not body.is_sleeping
    for _ in range(30):
        service.step(1 / 60)

    assert not record.is_sleeping
    assert not body.is_sleeping
    assert record.y > 100
    assert node.transform.world.position[1] > 100
    assert record.pm_body.velocity.y > 0
    assert body.velocity[1] > 0
    node.destroy_component(body)
    service.destroy_body(handle)


@pytest.mark.parametrize("api", ["method", "property"])
def test_unchanged_gravity_does_not_wake_sleeping_bodies(api):
    service = pu.Physics(gravity=(0, 0), enable_spatial_hash=False)
    handles = [
        service.create_body(
            position=(x, 100), shapes=[pu.BoxShape(width=20, height=20)]
        )
        for x in (100, 200, 300)
    ]
    records = list(service.iter_body_states())
    for _ in range(60):
        service.step(1 / 60)
    assert all(record.is_sleeping for record in records)

    if api == "method":
        service.set_gravity(0, 0)
    else:
        service.gravity = (0, 0)
    assert all(record.is_sleeping for record in records)
    service.step(1 / 60)
    assert all(record.is_sleeping and record.y == 100 for record in records)
    service.destroy_body_batch(handles)


@pytest.mark.parametrize("scenario", ["configured_zero", "toggle", "reset", "external"])
@pytest.mark.parametrize("enable_spatial_hash", [False, True])
def test_physics_example_enables_gravity_for_sleeping_objects(
    scenario, enable_spatial_hash
):
    from examples.example_physics import (
        FallingBox,
        FallingCircle,
        PhysicsApp,
        PhysicsScene,
    )

    class DemoButtons(pu.ServiceUnit):
        def __init__(self, name):
            super().__init__(name=name)
            self.pressed: set[str] = set()

        def is_pressed(self, action):
            return action in self.pressed

    app = PhysicsApp()
    service = pu.Physics(
        gravity=(0, 0) if scenario == "configured_zero" else (0, 900),
        enable_spatial_hash=enable_spatial_hash,
    )
    keyboard = DemoButtons("Input")
    DemoButtons("Mouse")
    app.scene_manager = pu.SceneManager()
    app.scene_manager.push(PhysicsScene())
    app.scene_manager.apply_pending()

    def press(action):
        keyboard.pressed.add(action)
        try:
            app._fixed_step(1 / 60, 0)
        finally:
            keyboard.pressed.clear()

    try:
        if scenario in {"toggle", "reset"}:
            press("toggle_gravity")
        elif scenario == "external":
            service.set_gravity(0, 0)
        if scenario == "reset":
            previous = app.scene_manager.current
            press("reset")
            assert app.scene_manager.current is not previous
        assert service.gravity == (0, 0)

        scene = app.scene_manager.current
        assert isinstance(scene, PhysicsScene)
        box_node = pu.NodeUnit(name="sleeping-box")
        box = box_node.add_component(FallingBox(100, 200))
        scene.root.attach(box_node)
        circle_node = pu.NodeUnit(name="sleeping-circle")
        circle = circle_node.add_component(FallingCircle(700, 200))
        scene.root.attach(circle_node)
        for _ in range(60):
            app._fixed_step(1 / 60, 0)
        assert box.physics.is_sleeping
        assert circle.physics.is_sleeping
        assert box_node.transform.world.position == (100.0, 200.0)
        assert circle_node.transform.world.position == (700.0, 200.0)

        press("toggle_gravity")
        assert service.gravity == (0, 900)
        for _ in range(30):
            app._fixed_step(1 / 60, 0)
        assert not box.physics.is_sleeping
        assert not circle.physics.is_sleeping
        assert box_node.transform.world.position[1] > 200
        assert circle_node.transform.world.position[1] > 200
        assert box.physics.velocity[1] > 0
        assert circle.physics.velocity[1] > 0
        press("toggle_gravity")
        assert service.gravity == (0, 0)
    finally:
        app.shutdown()
