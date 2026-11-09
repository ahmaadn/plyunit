from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.window as win_mod
from plyunit.backends.integrations.raylib.window import Window
from plyunit.backends.ports.renderer import IWindow
from plyunit.core.units import ServiceUnit


@pytest.fixture()
def fake_pr(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    fake = SimpleNamespace(
        init_window=lambda w, h, t: calls.append(("init", w, h, t)),
        set_target_fps=lambda f: calls.append(("fps", f)),
        window_should_close=lambda: False,
        begin_drawing=lambda: calls.append(("begin",)),
        end_drawing=lambda: calls.append(("end",)),
        close_window=lambda: calls.append(("close",)),
        get_frame_time=lambda: 0.016,
        clear_background=lambda c: calls.append(("clear", c)),
    )
    monkeypatch.setattr(win_mod, "pr", fake)
    return calls


def test_raylib_window_lifecycle(fake_pr):
    calls = fake_pr
    w = Window()
    assert isinstance(w, ServiceUnit)
    assert isinstance(w, IWindow)
    assert w.name == "Window"
    assert w.singleton_kind == "service"
    w.init_window(320, 240, "t")
    w.set_target_fps(60)
    assert w.window_should_close() is False
    w.begin_drawing()
    w.clear_background((1, 2, 3, 4))
    w.end_drawing()
    assert w.get_frame_time() == 0.016
    w.close_window()
    assert ("init", 320, 240, "t") in calls
    assert ("fps", 60) in calls
    assert ("begin",) in calls
    assert ("end",) in calls
    assert ("close",) in calls


def test_raylib_window_accepts_uncapped_fps(fake_pr: list[tuple]) -> None:
    """The window accepts the zero FPS cap documented by AppConfig."""
    window = Window()
    window.set_target_fps(0)
    assert ("fps", 0) in fake_pr
    with pytest.raises(ValueError, match=">= 0"):
        window.set_target_fps(-1)


def test_loading_frame_always_ends_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A loading-screen exception must still finish its native drawing frame."""
    calls: list[str] = []

    def fail_clear(color: object) -> None:
        raise RuntimeError("clear failed")

    monkeypatch.setattr(
        win_mod,
        "pr",
        SimpleNamespace(
            begin_drawing=lambda: calls.append("begin"),
            clear_background=fail_clear,
            end_drawing=lambda: calls.append("end"),
        ),
    )
    with pytest.raises(RuntimeError, match="clear failed"):
        Window().present_loading_frame((0, 0, 0, 255))
    assert calls == ["begin", "end"]


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_time_scale_rejects_nonfinite_values(value: float) -> None:
    """Non-finite scale cannot poison the fixed-step accumulator."""
    window = Window()
    with pytest.raises(ValueError, match="finite"):
        window.set_time_scale(value)
    assert window.time_scale == 1.0
