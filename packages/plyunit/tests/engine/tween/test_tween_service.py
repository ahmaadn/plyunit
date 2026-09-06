from __future__ import annotations

import pytest

from plyunit.core.app import App
from plyunit.core.components.transform import TransformState
from plyunit.core.units import unit as unit_module
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.events.signal import Signal
from plyunit.services.tween import TweenAnimation
from plyunit.utils.math.easing import get_easing


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


def test_tween_position_completes(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    done: list[int] = []
    tw = (
        tweens.to(t, duration=1.0, easing="linear", time_base="wall")
        .position((10.0, 20.0))
        .on_complete(lambda: done.append(1))
        .play()
    )
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert abs(t.local.position[0] - 5.0) < 1e-6
    probe.on_start_frame.emit()
    assert abs(t.local.position[0] - 10.0) < 1e-6
    assert done == [1]
    assert not tw.is_alive
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_replace_same_property(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    first_done: list[int] = []
    second_done: list[int] = []
    tweens.to(t, duration=1.0, time_base="wall").position((100.0, 0.0)).on_complete(
        lambda: first_done.append(1)
    ).play()
    tweens.to(t, duration=1.0, time_base="wall").position((0.0, 50.0)).on_complete(
        lambda: second_done.append(1)
    ).play()
    probe.window.unscaled_dt = 1.0
    probe.on_start_frame.emit()
    assert first_done == []
    assert second_done == [1]
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_raw_tween_and_kill(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    box = {"v": 0.0}
    tw = tweens.tween(
        lambda: box["v"],
        lambda v: box.__setitem__("v", float(v)),
        10.0,
        duration=1.0,
        time_base="fixed",
    )
    probe.on_fixed_update.emit(0.5)
    assert abs(box["v"] - 5.0) < 1e-6
    tw.kill()
    probe.on_fixed_update.emit(0.5)
    assert abs(box["v"] - 5.0) < 1e-6
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_sequence(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    a = tweens.to(t, duration=0.5, time_base="wall").position((10.0, 0.0))
    b = tweens.to(t, duration=0.5, time_base="wall").position((10.0, 10.0))
    done: list[int] = []
    tweens.sequence(a, b).on_complete(lambda: done.append(1)).play()
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert done == []
    probe.on_start_frame.emit()
    assert abs(t.local.position[1] - 10.0) < 1e-6
    assert done == [1]
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_parallel(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    t.set_rotation(0.0)
    a = tweens.to(t, duration=1.0, time_base="wall").position((10.0, 0.0))
    b = tweens.to(t, duration=0.5, time_base="wall").rotation(90.0)
    done: list[int] = []
    tweens.parallel(a, b).on_complete(lambda: done.append(1)).play()
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert abs(t.local.rotation - 90.0) < 1e-6
    assert done == []
    probe.on_start_frame.emit()
    assert done == [1]
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_kill_by_target(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    tweens.to(t, duration=2.0, time_base="wall").position((100.0, 0.0)).play()
    tweens.kill_by_target(t)
    probe.window.unscaled_dt = 2.0
    probe.on_start_frame.emit()
    assert t.local.position == (0.0, 0.0)
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_loop_finite(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    box = {"v": 0.0}
    done: list[int] = []
    tw = tweens.tween(
        lambda: box["v"],
        lambda v: box.__setitem__("v", float(v)),
        1.0,
        duration=0.5,
        time_base="wall",
        autoplay=False,
    )
    tw.loop(2).on_complete(lambda: done.append(1)).play()
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert done == []
    probe.on_start_frame.emit()
    assert done == [1]
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_easing_quad_out_not_linear_midpoint() -> None:
    assert abs(get_easing("linear")(0.5) - 0.5) < 1e-9
    assert get_easing("quad_out")(0.5) > 0.5


def test_app_hooks_integration(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    app = App()
    tweens = TweenAnimation()
    t = TransformState()
    t.set_position(0.0, 0.0)
    tweens.to(t, duration=0.1, time_base="fixed").position((5.0, 0.0)).play()
    app.on_fixed_update.emit(0.1)
    assert abs(t.local.position[0] - 5.0) < 1e-6
    app.shutdown()


def test_pause_and_rotation_scale(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_rotation(0.0)
    t.set_scale(1.0, 1.0)
    tweens.to(t, duration=1.0, time_base="wall").rotation(90.0).scale((2.0, 3.0)).play()
    tweens.pause()
    probe.window.unscaled_dt = 1.0
    probe.on_start_frame.emit()
    assert t.local.rotation == 0.0
    tweens.resume()
    probe.on_start_frame.emit()
    assert abs(t.local.rotation - 90.0) < 1e-6
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_yoyo_once(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    box = {"v": 0.0}
    done: list[int] = []
    tw = tweens.tween(
        lambda: box["v"],
        lambda v: box.__setitem__("v", float(v)),
        10.0,
        duration=0.5,
        time_base="wall",
        autoplay=False,
    )
    tw.yoyo(True).on_complete(lambda: done.append(1)).play()
    probe.window.unscaled_dt = 0.5
    probe.on_start_frame.emit()
    assert abs(box["v"] - 10.0) < 1e-6
    assert done == []
    probe.on_start_frame.emit()
    assert abs(box["v"] - 0.0) < 1e-6
    assert done == [1]
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_kill_by_tag_and_zero_duration(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    t.set_position(0.0, 0.0)
    done: list[int] = []
    tweens.to(t, duration=0.0, time_base="wall", tag="ui").position(
        (9.0, 0.0)
    ).on_complete(lambda: done.append(1)).play()
    assert done == [1]
    tweens.to(t, duration=2.0, time_base="wall", tag="ui").position((0.0, 0.0)).play()
    tweens.kill_by_tag("ui")
    probe.window.unscaled_dt = 2.0
    probe.on_start_frame.emit()
    assert abs(t.local.position[0] - 9.0) < 1e-6
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_empty_sequence_parallel_and_kill(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    done: list[str] = []
    tweens.sequence().on_complete(lambda: done.append("s")).play()
    tweens.parallel().on_complete(lambda: done.append("p")).play()
    assert done == ["s", "p"]
    t = TransformState()
    t.set_position(0.0, 0.0)
    a = tweens.to(t, duration=1.0, time_base="wall").position((1.0, 0.0))
    b = tweens.to(t, duration=1.0, time_base="wall").rotation(10.0)
    seq = tweens.sequence(a, b).play()
    seq.kill()
    probe.window.unscaled_dt = 1.0
    probe.on_start_frame.emit()
    assert t.local.position == (0.0, 0.0)
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_play_without_tracks_raises(isolated_registry: UnitRegistry) -> None:
    _ = isolated_registry
    probe = _ProbeApp()
    tweens = TweenAnimation()
    tweens.on_attach(probe)  # type: ignore[arg-type]
    t = TransformState()
    with pytest.raises(ValueError, match="no properties"):
        tweens.to(t, duration=0.1).play()
    tweens.on_detach(probe)  # type: ignore[arg-type]


def test_unknown_easing() -> None:
    with pytest.raises(ValueError, match="unknown easing"):
        get_easing("not_real")
