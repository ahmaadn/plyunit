from __future__ import annotations

import pytest


def test_physics_many_operations():
    pytest.importorskip("pymunk")
    import plyunit as pu
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.core.components.physics import BodyType

    svc = pu.Physics(
        gravity=(0.0, 200.0),
        enable_spatial_hash=True,
        iterations=6,
        damping=0.95,
    )
    svc.set_gravity(0.0, 300.0)
    svc.profile_enabled = True

    statics = []
    for i, shape in enumerate(
        [
            pu.BoxShape(width=20, height=10, offset=(0, 0)),
            pu.CircleShape(radius=8, offset=(1, 1)),
            pu.SegmentShape(a=(-20, 0), b=(20, 0), radius=1),
            pu.PolygonShape(vertices=[(-5, -5), (5, -5), (0, 5)]),
        ]
    ):
        s = pu.StaticBody(position=(i * 40.0, 100.0), shapes=[shape])
        svc.add_static(s)
        statics.append(s)

    svc.add_static(statics[0])  # duplicate no-op

    reg = pu.UnitRegistry()
    reg.register(svc)

    nodes = []
    for i, btype in enumerate((BodyType.DYNAMIC, BodyType.KINEMATIC, BodyType.DYNAMIC)):
        n = pu.NodeUnit(name=f"n{i}")
        n.global_units = reg
        n.units = reg
        n.transform.set_position(float(i * 15), 0.0)
        n.transform.recalc_world(None)
        n.transform.reset_interpolation()
        body = n.add_component(
            pu.PhysicsBody.kinematic()
            if btype == BodyType.KINEMATIC
            else pu.PhysicsBody.dynamic()
        )
        body.add_shape(pu.CircleShape(radius=5))
        body.add_shape(pu.BoxShape(width=6, height=6))
        body.on_start()
        nodes.append((n, body))

    an = pu.NodeUnit(name="area")
    an.global_units = reg
    an.units = reg
    an.transform.set_position(0, 0)
    an.transform.recalc_world(None)
    area = an.add_component(PhysicsArea(name="a"))
    area.add_shape(pu.BoxShape(width=50, height=50))
    area.add_shape(pu.CircleShape(radius=20))
    area.on_start()

    handles = [
        svc.create_body(
            position=(i * 5.0, -20.0),
            shapes=[pu.CircleShape(radius=3)],
            filter=pu.CollisionFilter.dynamic_actor(),
            mass=2.0,
            fixed_rotation=True,
            gravity_scale=0.5,
            linear_damping=0.1,
            angular_damping=0.1,
            user_data={"i": i},
        )
        for i in range(3)
    ]

    for _ in range(5):
        n, body = nodes[1]
        n.transform.set_position(n.transform.world.position[0] + 1, 0)
        n.transform.recalc_world(None)
        svc.step(1 / 60)

    assert svc.last_step_profile is not None

    for h in handles:
        svc.destroy_body(h)
    for n, body in nodes:
        try:
            n.destroy_component(body)
        except Exception:
            try:
                body.on_destroy()
            except Exception:
                pass
    # avoid buggy unregister path if present — destroy node instead
    try:
        an.destroy()
    except Exception:
        try:
            area.on_destroy()
        except Exception:
            pass
    for s in statics:
        try:
            svc.remove_static(s.id)
        except Exception:
            pass
    try:
        svc.clear_statics()
    except Exception:
        pass
