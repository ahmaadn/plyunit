from __future__ import annotations

import pytest


def test_physics_area_construct_and_shapes():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.services.physics._types import BoxShape, CircleShape

    area = PhysicsArea(name="Zone")
    area.shapes.append(BoxShape(width=16, height=16, is_sensor=True))
    area.shapes.append(CircleShape(radius=8, is_sensor=True))
    assert area.monitoring is True
    assert area.monitorable is True
    assert len(area.shapes) == 2
    assert len(area.on_body_entered) == 0
    assert len(area.on_body_exited) == 0
    assert PhysicsArea.sensor("s").name == "s"


def test_physics_service_add_static_and_step():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk import Physics
    from plyunit.services.physics import BoxShape, StaticBody

    svc = Physics(gravity=(0.0, 100.0), enable_spatial_hash=False)
    body = StaticBody(
        position=(0.0, 0.0),
        shapes=[BoxShape(width=32, height=16)],
    )
    svc.add_static(body)
    svc.step(1 / 60)
    svc.step(1 / 60)

    assert svc.static_count == 1
    assert svc.get_statics() == [body]
    assert body.position == (0.0, 0.0)
    assert svc.point_query(0.0, 0.0) == [body]

    svc.remove_static(body.id)
    assert svc.static_count == 0
    assert svc.point_query(0.0, 0.0) == []
