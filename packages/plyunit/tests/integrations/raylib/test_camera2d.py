from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.backends.integrations.raylib.core.camera2d as camera2d_module


class FakeVector2:
    def __init__(self, x=0.0, y=0.0):
        if isinstance(x, tuple):
            x, y = x
        self.x = float(x)
        self.y = float(y)


class FakeRectangle:
    def __init__(self, x: float, y: float, width: float, height: float):
        self.x = float(x)
        self.y = float(y)
        self.width = float(width)
        self.height = float(height)


class FakeCameraObject:
    def __init__(self, offset, target, rotation: float, zoom: float):
        if isinstance(offset, tuple):
            self.offset = FakeVector2(offset[0], offset[1])
        else:
            self.offset = offset
        if isinstance(target, tuple):
            self.target = FakeVector2(target[0], target[1])
        else:
            self.target = target
        self.rotation = float(rotation)
        self.zoom = float(zoom)


@pytest.fixture()
def camera_rl(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    state: dict[str, object] = {
        "begin_calls": [],
        "end_calls": 0,
        "resized": False,
        "screen_size": (800, 600),
    }

    def begin_mode_2d(camera_obj: object) -> None:
        begin_calls = state["begin_calls"]
        assert isinstance(begin_calls, list)
        begin_calls.append(camera_obj)

    def end_mode_2d() -> None:
        # pyrefly: ignore [bad-argument-type]
        state["end_calls"] = int(state["end_calls"]) + 1

    fake_pr = SimpleNamespace(
        Rectangle=FakeRectangle,
        Camera2D=FakeCameraObject,
        Vector2=FakeVector2,
        begin_mode_2d=begin_mode_2d,
        end_mode_2d=end_mode_2d,
        is_window_resized=lambda: bool(state["resized"]),
        # pyrefly: ignore [bad-index]
        get_screen_width=lambda: int(state["screen_size"][0]),
        # pyrefly: ignore [bad-index]
        get_screen_height=lambda: int(state["screen_size"][1]),
        BLACK=(0, 0, 0, 255),
        draw_rectangle=lambda x, y, w, h, c: None,
    )
    monkeypatch.setattr(camera2d_module, "pr", fake_pr)
    return state


def test_camera2d_setup_begin_end(camera_rl: dict[str, object]) -> None:
    camera = camera2d_module.Camera2D(
        size=(320, 240), position=(5.0, 6.0), rotation=15.0, zoom=2.0
    )
    assert camera.target == (5.0, 6.0)
    with pytest.raises(RuntimeError, match=r"Panggil setup\(\)"):
        camera.start_frame()
    camera.setup(1000, 800)
    assert camera._camera is not None
    camera.start_frame()
    camera.end_frame()
    assert camera_rl["end_calls"] == 1


def test_camera2d_set_target_zoom_and_resize(camera_rl: dict[str, object]) -> None:
    camera = camera2d_module.Camera2D(size=(320, 240), position=(0.0, 0.0))
    camera.setup(800, 600)
    node = pu.NodeUnit(name="TargetNode")
    node.transform.world.position = (11.0, 22.0)
    camera.set_target(node)
    assert camera.target == (11.0, 22.0)
    camera.set_target((3.0, 4.0))
    assert camera.target == (3.0, 4.0)
    camera.set_zoom(-10.0)
    assert math.isclose(camera._zoom, 0.0)
    camera_rl["resized"] = True
    camera_rl["screen_size"] = (1200, 700)
    camera.update(0.016)
    assert camera._offset == (600.0, 350.0)


def test_camera2d_smooth_follow_clamp_and_dead_zone(
    camera_rl: dict[str, object],
) -> None:
    camera = camera2d_module.Camera2D(
        size=(320, 240), position=(0.0, 0.0), slowness=1.0
    )
    camera.setup(640, 480)
    camera.set_target((10.0, 5.0))
    camera.update(1.0)
    assert math.isclose(camera.pos[0], 10.0)
    assert math.isclose(camera.pos[1], 5.0)

    camera.teleport((0.0, 0.0), instant=False)
    camera.set_dead_zone(4.0, 4.0)
    camera.set_target((1.0, 1.0))
    camera.update(1.0)
    # inside dead zone → stay
    assert math.isclose(camera.pos[0], 0.0)
    assert math.isclose(camera.pos[1], 0.0)

    camera.set_target((5.0, -5.0))
    camera.update(1.0)
    # outside: approach edge of dead zone
    assert math.isclose(camera.pos[0], 3.0)
    assert math.isclose(camera.pos[1], -3.0)

    camera.clear_dead_zone()
    camera.set_limits(0.0, 0.0, 2.0, 1.0)
    camera.slowness = 0.0
    camera.set_target((10.0, 10.0))
    camera.update(0.016)
    assert math.isclose(camera.pos[0], 2.0)
    assert math.isclose(camera.pos[1], 1.0)


def test_camera2d_teleport(camera_rl: dict[str, object]) -> None:
    camera = camera2d_module.Camera2D(
        size=(320, 240), position=(0.0, 0.0), slowness=5.0
    )
    camera.setup(640, 480)
    camera.teleport((50.0, 60.0))
    assert math.isclose(camera.pos[0], 50.0)
    # pyrefly: ignore [missing-attribute]
    assert math.isclose(camera._camera.target.x, 50.0)
