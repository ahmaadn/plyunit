from __future__ import annotations

import gc
import importlib
import weakref
from typing import cast

import pytest

import plyunit as pu
from plyunit.events.signal import unwire_bindings, wire_bindings
from plyunit.events.signal import _SignalBinding

unit_module = importlib.import_module("plyunit.core.units.unit")


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_signal_connect_emit_disconnect_and_repr() -> None:
    signal = pu.Signal("damage")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def listener(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    signal.connect(listener)
    signal.connect(listener)
    assert len(signal) == 1

    signal.emit(10, source="enemy")
    assert calls == [((10,), {"source": "enemy"})]

    signal.disconnect(listener)
    signal.disconnect(listener)
    assert len(signal) == 0

    assert repr(signal) == "Signal('damage' listeners=0)"


def test_signal_disconnect_all_and_mutation_during_emit() -> None:
    signal = pu.Signal()
    calls: list[str] = []

    def one() -> None:
        calls.append("one")
        signal.disconnect(second)

    def second() -> None:
        calls.append("second")

    signal.connect(one)
    signal.connect(second)

    signal.emit()
    assert calls == ["one", "second"]

    calls.clear()
    signal.emit()
    assert calls == ["one"]

    signal.disconnect_all()
    assert len(signal) == 0


def test_signal_does_not_retain_bound_method_owner() -> None:
    signal = pu.Signal("weak")
    calls: list[int] = []

    class Listener:
        def on_value(self, value: int) -> None:
            calls.append(value)

    listener = Listener()
    listener_ref = weakref.ref(listener)

    signal.connect(listener.on_value)
    signal.emit(1)
    assert calls == [1]

    del listener
    gc.collect()

    assert listener_ref() is None

    # The listener was GC'd; emit must not crash and the entry must be cleaned up.
    signal.emit(2)
    assert calls == [1]
    assert len(signal) == 0


def test_on_rejects_non_class_component() -> None:
    with pytest.raises(ValueError, match="component harus berupa tipe class"):
        pu.on(
            None,
            component=cast(type[pu.Component], pu.Component()),
            event="ping",
        )


def test_signal_binding_repr_variants() -> None:
    class Health(pu.Component):
        pass

    binding_unit = _SignalBinding("Enemy", event_name="died", scope="mixed")
    binding_string_component = _SignalBinding(
        "Enemy",
        cast(type[pu.Component], "Health"),
        event_name="died",
        scope="mixed",
    )
    binding_component_type = _SignalBinding(
        "Enemy", Health, event_name="died", scope="mixed"
    )

    assert repr(binding_unit) == "@on('Enemy', 'died')"
    assert repr(binding_string_component) == "@on('Enemy', Health, 'died')"
    assert repr(binding_component_type) == "@on('Enemy', Health, 'died')"


def test_wire_bindings_self_signal_and_unwire() -> None:
    class Listener(pu.Unit):
        def __init__(self) -> None:
            super().__init__(name="Listener")
            self.ping = pu.Signal("ping")
            self.received: list[int] = []

        @pu.on(None, event="ping")
        def on_ping(self, value: int) -> None:
            self.received.append(value)

    listener = Listener()
    wired = wire_bindings(listener)

    assert len(wired) == 1
    listener.ping.emit(42)
    assert listener.received == [42]

    unwire_bindings(wired)
    assert wired == []

    listener.ping.emit(99)
    assert listener.received == [42]


def test_wire_bindings_resolves_target_component_signal(
    isolated_registry: pu.UnitRegistry,
) -> None:
    class Health(pu.Component):
        def __init__(self) -> None:
            super().__init__()
            self.on_low_hp = pu.Signal("on_low_hp")

    class Enemy(pu.NodeUnit):
        pass

    class Observer(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Observer")
            self.seen: list[int] = []

        @pu.on("Enemy", Health, event="on_low_hp")
        def on_enemy_low(self, hp: int) -> None:
            self.seen.append(hp)

    class SceneUnit(pu.SceneUnit):
        def on_load(self) -> None:
            enemy = Enemy(name="Enemy")
            enemy.add_component(Health())

            observer = Observer()

            self.root.attach(enemy)
            self.root.attach(observer)

    scene = SceneUnit()
    scene.load()

    observer = scene.one(Observer)
    health = scene.one(Enemy)[Health]

    wired = wire_bindings(observer)
    assert len(wired) == 1

    health.on_low_hp.emit(12)
    assert observer.seen == [12]

    unwire_bindings(wired)
    assert wired == []


def test_wire_bindings_warns_when_target_missing(
    isolated_registry: pu.UnitRegistry,
) -> None:
    class Observer(pu.Unit):
        def __init__(self) -> None:
            super().__init__(name="Observer")
            self.count = 0

        @pu.on("MissingEnemy", event="died")
        def on_enemy_died(self) -> None:
            self.count += 1

    observer = Observer()

    with pytest.warns(UserWarning, match="target unit 'MissingEnemy' tidak ditemukan"):
        wired = wire_bindings(observer)

    assert wired == []


def test_wire_bindings_warns_when_target_lacks_component(
    isolated_registry: pu.UnitRegistry,
) -> None:

    class Health(pu.Component):
        pass

    class Enemy(pu.NodeUnit):
        pass

    class Observer(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Observer")
            self.seen: list[int] = []

        @pu.on("Enemy", Health, event="on_low_hp")
        def on_enemy_low(self, hp: int) -> None:
            self.seen.append(hp)

    class SceneUnit(pu.SceneUnit):
        def on_load(self) -> None:
            enemy = Enemy(name="Enemy")
            observer = Observer()

            self.root.attach(enemy)
            self.root.attach(observer)

    scene = SceneUnit()
    scene.load()
    observer = scene.one(Observer)

    with pytest.warns(UserWarning, match="tidak punya component 'Health'"):
        wired = wire_bindings(observer)

    assert wired == []


def test_wire_bindings_warns_when_event_attribute_is_not_signal(
    isolated_registry: pu.UnitRegistry,
) -> None:
    class Stats(pu.Component):
        def __init__(self) -> None:
            super().__init__()
            self.not_signal = 123

    class Enemy(pu.NodeUnit):
        pass

    class Observer(pu.NodeUnit):
        @pu.on("Enemy", Stats, event="not_signal")
        def on_enemy_stats(self, value: int) -> None:
            _ = value

    class SceneUnit(pu.SceneUnit):
        def on_load(self) -> None:

            enemy = Enemy(name="Enemy")
            enemy.add_component(Stats())
            observer = Observer(name="Observer")
            self.root.attach(enemy)
            self.root.attach(observer)

    scene = SceneUnit()
    scene.load()
    observer = scene.one(Observer)

    with pytest.warns(UserWarning, match="bukan Signal atau tidak ada"):
        wired = wire_bindings(observer)

    assert wired == []


def test_wire_bindings_mixed_scope_prefers_scene_registry(
    isolated_registry: pu.UnitRegistry,
) -> None:
    class EnemyGlobal(pu.Unit):
        def __init__(self) -> None:
            super().__init__(name="Enemy", register=True)
            self.died = pu.Signal("global_died")

    class EnemyScene(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Enemy")
            self.died = pu.Signal("scene_died")

    class Observer(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Observer")
            self.count = 0

        @pu.on("Enemy", event="died")
        def on_enemy_died(self) -> None:
            self.count += 1

    global_enemy = EnemyGlobal()

    scene = pu.SceneUnit(name="Battle")
    scene._attach_subtree(scene.root)

    scene_enemy = EnemyScene()
    observer = Observer()

    scene.root.attach(scene_enemy)
    scene.root.attach(observer)

    wired = wire_bindings(observer)
    assert len(wired) == 1

    scene_enemy.died.emit()
    global_enemy.died.emit()
    assert observer.count == 1

    unwire_bindings(wired)


def test_wire_bindings_global_scope_ignores_scene_registry(
    isolated_registry: pu.UnitRegistry,
) -> None:
    class EnemyGlobal(pu.Unit):
        def __init__(self) -> None:
            super().__init__(name="Enemy", register=True)
            self.died = pu.Signal("global_died")

    class EnemyScene(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Enemy")
            self.died = pu.Signal("scene_died")

    class Observer(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Observer")
            self.count = 0

        @pu.on("Enemy", event="died", scope="global")
        def on_enemy_died(self) -> None:
            self.count += 1

    global_enemy = EnemyGlobal()

    scene = pu.SceneUnit(name="Battle")
    scene._attach_subtree(scene.root)

    scene_enemy = EnemyScene()
    observer = Observer()

    scene.root.attach(scene_enemy)
    scene.root.attach(observer)

    wired = wire_bindings(observer)
    assert len(wired) == 1

    scene_enemy.died.emit()
    global_enemy.died.emit()
    assert observer.count == 1

    unwire_bindings(wired)
