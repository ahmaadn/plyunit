from __future__ import annotations

import gc

import pytest

from plyunit.core.components.component import Component
from plyunit.core.components.component_registry import ComponentRegistry, components
from plyunit.core.units.node_unit import NodeUnit


class Health(Component):
    pass


class Armor(Component):
    pass


class HealthSubclass(Health):
    pass


@pytest.fixture(autouse=True)
def clear_registry():
    components.clear()
    yield
    components.clear()


def test_register_units_with_exact_type_only():
    a = NodeUnit(name="A")
    b = NodeUnit(name="B")
    a.add_component(Health())
    b.add_component(HealthSubclass())

    found = components.units_with(Health)
    assert a in found
    assert b not in found
    assert components.units_with(HealthSubclass) == [b]
    assert components.units_with(Armor) == []


def test_unregister_on_destroy_component():
    unit = NodeUnit(name="U")
    health = unit.add_component(Health())
    assert unit in components.units_with(Health)
    unit.destroy_component(health)
    assert components.units_with(Health) == []


def test_weak_refs_drop_dead_units():
    unit = NodeUnit(name="Temp")
    unit.add_component(Health())
    assert components.units_with(Health)
    del unit
    gc.collect()
    assert components.units_with(Health) == []


def test_registry_clear_and_local_instance():
    reg = ComponentRegistry()
    unit = NodeUnit(name="X")
    reg.register(unit, Health)
    assert reg.units_with(Health) == [unit]
    reg.unregister(unit, Health)
    assert reg.units_with(Health) == []
    reg.register(unit, Health)
    reg.clear()
    assert reg.units_with(Health) == []
