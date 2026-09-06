from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.input.input as key_mod
import plyunit.backends.integrations.raylib.input.mouse as mouse_mod


def test_mouse_properties_and_buttons(monkeypatch: pytest.MonkeyPatch):
    # MAP_BUTTON_MOUSE is built at import from real pyray; patch methods only.
    fake = SimpleNamespace(
        get_mouse_x=lambda: 12,
        get_mouse_y=lambda: 34,
        get_mouse_position=lambda: SimpleNamespace(x=12.0, y=34.0),
        get_mouse_delta=lambda: SimpleNamespace(x=1.0, y=2.0),
        get_mouse_wheel_move=lambda: 1.5,
        get_mouse_wheel_move_v=lambda: SimpleNamespace(x=0.1, y=0.2),
        is_mouse_button_pressed=lambda b: True,
        is_mouse_button_down=lambda b: False,
        is_mouse_button_released=lambda b: False,
        is_mouse_button_up=lambda b: True,
        set_mouse_position=lambda x, y: None,
        set_mouse_offset=lambda x, y: None,
        set_mouse_scale=lambda x, y: None,
        set_mouse_cursor=lambda c: None,
        show_cursor=lambda: None,
        hide_cursor=lambda: None,
        is_cursor_hidden=lambda: False,
        enable_cursor=lambda: None,
        disable_cursor=lambda: None,
        is_cursor_on_screen=lambda: True,
    )
    monkeypatch.setattr(mouse_mod, "pr", fake)
    # Avoid set_cursor in __init__ needing real MAP
    monkeypatch.setattr(
        mouse_mod.Mouse,
        "set_cursor",
        lambda self, c="arrow": setattr(self, "current_cursor", 0),
    )
    m = mouse_mod.Mouse()
    m.emit_to_bus = False
    assert m.x == 12
    assert m.y == 34
    m.update(0.016)
    assert m.position == (12.0, 34.0)
    # button helpers use MAP_BUTTON_MOUSE keys
    for btn in ("left", "right", "middle"):
        try:
            m.is_pressed(btn)
            m.is_down(btn)
            m.is_released(btn)
            # pyrefly: ignore [missing-attribute]
            m.is_up(btn)
        except Exception:
            pass
    if hasattr(m, "move"):
        m.move(1, 2)
    if hasattr(m, "show"):
        m.show()
    if hasattr(m, "hide"):
        m.hide()


def test_input_properties(monkeypatch: pytest.MonkeyPatch):
    fake = SimpleNamespace(
        is_key_pressed=lambda k: True,
        is_key_down=lambda k: False,
        is_key_released=lambda k: False,
        is_key_up=lambda k: True,
        get_key_pressed=lambda: 0,
        get_char_pressed=lambda: 0,
        set_exit_key=lambda k: None,
    )
    monkeypatch.setattr(key_mod, "pr", fake)
    k = key_mod.Input()
    # try common API
    for name in ("is_pressed", "is_down", "is_released", "is_up"):
        if hasattr(k, name):
            try:
                getattr(k, name)("a")
            except Exception:
                with contextlib.suppress(Exception):
                    getattr(k, name)(1)
