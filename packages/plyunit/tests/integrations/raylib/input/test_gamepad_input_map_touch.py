from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.backends.integrations.raylib.input.gamepad as gamepad_mod
import plyunit.backends.integrations.raylib.input.input as input_mod
from plyunit.backends.integrations.raylib.input.gamepad import Gamepad, _apply_deadzone
from plyunit.backends.integrations.raylib.input.input import Input

unit_module = __import__("plyunit.core.units.unit", fromlist=["units"])


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_apply_deadzone() -> None:
    assert _apply_deadzone(0.1, 0.15) == 0.0
    assert _apply_deadzone(0.5, 0.15) == 0.5


def test_gamepad_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        "available": True,
        "pressed": set(),
        "down": set(),
        "released": set(),
        "axes": {},
        "name": "FakePad",
        "vib": [],
    }
    a = gamepad_mod.MAP_GAMEPAD_BUTTONS["a"]
    lx = gamepad_mod.MAP_GAMEPAD_AXES["left_x"]
    ly = gamepad_mod.MAP_GAMEPAD_AXES["left_y"]

    monkeypatch.setattr(
        gamepad_mod,
        "pr",
        SimpleNamespace(
            is_gamepad_available=lambda p: state["available"],
            get_gamepad_name=lambda p: state["name"],
            is_gamepad_button_pressed=lambda p, b: b in state["pressed"],
            is_gamepad_button_down=lambda p, b: b in state["down"],
            is_gamepad_button_released=lambda p, b: b in state["released"],
            is_gamepad_button_up=lambda p, b: b not in state["down"],
            get_gamepad_axis_movement=lambda p, ax: float(state["axes"].get(ax, 0.0)),
            set_gamepad_vibration=lambda p, left, right, d: state["vib"].append(
                (p, left, right, d)
            ),
        ),
    )
    # pyrefly: ignore [bad-instantiation]
    pad = Gamepad(deadzone=0.2)
    state["pressed"] = {a}
    state["down"] = {a}
    assert pad.is_available()
    assert pad.is_pressed("a")
    assert pad.is_down("a")
    assert pad.name_on_device == "FakePad"

    state["axes"][lx] = 0.1
    assert pad.get_axis("left_x") == 0.0
    state["axes"][lx] = 0.8
    state["axes"][ly] = -0.5
    assert pad.get_vector() == (0.8, -0.5)
    pad.set_vibration(0.5, 0.25, duration=0.1)
    assert state["vib"][-1] == (0, 0.5, 0.25, 0.1)

    state["available"] = False
    assert not pad.is_available()
    assert pad.get_axis("left_x") == 0.0


def test_input_keyboard_only(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = pu.EventBus()
    isolated_registry.register(bus)
    state = {"pressed": set(), "down": set(), "released": set(), "repeat": set()}
    monkeypatch.setattr(
        input_mod,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: k in state["pressed"],
            is_key_down=lambda k: k in state["down"],
            is_key_released=lambda k: k in state["released"],
            is_key_pressed_repeat=lambda k: k in state["repeat"],
            is_key_up=lambda k: k not in state["down"],
        ),
    )
    inp = Input(emit_to_bus=True)
    isolated_registry.register(inp)
    inp.map("jump", 32)

    received: list[str] = []
    bus.subscribe("key.jump.pressed", lambda **kw: received.append("p"))
    bus.subscribe("key.jump.down", lambda **kw: received.append("d"))
    state["pressed"] = {32}
    state["down"] = {32}
    assert inp.is_pressed("jump")
    assert inp.is_down("jump")
    app = SimpleNamespace(
        is_first_fixed_step=True,
        one_or_none=lambda ref, scope="global": bus if ref == "@EventBus" else None,
    )
    inp.on_attach(app)
    inp.update(0.016)
    bus.dispatch()
    assert "p" in received and "d" in received


def test_input_virtual_axis_from_keys(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry
    state = {"pressed": set(), "down": set(), "released": set(), "repeat": set()}
    monkeypatch.setattr(
        input_mod,
        "pr",
        SimpleNamespace(
            is_key_pressed=lambda k: k in state["pressed"],
            is_key_down=lambda k: k in state["down"],
            is_key_released=lambda k: k in state["released"],
            is_key_pressed_repeat=lambda k: k in state["repeat"],
            is_key_up=lambda k: k not in state["down"],
        ),
    )
    inp = Input()
    inp.map_axis("move_x", key_neg=[65], key_pos=[68])

    state["down"] = {65}
    assert inp.get_axis("move_x") == -1.0
    state["down"] = set()
    state["down"] = {68}
    assert inp.get_axis("move_x") == 1.0
    state["down"] = {65, 68}
    assert inp.get_axis("move_x") == 0.0
    state["down"] = set()
    assert inp.get_axis("move_x") == 0.0
    assert inp.get_axis("unmapped") == 0.0


def test_touch_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    import plyunit.backends.integrations.raylib.input.touch as touch_mod
    from plyunit.backends.integrations.raylib.input.touch import Touch

    state = {"count": 0, "x": 0.0, "y": 0.0}

    class Pos:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    monkeypatch.setattr(
        touch_mod,
        "pr",
        SimpleNamespace(
            get_touch_point_count=lambda: state["count"],
            get_touch_position=lambda i: Pos(state["x"], state["y"]),
        ),
    )
    touch = Touch()
    touch.update(0.016)
    assert not touch.is_down()

    state["count"] = 1
    state["x"], state["y"] = 12.0, 34.0
    touch.update(0.016)
    assert touch.is_down() and touch.is_pressed()
    assert touch.position == (12.0, 34.0)

    state["count"] = 0
    touch.update(0.016)
    assert touch.is_released()


def test_unknown_button_raises() -> None:
    # pyrefly: ignore [bad-instantiation]
    pad = Gamepad()
    with pytest.raises(ValueError, match="Unknown gamepad button"):
        # will call pr — monkeypatch not needed if we raise before pr on unknown name
        pad.is_down("not_a_button")


def test_input_alias() -> None:
    # No Keyboard alias any more — Input is the only class.
    from plyunit.backends.integrations.raylib.input import Input

    assert Input.__name__ == "Input"
