from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.backends.integrations.raylib.input.gamepad as gamepad_mod
import plyunit.backends.integrations.raylib.input.input as input_mod
from plyunit.backends.integrations.raylib.input.gamepad import Gamepad, apply_deadzone
from plyunit.backends.integrations.raylib.input.input import Input

unit_module = __import__("plyunit.core.units.unit", fromlist=["units"])


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_apply_deadzone() -> None:
    assert apply_deadzone(0.1, 0.15) == 0.0
    assert apply_deadzone(0.5, 0.15) == 0.5


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
    a = gamepad_mod.GAMEPAD_BUTTONS["a"]
    lx = gamepad_mod.GAMEPAD_AXES["left_x"]
    ly = gamepad_mod.GAMEPAD_AXES["left_y"]

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
    inp = Input()
    isolated_registry.register(inp)
    inp.map("jump", 32)

    received: list[str] = []
    bus.subscribe("key.jump.pressed", lambda **kw: received.append("p"))
    bus.subscribe("key.jump.down", lambda **kw: received.append("d"))
    state["pressed"] = {32}
    state["down"] = {32}
    assert inp.is_pressed("jump")
    assert inp.is_down("jump")
    inp.update(0.016)
    bus.dispatch()
    assert "p" in received and "d" in received


def test_input_with_gamepad(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = gamepad_mod.GAMEPAD_BUTTONS["a"]
    lx = gamepad_mod.GAMEPAD_AXES["left_x"]
    pad_state = {
        "available": True,
        "pressed": set(),
        "down": set(),
        "released": set(),
        "axes": {},
    }
    key_state = {"pressed": set(), "down": set(), "released": set(), "repeat": set()}

    def pr_ns(**extra):
        base = {
            "is_key_pressed": lambda k: k in key_state["pressed"],
            "is_key_down": lambda k: k in key_state["down"],
            "is_key_released": lambda k: k in key_state["released"],
            "is_key_pressed_repeat": lambda k: k in key_state["repeat"],
            "is_key_up": lambda k: k not in key_state["down"],
            "is_gamepad_available": lambda p: pad_state["available"],
            "get_gamepad_name": lambda p: "pad",
            "is_gamepad_button_pressed": lambda p, b: b in pad_state["pressed"],
            "is_gamepad_button_down": lambda p, b: b in pad_state["down"],
            "is_gamepad_button_released": lambda p, b: b in pad_state["released"],
            "is_gamepad_button_up": lambda p, b: b not in pad_state["down"],
            "get_gamepad_axis_movement": lambda p, ax: float(
                pad_state["axes"].get(ax, 0.0)
            ),
            "set_gamepad_vibration": lambda *a: None,
        }
        base.update(extra)
        return SimpleNamespace(**base)

    monkeypatch.setattr(input_mod, "pr", pr_ns())
    monkeypatch.setattr(gamepad_mod, "pr", pr_ns())

    # pyrefly: ignore [bad-instantiation]
    pad = Gamepad()
    isolated_registry.register(pad)
    inp = Input(gamepad=pad)
    isolated_registry.register(inp)
    inp.map("jump", 32, buttons=["a"])
    inp.map_axis(
        "move_x",
        key_neg=[65],
        key_pos=[68],
        pad_axis="left_x",
        pad_buttons_neg=["dpad_left"],
        pad_buttons_pos=["dpad_right"],
        deadzone=0.15,
    )

    key_state["pressed"] = {32}
    assert inp.is_pressed("jump")
    key_state["pressed"] = set()
    pad_state["pressed"] = {a}
    assert inp.is_pressed("jump")

    key_state["down"] = {65}
    assert inp.get_axis("move_x") == -1.0
    key_state["down"] = set()
    pad_state["axes"][lx] = 0.9
    assert inp.get_axis("move_x") == 0.9
    pad_state["axes"][lx] = 0.0
    dpad_r = gamepad_mod.GAMEPAD_BUTTONS["dpad_right"]
    pad_state["down"] = {dpad_r}
    assert inp.get_axis("move_x") == 1.0


def test_input_json_roundtrip(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry
    inp = Input(gamepad=True)
    inp.map("jump", 32, buttons=["a"])
    inp.map_axis("move_x", key_neg=[65], key_pos=[68], pad_axis="left_x")
    path = tmp_path / "bindings.json"
    inp.save(path)
    other = Input(gamepad=True)
    other.load(path)
    assert 32 in other.actions["jump"]
    assert "a" in other._buttons["jump"]
    assert "move_x" in other._axes

    flat = tmp_path / "flat.json"
    flat.write_text('{"shoot": [17]}', encoding="utf-8")
    other.load(flat)
    assert 17 in other.actions["shoot"]

    ini = tmp_path / "x.ini"
    ini.write_text("[x]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        other.load(ini)


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
