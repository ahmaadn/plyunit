from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.backends.integrations.raylib.input.input as input_module
import plyunit.backends.integrations.raylib.input.mouse as mouse_module
from plyunit.events.event_bus import EventBus
from plyunit.backends.integrations.raylib.input.input import Input
from plyunit.backends.integrations.raylib.input.mouse import Mouse

unit_module = __import__("plyunit.core.units.unit", fromlist=["units"])


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


class FakeVector2:
    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)


def test_keyboard_defers_key_events(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = EventBus()
    isolated_registry.register(bus)

    state = {"pressed": set(), "down": set(), "released": set(), "repeat": set()}
    monkeypatch.setattr(
        input_module,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: k in state["pressed"],
            is_key_down=lambda k: k in state["down"],
            is_key_released=lambda k: k in state["released"],
            is_key_pressed_repeat=lambda k: k in state["repeat"],
            is_key_up=lambda k: k not in state["down"],
        ),
    )

    kb = Input()
    isolated_registry.register(kb)
    kb.map("jump", 32)

    received: list[str] = []
    bus.subscribe("key.jump.pressed", lambda **kw: received.append("pressed"))
    bus.subscribe("key.jump.down", lambda **kw: received.append("down"))
    bus.subscribe("key.jump.released", lambda **kw: received.append("released"))
    bus.subscribe("key.jump.repeat", lambda **kw: received.append("repeat"))

    state["pressed"] = {32}
    state["down"] = {32}
    state["repeat"] = {32}
    kb.update(0.016)
    assert bus._queue  # deferred
    bus.dispatch()
    assert "pressed" in received
    assert "down" in received
    assert "repeat" in received

    received.clear()
    state["pressed"] = set()
    state["repeat"] = set()
    state["released"] = {32}
    state["down"] = set()
    kb.update(0.016)
    bus.dispatch()
    assert received == ["released"]


def test_keyboard_no_bus_is_noop(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry
    monkeypatch.setattr(
        input_module,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: True,
            is_key_down=lambda k: True,
            is_key_released=lambda k: False,
            is_key_pressed_repeat=lambda k: False,
            is_key_up=lambda k: False,
        ),
    )
    kb = Input()
    kb.map("jump", 1)
    kb.update(0.016)  # no EventBus registered


def test_keyboard_emit_to_bus_false(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = EventBus()
    isolated_registry.register(bus)
    monkeypatch.setattr(
        input_module,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: True,
            is_key_down=lambda k: True,
            is_key_released=lambda k: False,
            is_key_pressed_repeat=lambda k: False,
            is_key_up=lambda k: False,
        ),
    )
    kb = Input()
    isolated_registry.register(kb)
    kb.map("jump", 1)
    bus.subscribe("key.jump.pressed", lambda **kw: None)
    kb.emit_to_bus = False
    kb.update(0.016)
    assert bus._queue == []


def test_mouse_defers_button_events(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = EventBus()
    isolated_registry.register(bus)

    state = {
        "pos": FakeVector2(10.0, 20.0),
        "pressed": set(),
        "down": set(),
        "released": set(),
    }
    left = mouse_module.MAP_BUTTON_MOUSE["left"]

    monkeypatch.setattr(
        mouse_module,
        "pr",
        SimpleNamespace(
            get_mouse_position=lambda: state["pos"],
            get_mouse_x=lambda: int(state["pos"].x),
            get_mouse_y=lambda: int(state["pos"].y),
            is_mouse_button_pressed=lambda b: b in state["pressed"],
            is_mouse_button_down=lambda b: b in state["down"],
            is_mouse_button_released=lambda b: b in state["released"],
            set_mouse_cursor=lambda _c: None,
            MouseButton=SimpleNamespace(
                MOUSE_BUTTON_LEFT=left,
                MOUSE_BUTTON_RIGHT=1,
                MOUSE_BUTTON_MIDDLE=2,
                MOUSE_BUTTON_SIDE=3,
                MOUSE_BUTTON_EXTRA=4,
                MOUSE_BUTTON_FORWARD=5,
                MOUSE_BUTTON_BACK=6,
            ),
            MouseCursor=SimpleNamespace(
                MOUSE_CURSOR_ARROW=0,
                MOUSE_CURSOR_IBEAM=1,
                MOUSE_CURSOR_CROSSHAIR=2,
                MOUSE_CURSOR_POINTING_HAND=3,
                MOUSE_CURSOR_RESIZE_EW=4,
                MOUSE_CURSOR_RESIZE_NS=5,
                MOUSE_CURSOR_RESIZE_NWSE=6,
                MOUSE_CURSOR_RESIZE_NESW=7,
                MOUSE_CURSOR_RESIZE_ALL=8,
                MOUSE_CURSOR_NOT_ALLOWED=9,
            ),
        ),
    )

    # Rebuild MAP after patch is not needed if MAP already resolved constants.
    mouse = Mouse()
    isolated_registry.register(mouse)

    payloads: list[dict] = []
    bus.subscribe(
        "mouse.left.pressed",
        lambda **kw: payloads.append(kw),
    )

    def on_down(**kw) -> None:
        payloads.append({"kind": "down", **kw})

    bus.subscribe("mouse.left.down", on_down)

    state["pressed"] = {left}
    state["down"] = {left}
    mouse.update(0.016)
    bus.dispatch()

    assert any(
        p.get("action") == "left" and p.get("device") == "mouse" for p in payloads
    )
    assert any(p.get("position") == (10.0, 20.0) for p in payloads)


def test_app_dispatch_after_begin_update(
    isolated_registry: pu.UnitRegistry,
) -> None:
    from plyunit.core.app import App

    bus = EventBus()
    isolated_registry.register(bus)
    app = App()
    isolated_registry.register(app)

    calls: list[str] = []
    bus.subscribe("ping", lambda: calls.append("ping"))
    bus.defer("ping")
    assert calls == []
    app._dispatch_event_bus()
    assert calls == ["ping"]


def test_keyboard_edges_once_per_multi_substep(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressed/released/repeat fire only on first fixed substep; down every step."""
    from plyunit.core.app import App

    bus = EventBus()
    isolated_registry.register(bus)
    app = App()
    isolated_registry.register(app)

    state = {"pressed": set(), "down": set(), "released": set(), "repeat": set()}
    monkeypatch.setattr(
        input_module,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: k in state["pressed"],
            is_key_down=lambda k: k in state["down"],
            is_key_released=lambda k: k in state["released"],
            is_key_pressed_repeat=lambda k: k in state["repeat"],
            is_key_up=lambda k: k not in state["down"],
        ),
    )

    kb = Input()
    isolated_registry.register(kb)
    kb.map("jump", 32)

    received: list[str] = []
    bus.subscribe("key.jump.pressed", lambda **kw: received.append("pressed"))
    bus.subscribe("key.jump.down", lambda **kw: received.append("down"))
    bus.subscribe("key.jump.repeat", lambda **kw: received.append("repeat"))

    state["pressed"] = {32}
    state["down"] = {32}
    state["repeat"] = {32}

    for i in range(3):
        app._fixed_step_index = i
        assert kb.is_pressed("jump") is (i == 0)
        assert kb.is_pressed_repeat("jump") is (i == 0)
        assert kb.is_down("jump") is True
        kb.update(0.016)
        bus.dispatch()

    assert received.count("pressed") == 1
    assert received.count("repeat") == 1
    assert received.count("down") == 3


def test_mouse_edges_once_per_multi_substep(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plyunit.core.app import App

    bus = EventBus()
    isolated_registry.register(bus)
    app = App()
    isolated_registry.register(app)

    left = mouse_module.MAP_BUTTON_MOUSE["left"]
    state = {
        "pos": FakeVector2(1.0, 2.0),
        "pressed": {left},
        "down": {left},
        "released": set(),
    }
    monkeypatch.setattr(
        mouse_module,
        "pr",
        SimpleNamespace(
            get_mouse_position=lambda: state["pos"],
            get_mouse_x=lambda: int(state["pos"].x),
            get_mouse_y=lambda: int(state["pos"].y),
            is_mouse_button_pressed=lambda b: b in state["pressed"],
            is_mouse_button_down=lambda b: b in state["down"],
            is_mouse_button_released=lambda b: b in state["released"],
            set_mouse_cursor=lambda _c: None,
            MouseButton=SimpleNamespace(
                MOUSE_BUTTON_LEFT=left,
                MOUSE_BUTTON_RIGHT=1,
                MOUSE_BUTTON_MIDDLE=2,
                MOUSE_BUTTON_SIDE=3,
                MOUSE_BUTTON_EXTRA=4,
                MOUSE_BUTTON_FORWARD=5,
                MOUSE_BUTTON_BACK=6,
            ),
            MouseCursor=SimpleNamespace(
                MOUSE_CURSOR_ARROW=0,
                MOUSE_CURSOR_IBEAM=1,
                MOUSE_CURSOR_CROSSHAIR=2,
                MOUSE_CURSOR_POINTING_HAND=3,
                MOUSE_CURSOR_RESIZE_EW=4,
                MOUSE_CURSOR_RESIZE_NS=5,
                MOUSE_CURSOR_RESIZE_NWSE=6,
                MOUSE_CURSOR_RESIZE_NESW=7,
                MOUSE_CURSOR_RESIZE_ALL=8,
                MOUSE_CURSOR_NOT_ALLOWED=9,
            ),
        ),
    )

    mouse = Mouse()
    isolated_registry.register(mouse)

    pressed_count = 0
    down_count = 0

    def on_pressed(**_kw) -> None:
        nonlocal pressed_count
        pressed_count += 1

    def on_down(**_kw) -> None:
        nonlocal down_count
        down_count += 1

    bus.subscribe("mouse.left.pressed", on_pressed)
    bus.subscribe("mouse.left.down", on_down)

    for i in range(3):
        app._fixed_step_index = i
        assert mouse.is_pressed("left") is (i == 0)
        assert mouse.is_down("left") is True
        mouse.update(0.016)
        bus.dispatch()

    assert pressed_count == 1
    assert down_count == 3


def test_edge_fallback_without_app(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without App, edges stay enabled so isolated unit tests keep working."""
    _ = isolated_registry
    monkeypatch.setattr(
        input_module,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: True,
            is_key_down=lambda k: True,
            is_key_released=lambda k: False,
            is_key_pressed_repeat=lambda k: False,
            is_key_up=lambda k: False,
        ),
    )
    kb = Input()
    kb.map("jump", 1)
    assert kb.is_pressed("jump") is True
