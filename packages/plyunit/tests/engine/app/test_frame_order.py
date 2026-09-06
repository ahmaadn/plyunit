from __future__ import annotations

import importlib

import pytest

from plyunit.core.app import App, AppConfig
from plyunit.core.units.node_unit import NodeUnit
from plyunit.core.units.scene_unit import SceneUnit
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.event_bus import EventBus


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


class OrderScene(SceneUnit):
    def __init__(self) -> None:
        super().__init__(name="OrderScene")
        self.order: list[str] = []

    def update(self, dt: float) -> None:
        _ = dt
        self.order.append("scene_update")
        bus = self.one_or_none("@EventBus", scope="global")
        if bus is not None:
            bus.defer("late.event")


def test_early_and_late_event_bus_drain():
    app = App()
    app.config = AppConfig()
    app.window = type(
        "Window",
        (),
        {
            "fixed_delta_time": 1.0 / 60.0,
            "accumulator": 0.0,
            "consume_fixed_steps": lambda self, max_steps: 1,
        },
    )()
    bus = EventBus()
    order: list[str] = []

    bus.subscribe("early.event", lambda: order.append("early_delivered"))
    bus.subscribe("late.event", lambda: order.append("late_delivered"))

    scene = OrderScene()
    scene.load()

    class SM:
        def begin_step(self) -> None:
            return

        def end_step(self) -> None:
            return

        def apply_pending(self) -> None:
            return

        def update(self, dt: float) -> None:
            scene._dispatch_update(dt)
            order.append("scene_update")

    sm = SM()
    app.scene_manager = sm

    def on_begin(dt: float) -> None:
        _ = dt
        order.append("begin")
        bus.defer("early.event")

    def on_fixed(dt: float) -> None:
        _ = dt
        order.append("physics")

    def fixed_update(dt: float, step: int) -> None:
        _ = step
        sm.update(dt)

    app.on_begin_update.connect(on_begin)
    app.on_fixed_update.connect(on_fixed)
    app.fixed_update = fixed_update  # type: ignore[method-assign]

    app.window.accumulator = app.window.fixed_delta_time
    app.step_fixed()

    assert order.index("begin") < order.index("early_delivered")
    assert order.index("early_delivered") < order.index("scene_update")
    assert order.index("scene_update") < order.index("physics")
    assert order.index("physics") < order.index("late_delivered")


def test_exact_fixed_step_lifecycle_order() -> None:
    app = App()
    app.config = AppConfig()
    app.window = type(
        "Window",
        (),
        {
            "fixed_delta_time": 1.0 / 60.0,
            "accumulator": 1.0 / 60.0,
            "consume_fixed_steps": lambda self, max_steps: 1,
        },
    )()
    order: list[str] = []

    class SM:
        def begin_step(self) -> None:
            order.append("begin_step")

        def update(self, dt: float) -> None:
            _ = dt
            order.append("scene_update")

        def apply_pending(self) -> None:
            order.append("apply_pending")

        def end_step(self) -> None:
            order.append("end_step")

    sm = SM()
    app.scene_manager = sm
    app.on_begin_update.connect(lambda dt: order.append("begin_update"))
    app.on_after_update.connect(lambda dt: order.append("after_update"))
    app.on_end_update.connect(lambda dt: order.append("end_update"))
    app.on_fixed_update.connect(lambda dt: order.append("on_fixed_update"))
    app._dispatch_event_bus = lambda: order.append(  # type: ignore[method-assign]
        "event_dispatch"
    )

    def fixed_update(dt: float, step: int) -> None:
        _ = dt, step
        order.append("fixed_update")
        sm.update(dt)
        sm.apply_pending()

    app.fixed_update = fixed_update  # type: ignore[method-assign]

    app.step_fixed()

    assert order == [
        "begin_step",
        "begin_update",
        "event_dispatch",
        "fixed_update",
        "scene_update",
        "apply_pending",
        "after_update",
        "end_update",
        "on_fixed_update",
        "event_dispatch",
        "end_step",
    ]


def test_physics_hook_is_on_fixed_update_not_begin():
    pytest.importorskip("pymunk")
    from plyunit.backends.physics.pymunk.service import Physics
    from plyunit.events.signal import Signal

    class ProbeApp:
        def __init__(self) -> None:
            self.on_fixed_update = Signal("on_fixed_update")
            self.on_begin_update = Signal("on_begin_update")

    probe = ProbeApp()
    svc = Physics(gravity=(0.0, 0.0), enable_spatial_hash=False)
    svc.on_attach(probe)  # type: ignore[arg-type]
    assert len(probe.on_fixed_update._listeners) == 1
    assert len(probe.on_begin_update._listeners) == 0


def test_same_step_world_after_dispatch_update():
    scene = SceneUnit(name="S")
    scene.load()

    class Writer(NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            self.transform.set_position(10.0, 0.0)

    parent_writer = Writer(name="PW")
    scene.root.attach(parent_writer)
    child2 = NodeUnit(name="CW")
    parent_writer.attach(child2)
    child2.transform.set_position(5.0, 0.0)

    scene._dispatch_update(0.016)
    assert parent_writer.transform.world.position[0] == 10.0
    assert child2.transform.world.position[0] == 15.0
