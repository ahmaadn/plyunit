from __future__ import annotations

import pytest


class HashableBody:
    def __init__(self, i: int) -> None:
        self.i = i

    def __hash__(self) -> int:
        return self.i

    def __eq__(self, other) -> bool:
        return isinstance(other, HashableBody) and other.i == self.i


def test_physics_area_shapes_and_overlap_api():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea
    from plyunit.core.components.physics import BoxShape, CircleShape

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

    body = HashableBody(1)
    area2 = PhysicsArea(name="B")
    # pyrefly: ignore [bad-argument-type]
    area._on_body_enter(body)
    assert area.has_overlapping_bodies()
    # pyrefly: ignore [bad-argument-type]
    area._on_body_enter(body)
    # pyrefly: ignore [bad-argument-type]
    area._on_body_exit(body)
    assert not area.has_overlapping_bodies()

    area._on_area_enter(area2)
    assert area.has_overlapping_areas()
    area._on_area_enter(area)
    area._on_area_exit(area2)
    assert not area.has_overlapping_areas()

    area.monitoring = False
    # pyrefly: ignore [bad-argument-type]
    area._on_body_enter(body)
    assert not area.has_overlapping_bodies()
    area._on_area_enter(area2)
    assert not area.has_overlapping_areas()

    area.on_destroy()
    area.destroy()


def test_physics_area_lifecycle_without_service(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("pymunk")
    from plyunit.core.units import unit as unit_module
    from plyunit.core.units.node_unit import NodeUnit
    from plyunit.core.units.unit_registry import UnitRegistry
    from plyunit.backends.physics.pymunk.physics_area import PhysicsArea

    # Isolate global registry so leftover Physics singletons from other
    # tests cannot make one_or_none("@Physics") raise MultipleResultsFound.
    registry = UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)

    node = NodeUnit(name="n")
    node.global_units = registry
    area = PhysicsArea(name="zone")
    node.add_component(area)
    area.on_start()
    area.on_destroy()
