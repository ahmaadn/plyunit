from __future__ import annotations

import pytest


def test_physics_area_shapes_and_overlap_api():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.backends.physics.pymunk.physics_body import PhysicsBody
    from plyunit.services.physics._types import BoxShape, CircleShape

    area = PhysicsArea(name="A")
    s1 = BoxShape(width=10, height=10)
    s2 = CircleShape(radius=5)
    area.add_shape(s1)
    assert s1.is_sensor is True
    assert s1 in area.shapes
    area.add_shape(s2)
    area.remove_shape(s1)
    assert s1 not in area.shapes
    area.clear_shapes()
    assert area.shapes == []

    assert area.get_overlapping_bodies() == []
    assert area.get_overlapping_areas() == []
    assert area.has_overlapping_bodies() is False
    assert area.has_overlapping_areas() is False

    body = PhysicsBody.dynamic()
    area2 = PhysicsArea(name="B")
    area._on_body_enter(body)
    assert area.has_overlapping_bodies()
    area._on_body_enter(body)
    area._on_body_exit(body)
    assert not area.has_overlapping_bodies()

    area._on_area_enter(area2)
    assert area.has_overlapping_areas()
    area._on_area_enter(area)
    area._on_area_exit(area2)
    assert not area.has_overlapping_areas()

    area.monitoring = False
    area._on_body_enter(body)
    assert not area.has_overlapping_bodies()
    area._on_area_enter(area2)
    assert not area.has_overlapping_areas()

    area.on_destroy()
    area.destroy()


def test_physics_area_start_requires_global_service():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.core.units.node_unit import NodeUnit
    from plyunit.core.units.unit_registry import NoResultFound, UnitRegistry

    node = NodeUnit(name="n")
    node.global_units = UnitRegistry()
    area = node.add_component(PhysicsArea(name="zone"))

    with pytest.raises(NoResultFound, match="@Physics"):
        area.on_start()

    assert area._registered is False
    assert area._physics_service is None
    node.destroy_component(area)
