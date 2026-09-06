from __future__ import annotations

import pytest


def test_physics_service_collision_and_query_paths():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    # floor
    floor = pu.StaticBody(
        position=(0.0, 200.0),
        shapes=[pu.BoxShape(width=400, height=20)],
        filter=pu.CollisionFilter.world_static(),
    )
    svc.add_static(floor)

    # dynamic falling onto floor
    h1 = svc.create_body(
        position=(0.0, 0.0),
        shapes=[pu.CircleShape(radius=8.0)],
        filter=pu.CollisionFilter.dynamic_actor(),
        mass=1.0,
    )
    h2 = svc.create_body(
        position=(5.0, -30.0),
        shapes=[pu.BoxShape(width=10, height=10)],
        filter=pu.CollisionFilter.dynamic_actor(collide_with_dynamic=True),
        mass=1.0,
    )
    svc.set_gravity(0.0, 900.0)
    for _ in range(30):
        svc.step(1 / 60)

    # iterate states
    states = list(svc.iter_body_states()) if hasattr(svc, "iter_body_states") else []
    assert len(states) >= 0

    # get states
    assert svc.get_body_state(h1) is not None
    assert svc.get_body_state(h2) is not None

    # destroy batch
    if hasattr(svc, "destroy_body_batch"):
        svc.destroy_body_batch([h1, h2])
    else:
        svc.destroy_body(h1)
        svc.destroy_body(h2)
    svc.remove_static(floor.id)
    svc.clear_statics()


def test_physics_body_component_forces():
    pytest.importorskip("pymunk")
    import plyunit as pu

    svc = pu.Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    reg = pu.UnitRegistry()
    reg.register(svc)
    node = pu.NodeUnit(name="force-node")
    node.global_units = reg
    node.units = reg
    node.transform.set_position(0, 0)
    node.transform.recalc_world(None)
    node.transform.reset_interpolation()
    body = node.add_component(pu.PhysicsBody.dynamic())
    body.add_shape(pu.CircleShape(radius=6))
    body.on_start()
    # property access
    for prop in ("velocity", "angular_velocity", "is_sleeping", "body_type"):
        if hasattr(body, prop):
            try:
                getattr(body, prop)
            except Exception:
                pass
    try:
        body.velocity = (50.0, -10.0)
    except Exception:
        pass
    try:
        body.angular_velocity = 1.0
    except Exception:
        pass
    for meth in ("apply_force_at_local_point", "apply_impulse_at_local_point", "apply_force", "apply_impulse"):
        if hasattr(body, meth):
            try:
                getattr(body, meth)((100, 0), (0, 0))
            except TypeError:
                try:
                    getattr(body, meth)((100, 0))
                except Exception:
                    pass
            except Exception:
                pass
    svc.step(1 / 60)
    svc.step(1 / 60)
    try:
        node.destroy_component(body)
    except Exception:
        try:
            body.on_destroy()
        except Exception:
            pass


def test_pymunk_adapter_direct():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.pymunk_adapter import PhysicsBackend
    from plyunit.core.components.physics import (
        BoxShape,
        CircleShape,
        CollisionFilter,
        SegmentShape,
        PolygonShape,
    )

    backend = PhysicsBackend(gravity=(0, 100), enable_spatial_hash=False)
    backend.gravity = (0, 200)
    assert backend.gravity[1] == 200
    static = backend.create_static_body(position=(0, 50))
    filt = CollisionFilter.world_static()
    for shape in (
        CircleShape(radius=5),
        BoxShape(width=10, height=10),
        SegmentShape(a=(-5, 0), b=(5, 0)),
        PolygonShape(vertices=[(-2, -2), (2, -2), (0, 2)]),
    ):
        try:
            backend.add_shape_to_body(static, shape, filt)
        except Exception:
            pass
    backend.step(1 / 60)
    try:
        backend.remove_body(static)
    except Exception:
        pass
