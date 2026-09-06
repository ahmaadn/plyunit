from __future__ import annotations

import gc
import importlib
import weakref

import plyunit as pu
import pytest


def test_unit_group_find_tags():
    reg = pu.UnitRegistry()
    a = pu.ServiceUnit(name="A", tags={"alpha", "svc"})
    b = pu.ServiceUnit(name="B", tags={"beta", "svc"})
    reg.register(a)
    reg.register(b)

    svcs = reg.group(pu.ServiceUnit)
    assert len(svcs) >= 2

    if hasattr(reg, "find_by_tag"):
        tagged = reg.find_by_tag("svc")
        assert len(tagged) >= 2

    if a.is_unique:
        got = reg.one("@A")
        assert got is a


def test_node_unit_transform():
    root = pu.NodeUnit(name="root")
    root.transform.set_position(10, 20)
    root.transform.recalc_world(None)
    assert root.transform.world.position == (10.0, 20.0)
    root.destroy()


def test_registry_strongly_retains_until_remove():
    reg = pu.UnitRegistry()
    unit = pu.Unit(name="Owned")
    reg.register(unit)
    reference = weakref.ref(unit)
    del unit
    gc.collect()

    retained = reg.one("Owned")
    assert reference() is retained
    reg.remove(retained)
    del retained
    gc.collect()
    assert reference() is None


def test_unique_name_removal_promotes_next_candidate():
    reg = pu.UnitRegistry()
    first = pu.Unit(name="Duplicate", is_unique=True)
    second = pu.Unit(name="Duplicate", is_unique=True)
    reg.register(first)
    reg.register(second)

    assert reg.one("@Duplicate") is first
    reg.unregister(first)
    assert reg.one("@Duplicate") is second
    reg.unregister(second)
    assert reg.one_or_none("@Duplicate") is None


def test_service_constructed_after_app_attaches_once_and_unregisters(
    monkeypatch: pytest.MonkeyPatch,
):
    registry = pu.UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    events: list[str] = []

    class TrackedService(pu.ServiceUnit):
        def __init__(self) -> None:
            super().__init__(name="TrackedService")

        def on_attach(self, app) -> None:
            _ = app
            events.append("attach")

        def on_detach(self, app) -> None:
            _ = app
            events.append("detach")

    class TrackedApp(pu.ServiceUnit):
        def __init__(self) -> None:
            self._is_app_root = True
            super().__init__(name="TrackedApp")

    app = TrackedApp()
    app.global_units = registry
    app.units = registry
    registry.register(app)
    registry.activate_app(app)

    service = TrackedService()
    service.global_units = registry
    registry.register(service)
    service._service_init_complete = True
    registry._service_ready(service)
    assert events == ["attach"]

    registry.unregister(service)
    registry.unregister(service)
    assert events == ["attach", "detach"]


def test_service_subclass_skipping_base_init_is_not_finalized():
    registry_module = importlib.import_module("plyunit.core.units.unit_registry")

    class BaselessService(pu.ServiceUnit):
        def __init__(self) -> None:
            self.marker = True

    fake = BaselessService()

    assert fake.marker
    assert not hasattr(fake, "_service_init_complete")
    assert not registry_module.units.contains(fake)
