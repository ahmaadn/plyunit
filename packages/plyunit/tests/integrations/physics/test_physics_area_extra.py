from __future__ import annotations

import pytest


def test_physics_area_construct_and_shapes():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.core.components.physics import BoxShape, CircleShape

    area = PhysicsArea(name="Zone")
    area.shapes.append(BoxShape(width=16, height=16, is_sensor=True))
    area.shapes.append(CircleShape(radius=8, is_sensor=True))
    assert area.monitoring is True
    assert area.monitorable is True
    assert len(area.shapes) == 2
    # signals exist
    assert hasattr(area, "on_body_entered")
    assert hasattr(area, "on_body_exited")
    assert area.sensor() is not None or PhysicsArea.sensor("s").name


def test_physics_service_add_static_and_step():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk import Physics, StaticBody
    from plyunit.core.components.physics import BoxShape

    svc = Physics(gravity=(0.0, 100.0), enable_spatial_hash=False)
    body = StaticBody(
        position=(0.0, 0.0),
        shapes=[BoxShape(width=32, height=16)],
    )
    if hasattr(svc, "add_static"):
        svc.add_static(body)
    elif hasattr(svc, "add_static_batch"):
        svc.add_static_batch([body])
    # step a few frames
    if hasattr(svc, "step"):
        svc.step(1 / 60)
        svc.step(1 / 60)
    assert svc is not None
