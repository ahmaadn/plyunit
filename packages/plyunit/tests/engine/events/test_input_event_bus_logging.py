from __future__ import annotations

import gc
import importlib
import logging
import weakref
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.backends.integrations.raylib.input as input_module
import plyunit.backends.integrations.raylib.input.input as keyboard_module
import plyunit.backends.integrations.raylib.input.mouse as mouse_module
from plyunit.events.event_bus import EventBus
from plyunit.core.logging import configure_logging

unit_module = importlib.import_module("plyunit.core.units.unit")


class FakeVector2:
    def __init__(self, x: float | tuple[float, float] = 0.0, y: float = 0.0) -> None:
        if isinstance(x, tuple):
            x, y = x
        self.x = float(x)
        self.y = float(y)


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_event_bus_subscribe_publish_and_unsubscribe(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []

    def listener(value: int) -> None:
        calls.append(value)

    bus.subscribe("hit", listener)
    bus.publish("hit", 1)

    bus.unsubscribe("hit", listener)
    bus.publish("hit", 2)

    bus.unsubscribe("missing", listener)

    assert calls == [1]


def test_event_bus_unsubscribe_missing_listener_is_noop(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []

    def listener(value: int) -> None:
        calls.append(value)

    def other(_value: int) -> None:
        pass

    bus.subscribe("hit", listener)
    bus.unsubscribe("hit", other)
    bus.publish("hit", 5)

    assert calls == [5]


def test_event_bus_does_not_retain_bound_method_owner(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    bus = EventBus()
    calls: list[int] = []

    class Listener:
        def on_value(self, value: int) -> None:
            calls.append(value)

    listener = Listener()
    listener_ref = weakref.ref(listener)

    bus.subscribe("tick", listener.on_value)
    bus.publish("tick", 1)
    assert calls == [1]

    del listener
    gc.collect()

    assert listener_ref() is None

    bus.publish("tick", 2)
    assert calls == [1]


def test_input_load_map_and_action_queries(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _ = isolated_registry

    state = {
        "pressed": set(),
        "repeat": set(),
        "down": set(),
        "released": set(),
        "up": set(),
    }

    fake_pr = SimpleNamespace(
        is_key_pressed=lambda key: key in state["pressed"],
        is_key_pressed_repeat=lambda key: key in state["repeat"],
        is_key_down=lambda key: key in state["down"],
        is_key_released=lambda key: key in state["released"],
        is_key_up=lambda key: key in state["up"],
    )

    monkeypatch.setattr(keyboard_module, "pr", fake_pr)

    input_service = input_module.Input()

    config_path = tmp_path / "input.json"
    config_path.write_text('{"left": [1], "right": [2], "jump": [3, 4]}')

    input_service.load(config_path)

    assert input_service.actions["left"] == {1}
    assert input_service.actions["right"] == {2}
    assert input_service.actions["jump"] == {3, 4}

    state["pressed"] = {1}
    assert input_service.is_pressed("left") is True
    assert input_service.is_pressed("right") is False

    state["down"] = {1}
    assert input_service.get_axis("left", "right") == -1.0

    state["down"] = {2}
    assert input_service.get_axis("left", "right") == 1.0

    state["down"] = {1, 2}
    assert input_service.get_axis("left", "right") == 0.0

    state["repeat"] = {3}
    assert input_service.is_pressed_repeat("jump") is True

    state["down"] = {4}
    assert input_service.is_down("jump") is True

    state["released"] = {2}
    assert input_service.is_released("right") is True

    state["up"] = {1}
    assert input_service.is_up("left") is True

    input_service.unmap("jump", 3)
    assert input_service.actions["jump"] == {4}

    input_service.unmap("jump", 4)
    assert "jump" not in input_service.actions

    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        input_service.load(missing)

    invalid_path = tmp_path / "input.txt"
    invalid_path.write_text("{}")
    with pytest.raises(ValueError, match="JSON"):
        input_service.load(invalid_path)

    ini_path = tmp_path / "input.ini"
    ini_path.write_text("[keys]\nleft=1")
    with pytest.raises(ValueError, match="JSON"):
        input_service.load(ini_path)


def test_mouse_update_and_cursor_controls(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    state = {
        "mouse_pos": FakeVector2(0.0, 0.0),
        "moves": [],
        "hidden": 0,
        "shown": 0,
        "disabled": 0,
    }

    def set_mouse_position(x: int, y: int) -> None:
        state["moves"].append((x, y))

    def hide_cursor() -> None:
        state["hidden"] += 1

    def show_cursor() -> None:
        state["shown"] += 1

    def disable_cursor() -> None:
        state["disabled"] += 1

    fake_pr = SimpleNamespace(
        Vector2=FakeVector2,
        get_mouse_position=lambda: state["mouse_pos"],
        get_mouse_x=lambda: 11,
        get_mouse_y=lambda: 22,
        set_mouse_position=set_mouse_position,
        hide_cursor=hide_cursor,
        show_cursor=show_cursor,
        disable_cursor=disable_cursor,
        set_mouse_cursor=lambda cursor: None,
    )

    monkeypatch.setattr(mouse_module, "pr", fake_pr)

    mouse = input_module.Mouse()

    state["mouse_pos"] = FakeVector2(5.0, 7.0)
    mouse.update(0.016)

    assert mouse.position[0] == 5.0
    assert mouse.position[1] == 7.0
    assert mouse.movement[0] == 5.0
    assert mouse.movement[1] == 7.0

    assert mouse.x == 11
    assert mouse.y == 22

    mouse.move(3, 4)
    assert state["moves"] == [(3, 4)]

    mouse.hide()
    mouse.show()
    mouse.disable()

    assert state["hidden"] == 1
    assert state["shown"] == 1
    assert state["disabled"] == 1


def test_configure_logging_creates_file_and_handlers(tmp_path) -> None:
    log_path = tmp_path / "plyunit.log"

    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level

    configure_logging("INFO", str(log_path))

    new_handlers = [
        handler for handler in root_logger.handlers if handler not in previous_handlers
    ]

    try:
        root_logger.info("hello")
        for handler in new_handlers:
            if hasattr(handler, "flush"):
                handler.flush()

        assert log_path.exists()
        assert "hello" in log_path.read_text(encoding="utf-8")
    finally:
        for handler in new_handlers:
            root_logger.removeHandler(handler)
            handler.close()
        root_logger.setLevel(previous_level)
