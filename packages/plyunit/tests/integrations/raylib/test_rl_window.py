from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.core.window as win_mod
from plyunit.backends.integrations.raylib.core import Window
from plyunit.backends.interfaces import IWindow
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
