from __future__ import annotations

import gc
import weakref

import pytest

import plyunit as pu
from plyunit.events.event_bus import EventBus

unit_module = __import__("plyunit.core.units.unit", fromlist=["units"])


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_priority_higher_first(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    bus = EventBus()
    order: list[str] = []

    bus.subscribe("hit", lambda: order.append("low"), priority=0)
    bus.subscribe("hit", lambda: order.append("high"), priority=10)
    bus.subscribe("hit", lambda: order.append("mid"), priority=5)
    bus.publish("hit")

    assert order == ["high", "mid", "low"]


def test_equal_priority_stable_subscribe_order(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    order: list[int] = []

    bus.subscribe("t", lambda: order.append(1), priority=0)
    bus.subscribe("t", lambda: order.append(2), priority=0)
    bus.subscribe("t", lambda: order.append(3), priority=0)
    bus.publish("t")

    assert order == [1, 2, 3]


def test_publish_immediate_does_not_queue(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []
    bus.subscribe("hit", lambda v: calls.append(v))
    bus.publish("hit", 1)
    assert calls == [1]
    assert bus._queue == []


def test_defer_then_dispatch(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[tuple] = []

    def listener(**kwargs) -> None:
        calls.append(("hit", kwargs))

    bus.subscribe("hit", listener)
    bus.defer("hit", value=1)
    bus.defer("hit", value=2)
    assert calls == []
    bus.dispatch()
    assert calls == [("hit", {"value": 1}), ("hit", {"value": 2})]
    assert bus._queue == []


def test_dispatch_snapshot_ignores_nested_defer(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[str] = []

    def first() -> None:
        calls.append("first")
        bus.defer("nested")

    def nested() -> None:
        calls.append("nested")

    bus.subscribe("first", first)
    bus.subscribe("nested", nested)
    bus.defer("first")
    bus.dispatch()
    assert calls == ["first"]
    assert len(bus._queue) == 1
    bus.dispatch()
    assert calls == ["first", "nested"]


def test_clear_queue(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []
    bus.subscribe("x", lambda v: calls.append(v))
    bus.defer("x", 1)
    bus.clear_queue()
    bus.dispatch()
    assert calls == []


def test_has_listeners(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    bus = EventBus()
    assert bus.has_listeners("a") is False

    def listener() -> None:
        pass

    bus.subscribe("a", listener)
    assert bus.has_listeners("a") is True
    bus.unsubscribe("a", listener)
    assert bus.has_listeners("a") is False


def test_weakref_bound_method_with_priority(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []

    class Listener:
        def on_value(self, value: int) -> None:
            calls.append(value)

    listener = Listener()
    ref = weakref.ref(listener)
    bus.subscribe("tick", listener.on_value, priority=5)
    bus.publish("tick", 1)
    assert calls == [1]
    del listener
    gc.collect()
    assert ref() is None
    bus.publish("tick", 2)
    assert calls == [1]
