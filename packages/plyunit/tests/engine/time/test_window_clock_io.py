from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.core.window as window_module
from plyunit.backends.integrations.raylib.core import Window
from plyunit.utils.io import read_json, write_json


@pytest.fixture()
def window(monkeypatch: pytest.MonkeyPatch) -> Window:
    monkeypatch.setattr(
        window_module,
        "pr",
        SimpleNamespace(get_frame_time=lambda: 1.0),
    )
    return Window()


def test_window_start_frame_and_consume_steps_behaviour(window: Window) -> None:
    window.set_time_scale(0.5)
    window.start_frame()

    assert math.isclose(window.unscaled_dt, 0.25)
    assert math.isclose(window.dt, 0.125)
    assert math.isclose(window.total_time, 0.25)
    assert window.frame_count == 1
    assert math.isclose(window.accumulator, 0.125)

    window.set_fixed_timestep_hz(10)
    steps = window.consume_fixed_steps(10)

    assert steps == 1
    assert math.isclose(window.accumulator, 0.025, abs_tol=1e-9)
    assert math.isclose(window.alpha, 0.25, abs_tol=1e-9)
    assert window.fixed_steps == 1


def test_window_consume_steps_overload_drop_remainder(window: Window) -> None:
    window.set_fixed_timestep_hz(10)
    window.accumulator = 0.55

    steps = window.consume_fixed_steps(3)

    assert steps == 3
    assert math.isclose(window.accumulator, 0.0)
    assert math.isclose(window.alpha, 0.0)
    assert window.fixed_steps == 3


def test_window_validation_and_reset(window: Window) -> None:
    with pytest.raises(ValueError, match="max_steps must be > 0"):
        window.consume_fixed_steps(0)

    with pytest.raises(ValueError, match="time_scale must be >= 0"):
        window.set_time_scale(-0.1)

    with pytest.raises(ValueError, match="fixed timestep hz must be > 0"):
        window.set_fixed_timestep_hz(0)

    window.set_time_scale(2.0)
    window.start_frame()
    window.reset()

    assert window.dt == 0.0
    assert window.unscaled_dt == 0.0
    assert window.total_time == 0.0
    assert window.frame_count == 0
    assert window.time_scale == 1.0
    assert window.accumulator == 0.0
    assert window.alpha == 0.0
    assert window.fixed_steps == 0


def test_io_read_and_write_json_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.json"
    payload = {"name": "plyunit", "value": 42, "items": [1, 2, 3]}

    write_json(path, payload)
    assert read_json(path) == payload

    path_str = tmp_path / "config_str.json"
    write_json(str(path_str), {"ok": True})
    assert read_json(str(path_str)) == {"ok": True}
