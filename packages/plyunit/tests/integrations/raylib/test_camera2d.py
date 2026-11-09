from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.camera2d as camera2d_module
from plyunit.backends.ports.camera2d import ICamera2D
from plyunit.core.units.node_unit import NodeUnit
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    """Keep camera service instances isolated from other tests.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        The test registry.
    """
    registry = UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", registry
    )
    return registry


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
    def __init__(
        self, offset=None, target=None, rotation: float = 0.0, zoom: float = 1.0
    ):
        if offset is None:
            offset = FakeVector2(0.0, 0.0)
        if target is None:
            target = FakeVector2(0.0, 0.0)
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
    assert isinstance(camera, ICamera2D)
    with pytest.raises(RuntimeError, match=r"call setup\(\)"):
        camera.start_frame()
    camera.setup(1000, 800)
    assert camera._camera is not None
    camera.start_frame()
    camera.end_frame()
    assert camera_rl["end_calls"] == 1


def test_camera2d_set_target_zoom_and_resize(camera_rl: dict[str, object]) -> None:
    camera = camera2d_module.Camera2D(size=(320, 240), position=(0.0, 0.0))
    camera.setup(800, 600)
    node = NodeUnit(name="TargetNode")
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

    camera.teleport((0.0, 0.0))
    camera.update(0.0)
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


def test_noninstant_teleport_keeps_current_position(
    camera_rl: dict[str, object],
) -> None:
    """A non-instant teleport changes the target without snapping the camera."""
    camera = camera2d_module.Camera2D(
        size=(320, 240), position=(0.0, 0.0), slowness=2.0
    )
    camera.setup(640, 480)
    camera.teleport((100.0, 50.0), instant=False)
    assert camera.pos == [0.0, 0.0]
    assert camera._camera.target.x == 0.0
    assert camera._camera.target.y == 0.0
    camera.update(0.5)
    assert camera.pos == pytest.approx([25.0, 12.5])


def test_virtual_size_can_change_before_setup(camera_rl: dict[str, object]) -> None:
    """Virtual-size changes do not dereference an uninitialized native camera."""
    camera = camera2d_module.Camera2D(size=(320, 240))
    camera.set_virtual_size(640, 360)
    assert camera._camera is None
    camera.setup(1280, 720)
    assert camera.calculate_zoom() == 2.0
    assert camera.viewport == (0.0, 0.0, 1280.0, 720.0)


def test_setup_updates_each_optional_window_dimension(
    camera_rl: dict[str, object],
) -> None:
    """A partially specified window size updates just that stored dimension."""
    camera = camera2d_module.Camera2D(size=(320, 240))
    camera.setup(800, 600)
    native = camera._camera
    camera.setup(window_width=1000)
    assert camera._window_size == (1000, 600)
    assert camera._camera is native
    with pytest.raises(ValueError, match="positive"):
        camera.setup(window_height=0)
    assert camera._window_size == (1000, 600)


def test_view_bounds_exclude_letterboxing(
    camera_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """World bounds use virtual viewport corners rather than the whole window."""
    camera = camera2d_module.Camera2D(size=(320, 240))
    camera.setup(1000, 800)
    points: list[tuple[float, float]] = []

    def screen_to_world(x: float, y: float) -> tuple[float, float]:
        points.append((x, y))
        return x, y

    monkeypatch.setattr(camera, "screen_to_world", screen_to_world)
    assert camera.get_view_rect() == (0.0, 25.0, 1000.0, 775.0)
    assert len(points) == 4


def test_rotated_view_bounds_use_all_four_corners(
    camera_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rotated bounds include extrema that do not lie on a single diagonal."""
    camera = camera2d_module.Camera2D(size=(320, 240), rotation=45.0)
    camera.setup(640, 480)
    points = iter([(1.0, 2.0), (5.0, -4.0), (-3.0, 8.0), (4.0, 7.0)])
    monkeypatch.setattr(camera, "screen_to_world", lambda x, y: next(points))
    assert camera.get_view_rect() == (-3.0, -4.0, 5.0, 8.0)


@pytest.mark.parametrize("size", [(0, 240), (320, -1)])
def test_invalid_virtual_sizes_are_rejected(
    camera_rl: dict[str, object], size: tuple[int, int]
) -> None:
    """Invalid viewport dimensions fail before camera construction or division."""
    with pytest.raises(ValueError, match="positive"):
        camera2d_module.Camera2D(size=size)
    camera = camera2d_module.Camera2D(size=(320, 240))
    with pytest.raises(ValueError, match="positive"):
        camera.set_virtual_size(*size)


def test_removed_legacy_camera_property_is_absent(camera_rl: dict[str, object]) -> None:
    """The canonical easing parameter is slowness, without legacy aliases."""
    assert not hasattr(camera2d_module.Camera2D(size=(320, 240)), "lerp_speed")
