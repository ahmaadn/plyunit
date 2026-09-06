from __future__ import annotations

import pytest

from plyunit.core.app import App
from plyunit.core.components.transform import TransformState
from plyunit.core.units import unit as unit_module
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.signal import Signal
from plyunit.services.timers import Timer
from plyunit.services.tween import TweenAnimation


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


class _ProbeApp:
    def __init__(self) -> None:
        self.on_fixed_update = Signal("on_fixed_update")
        self.on_start_frame = Signal("on_start_frame")
        self.window = type("W", (), {"unscaled_dt": 0.0, "dt": 0.0})()


def test_delay_fixed_fires_after_steps(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    app.window = type("W", (), {})()
    app.window.fixed_delta_time = 1.0 / 60.0
    timers = Timer()
    timers.on_attach(app)

    fired: list[int] = []
    dt = app.window.fixed_delta_time
    steps = 30
    h = timers.delay(steps * dt, lambda: fired.append(1), time_base="fixed")
    assert h.is_alive

    for _ in range(steps - 1):
        app.on_fixed_update.emit(dt)
    assert fired == []
    app.on_fixed_update.emit(dt)
    assert fired == [1]
    assert not h.is_alive

    timers.on_detach(app)


def test_delay_cancel(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    timers = Timer()
    timers.on_attach(app)
    fired: list[int] = []
    h = timers.delay(1.0, lambda: fired.append(1), time_base="fixed")
    h.cancel()
    h.cancel()
    app.on_fixed_update.emit(1.0)
    assert fired == []
    timers.on_detach(app)


def test_interval_count_and_wall(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    timers = Timer()
    timers.on_attach(probe)  # type: ignore[arg-type]

    ticks: list[int] = []
    h = timers.interval(0.25, lambda: ticks.append(1), time_base="wall", count=3)
    probe.window.unscaled_dt = 0.25
    probe.window.dt = 0.0
    for _ in range(3):
        probe.on_start_frame.emit()
    assert ticks == [1, 1, 1]
    assert not h.is_alive
    timers.on_detach(probe)  # type: ignore[arg-type]


def test_scaled_uses_window_dt(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    timers = Timer()
    timers.on_attach(probe)  # type: ignore[arg-type]
    fired: list[int] = []
    timers.delay(0.5, lambda: fired.append(1), time_base="scaled")
    probe.window.unscaled_dt = 1.0
    probe.window.dt = 0.0
    probe.on_start_frame.emit()
    assert fired == []
    probe.window.dt = 0.5
    probe.on_start_frame.emit()
    assert fired == [1]
    timers.on_detach(probe)  # type: ignore[arg-type]


def test_pause_freezes(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    timers = Timer()
    timers.on_attach(app)
    fired: list[int] = []
    timers.delay(0.1, lambda: fired.append(1), time_base="fixed")
    timers.pause()
    app.on_fixed_update.emit(1.0)
    assert fired == []
    timers.resume()
    app.on_fixed_update.emit(0.1)
    assert fired == [1]
    timers.on_detach(app)


def test_wait_and_run_generator(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    app.window = type("W", (), {"fixed_delta_time": 0.1})()
    timers = Timer()
    timers.on_attach(app)
    log: list[str] = []

    def seq():
        log.append("a")
        yield timers.wait(0.2, time_base="fixed")
        log.append("b")
        yield timers.wait(0.1, time_base="fixed")
        log.append("c")

    coro = timers.run(seq())
    assert log == ["a"]
    dt = 0.1
    app.on_fixed_update.emit(dt)
    assert log == ["a"]
    app.on_fixed_update.emit(dt)
    assert log == ["a", "b"]
    app.on_fixed_update.emit(dt)
    assert log == ["a", "b", "c"]
    assert coro.done
    timers.on_detach(app)


def test_clear(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    timers = Timer()
    timers.on_attach(app)
    fired: list[int] = []
    timers.delay(1.0, lambda: fired.append(1), time_base="fixed")
    timers.clear()
    app.on_fixed_update.emit(2.0)
    assert fired == []
    timers.on_detach(app)


def test_invalid_args(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    timers = Timer()
    with pytest.raises(ValueError):
        timers.interval(0.0, lambda: None)
    with pytest.raises(ValueError):
        timers.interval(1.0, lambda: None, count=0)
    with pytest.raises(ValueError):
        timers.delay(-1.0, lambda: None)
    with pytest.raises(ValueError):
        timers.wait(-0.1)
    with pytest.raises(ValueError):
        timers.delay(1.0, lambda: None, time_base="nope")  # type: ignore[arg-type]


def test_run_cancel_mid_wait(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    timers = Timer()
    timers.on_attach(app)
    log: list[str] = []

    def seq():
        log.append("a")
        yield timers.wait(1.0, time_base="fixed")
        log.append("b")

    coro = timers.run(seq())
    assert log == ["a"]
    assert coro.is_alive
    coro.cancel()
    assert not coro.is_alive
    assert coro.done
    app.on_fixed_update.emit(2.0)
    assert log == ["a"]
    timers.on_detach(app)


def test_run_with_tween(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    timers = Timer()
    tweens = TweenAnimation()
    timers.on_attach(probe)  # type: ignore[arg-type]
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    done: list[int] = []

    def seq():
        yield tweens.to(t, duration=0.5, time_base="wall").position((10.0, 0.0)).play()
        done.append(1)

    timers.run(seq())
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert abs(t.local.position[0] - 10.0) < 1e-6
    assert done == [1]
    timers.on_detach(probe)  # type: ignore[arg-type]
    tweens.on_detach(probe)  # type: ignore[arg-type]
