from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.core.app as app_module
import plyunit.core.schema_config as schema_config_module

unit_module = importlib.import_module("plyunit.core.units.unit")


class StubRenderer:
    def __init__(self, canvas, strict_mode: bool = True) -> None:

        self.canvas = canvas
        self.strict_mode = strict_mode
        self.reset_frame_calls = 0
        self.flush_all_calls = 0
        self.flush_all_args: list[object | None] = []
        self.events: list[object] | None = None
        self.shutdown_calls = 0

    def reset_frame(self) -> None:
        self.reset_frame_calls += 1

    def init(self) -> None:
        return

    def flush_all(self, camera=None) -> None:
        self.flush_all_calls += 1
        self.flush_all_args.append(camera)
        if self.events is not None:
            self.events.append(("flush_all", camera))

    def get_pass(self, name: str) -> object | None:
        return SimpleNamespace(clear_color=None, camera=None, viewport_scissor=None)

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class TrackingApp(app_module.App):
    default_window: object | None = None

    def __init__(self) -> None:
        super().__init__()
        canvas = SimpleNamespace(name="canvas", clear_background=lambda color: None)
        renderer = StubRenderer(canvas)
        # pyrefly: ignore [bad-assignment]
        self.window = TrackingApp.default_window
        # pyrefly: ignore [bad-assignment]
        self.canvas = canvas
        # pyrefly: ignore [bad-assignment]
        self.renderer = renderer
        self.fixed_update_calls: list[tuple[float, int]] = []
        self.update_calls: list[float] = []

    def fixed_update(self, dt: float, step: int) -> None:
        self.fixed_update_calls.append((dt, step))
        # Mirror the documented pattern: the user drives the scene tree.
        if self.scene_manager is not None:
            self.scene_manager.update(dt)
            self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        self.update_calls.append(dt)


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


@pytest.fixture(autouse=True)
def app_rl(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    state: dict[str, object] = {
        "init_window": [],
        "target_fps": [],
        "close_window": 0,
        "begin_drawing": 0,
        "end_drawing": 0,
        "clear_background": [],
        "frame_time": 0.016,
        "window_should_close_seq": [True],
    }

    def init_window(width: int, height: int, title: str) -> None:
        entries = state["init_window"]
        assert isinstance(entries, list)
        entries.append((width, height, title))

    def set_target_fps(fps: int) -> None:
        entries = state["target_fps"]
        assert isinstance(entries, list)
        entries.append(fps)

    def get_frame_time() -> float:
        # pyrefly: ignore [bad-argument-type]
        return float(state["frame_time"])

    def window_should_close() -> bool:
        seq = state["window_should_close_seq"]
        assert isinstance(seq, list)
        if seq:
            return bool(seq.pop(0))
        return True

    def close_window() -> None:
        # pyrefly: ignore [bad-argument-type]
        state["close_window"] = int(state["close_window"]) + 1

    def begin_drawing() -> None:
        # pyrefly: ignore [bad-argument-type]
        state["begin_drawing"] = int(state["begin_drawing"]) + 1

    def end_drawing() -> None:
        # pyrefly: ignore [bad-argument-type]
        state["end_drawing"] = int(state["end_drawing"]) + 1

    def clear_background(color) -> None:
        entries = state["clear_background"]
        assert isinstance(entries, list)
        entries.append(color)

    def start_frame() -> None:
        raw_dt = min(max(get_frame_time(), 0.0), fake_window.max_frame_delta_time)
        fake_window.unscaled_dt = raw_dt
        fake_window.dt = raw_dt * fake_window.time_scale
        fake_window.total_time += raw_dt
        fake_window.frame_count += 1
        fake_window.accumulator += fake_window.dt

    def consume_fixed_steps(max_steps: int) -> int:
        steps = 0
        while (
            fake_window.accumulator >= fake_window.fixed_delta_time
            and steps < max_steps
        ):
            fake_window.accumulator -= fake_window.fixed_delta_time
            steps += 1
        if (
            steps == max_steps
            and fake_window.accumulator >= fake_window.fixed_delta_time
        ):
            fake_window.accumulator = 0.0
        fake_window.alpha = fake_window.accumulator / fake_window.fixed_delta_time
        fake_window.fixed_steps += steps
        return steps

    def set_fixed_timestep_hz(hz: int) -> None:
        fake_window.fixed_delta_time = 1.0 / hz

    fake_window = SimpleNamespace(
        RAYWHITE=(245, 245, 245, 255),
        dt=0.0,
        unscaled_dt=0.0,
        total_time=0.0,
        frame_count=0,
        time_scale=1.0,
        fixed_delta_time=1.0 / 60.0,
        max_frame_delta_time=0.25,
        accumulator=0.0,
        alpha=0.0,
        fixed_steps=0,
        init_window=init_window,
        set_target_fps=set_target_fps,
        get_frame_time=get_frame_time,
        window_should_close=window_should_close,
        close_window=close_window,
        begin_drawing=begin_drawing,
        clear_background=clear_background,
        end_drawing=end_drawing,
        start_frame=start_frame,
        consume_fixed_steps=consume_fixed_steps,
        set_fixed_timestep_hz=set_fixed_timestep_hz,
    )

    TrackingApp.default_window = fake_window
    return state


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"window_width": 0}, "window size must be greater than zero"),
        ({"window_height": 0}, "window size must be greater than zero"),
        ({"target_fps": -1}, "target_fps must be >= 0"),
        ({"fixed_update_hz": 0}, "fixed_update_hz must be > 0"),
        ({"max_frame_delta_time": 0.0}, "max_frame_delta_time must be > 0"),
    ],
)
def test_app_config_validate_error_paths(
    overrides: dict[str, object], message: str
) -> None:
    cfg = app_module.AppConfig()
    for key, value in overrides.items():
        setattr(cfg, key, value)

    with pytest.raises(ValueError, match=message):
        cfg.validate()


def test_app_config_from_dict_and_from_file(monkeypatch: pytest.MonkeyPatch) -> None:
    config = app_module.AppConfig.from_dict(
        {
            "title": "Test",
            "window_width": 1024,
            "window_height": 720,
            "target_fps": 0,
            "fixed_update_hz": 120,
            "max_frame_delta_time": 0.2,
            "max_substeps_per_frame": 8,
            "background_color": (1, 2, 3, 255),
        }
    )

    assert config.title == "Test"
    assert config.window_width == 1024
    assert config.fixed_update_hz == 120

    with pytest.raises(ValueError, match="Failed to create AppConfig from dict"):
        app_module.AppConfig.from_dict({"unknown": 1})

    monkeypatch.setattr(
        schema_config_module,
        "read_json",
        lambda path: {
            "title": "FileConfig",
            "window_width": 640,
            "window_height": 360,
            "target_fps": 30,
            "fixed_update_hz": 30,
            "max_frame_delta_time": 0.1,
            "max_substeps_per_frame": 4,
        },
    )

    from_file = app_module.AppConfig.from_file("config.json")
    assert from_file.title == "FileConfig"

    monkeypatch.setattr(
        schema_config_module,
        "read_json",
        lambda _path: (_ for _ in ()).throw(OSError("missing")),
    )
    with pytest.raises(ValueError, match="Failed to load AppConfig from file"):
        app_module.AppConfig.from_file("missing.json")


def test_app_init_accepts_object_string_and_default(
    app_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    init_emits: list[str] = []

    app = TrackingApp()
    app.on_init_complete.connect(lambda: init_emits.append("object"))
    app.init(
        app_module.AppConfig(
            title="Obj",
            window_width=800,
            window_height=600,
            target_fps=30,
            fixed_update_hz=120,
            max_frame_delta_time=0.1,
        )
    )

    assert app.window is not None
    assert math.isclose(app.window.fixed_delta_time, 1.0 / 120.0)
    assert math.isclose(app.window.max_frame_delta_time, 0.1)

    init_window_calls = app_rl["init_window"]
    target_fps_calls = app_rl["target_fps"]
    assert isinstance(init_window_calls, list)
    assert isinstance(target_fps_calls, list)
    assert init_window_calls[0] == (800, 600, "Obj")
    assert target_fps_calls[0] == 30

    from_file_calls: list[str] = []

    def fake_from_file(path: str) -> app_module.AppConfig:
        from_file_calls.append(path)
        return app_module.AppConfig(title="FromFile", target_fps=0, fixed_update_hz=20)

    monkeypatch.setattr(
        app_module.AppConfig,
        "from_file",
        classmethod(lambda cls, path: fake_from_file(path)),
    )

    second = TrackingApp()
    second.init("settings.json")

    assert from_file_calls == ["settings.json"]
    # pyrefly: ignore [missing-attribute]
    assert second.config.title == "FromFile"

    third = TrackingApp()
    third.init()
    # pyrefly: ignore [missing-attribute]
    assert third.config.title == "Plyunit Game"

    assert init_emits == ["object"]


def test_app_begin_end_update_and_fixed_steps(app_rl: dict[str, object]) -> None:
    _ = app_rl
    app = TrackingApp()
    app.config = app_module.AppConfig(max_substeps_per_frame=5)

    signals: list[str] = []
    app.on_start_frame.connect(lambda: signals.append("start_frame"))
    app.on_end_frame.connect(lambda: signals.append("end_frame"))
    app.on_fixed_update.connect(lambda dt: signals.append("fixed"))
    app.on_begin_update.connect(lambda dt: signals.append("begin_update"))
    app.on_end_update.connect(lambda dt: signals.append("end_update"))
    app.on_after_update.connect(lambda dt: signals.append("after_update"))

    class SceneManager:
        def __init__(self) -> None:
            self.update_calls: list[float] = []
            self.apply_pending_calls: int = 0

        def begin_step(self) -> None:
            return

        def end_step(self) -> None:
            return

        def apply_pending(self) -> None:
            self.apply_pending_calls += 1

        def update(self, dt: float) -> None:
            self.update_calls.append(dt)

    scene_manager = SceneManager()
    app.scene_manager = scene_manager

    assert app.window is not None
    app.window.set_fixed_timestep_hz(10)
    app.window.accumulator = 0.31

    app._start_frame()
    steps = app.step_fixed()
    app._end_frame()

    assert signals[0] == "start_frame"
    assert signals[-1] == "end_frame"
    assert steps == 3
    assert app._last_fixed_steps == 3
    assert app.fixed_update_calls == [(0.1, 0), (0.1, 1), (0.1, 2)]
    assert scene_manager.update_calls == [0.1, 0.1, 0.1]
    assert scene_manager.apply_pending_calls == 3
    # update() is per-frame (called by run()), not per-substep.
    assert app.update_calls == []


def test_app_fixed_step_index_during_catchup(app_rl: dict[str, object]) -> None:
    _ = app_rl
    app = TrackingApp()
    app.config = app_module.AppConfig(max_substeps_per_frame=5)

    indices: list[int] = []
    first_flags: list[bool] = []

    def on_begin(dt: float) -> None:
        _ = dt
        indices.append(app.fixed_step_index)
        first_flags.append(app.is_first_fixed_step)

    app.on_begin_update.connect(on_begin)
    assert app.window is not None
    app.window.set_fixed_timestep_hz(10)
    app.window.accumulator = 0.31

    app._start_frame()
    app.step_fixed()

    assert app._last_fixed_steps == 3
    assert indices == [0, 1, 2]
    assert first_flags == [True, False, False]


def test_app_run_owns_no_render_pipeline(app_rl: dict[str, object]) -> None:
    """run() never renders: update(dt) is the only per-frame user hook."""
    _ = app_rl
    app = TrackingApp()
    app.config = app_module.AppConfig()
    app_rl["window_should_close_seq"] = [False]
    app_rl["frame_time"] = 0.02
    renderer = app.renderer

    app.run()

    # One frame ran: fixed substep + one per-frame update call.
    assert app.update_calls == [0.02]
    assert [step for _dt, step in app.fixed_update_calls] == [0]
    # The engine never touched the render pipeline.
    # pyrefly: ignore [missing-attribute]
    assert renderer.reset_frame_calls == 0
    # pyrefly: ignore [missing-attribute]
    assert renderer.flush_all_calls == 0
    assert app_rl["begin_drawing"] == 0
    assert app_rl["end_drawing"] == 0


def test_app_update_is_engine_invoked_and_draw_removed() -> None:
    assert callable(getattr(app_module.App, "fixed_update", None))
    assert callable(getattr(app_module.App, "update", None))
    assert not hasattr(app_module.App, "draw")
    assert not hasattr(app_module.App, "on_render")
    assert not hasattr(app_module.App, "render_submit")
    assert not hasattr(app_module.App, "_render_frame")


def test_removed_late_update_api_is_absent() -> None:
    for owner in (
        app_module.App,
        pu.SceneManager,
        pu.SceneUnit,
        pu.NodeUnit,
        pu.Component,
    ):
        assert not hasattr(owner, "late_update")

    app = TrackingApp()
    component = pu.Component()
    assert not hasattr(app, "on_begin_late_update")
    assert not hasattr(app, "on_end_late_update")
    assert not hasattr(component, "late_updates")
    assert not hasattr(app, "on_begin_render")
    assert not hasattr(app, "on_end_render")
    assert not hasattr(pu.SceneManager, "begin_fixed_step")
    assert not hasattr(pu.SceneManager, "end_fixed_step")
    assert not hasattr(pu.SceneManager, "render_submit")
    assert not hasattr(pu.SceneManager, "request_switch")


def test_app_run_requires_config(
    app_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = TrackingApp()
    load_calls: list[None] = []
    monkeypatch.setattr(app, "on_load", lambda: load_calls.append(None))

    with pytest.raises(RuntimeError, match="AppConfig must be set"):
        app.run()

    assert load_calls == []
    assert app_rl["close_window"] == 0


def test_app_quit_stops_after_current_frame(app_rl: dict[str, object]) -> None:
    app = TrackingApp()
    app.config = app_module.AppConfig()
    app_rl["window_should_close_seq"] = [False, False]
    app_rl["frame_time"] = 0.02
    renders: list[float] = []
    renderer = app.renderer
    fixed_dt = app.window.fixed_delta_time

    def update(dt: float) -> None:
        renders.append(dt)
        app.quit()

    app.update = update  # type: ignore[method-assign]
    app.run()

    assert renders == [0.02]
    assert app.fixed_update_calls == [(fixed_dt, 0)]
    # pyrefly: ignore [missing-attribute]
    assert renderer.reset_frame_calls == 0
    # pyrefly: ignore [missing-attribute]
    assert renderer.flush_all_calls == 0
    assert app.running is False
    assert app_rl["close_window"] == 1
    # pyrefly: ignore [missing-attribute]
    assert app.renderer is None


def test_app_shutdown_order_and_idempotence(app_rl: dict[str, object]) -> None:
    events: list[str] = []

    class LifecycleApp(TrackingApp):
        def on_unload(self) -> None:
            events.append("app")

    class Owned:
        def __init__(self, label: str, method: str) -> None:
            setattr(self, method, lambda: events.append(label))

    class Service(pu.ServiceUnit):
        def __init__(self) -> None:
            super().__init__(name="service")

        def on_detach(self, app) -> None:
            _ = app
            events.append("service")

    app = LifecycleApp()
    app.config = app_module.AppConfig()
    app.scene_manager = Owned("scenes", "shutdown")
    app.animations = Owned("animations", "clear")
    app.assets = Owned("assets", "clear_all")
    app.renderer = Owned("renderer", "shutdown")
    Service()

    app.shutdown()
    app.shutdown()

    assert events == [
        "scenes",
        "app",
        "service",
        "animations",
        "assets",
        "renderer",
    ]
    assert app_rl["close_window"] == 1


def test_app_preserves_loop_error_when_shutdown_fails(
    app_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = TrackingApp()
    app.config = app_module.AppConfig()
    app_rl["window_should_close_seq"] = [False]
    monkeypatch.setattr(
        app,
        "update",
        lambda dt: (_ for _ in ()).throw(RuntimeError("loop failed")),
    )
    monkeypatch.setattr(
        app.renderer,
        "shutdown",
        lambda: (_ for _ in ()).throw(RuntimeError("shutdown failed")),
    )

    with pytest.raises(RuntimeError, match="loop failed"):
        app.run()

    assert app_rl["close_window"] == 1


def test_app_run_loop_handles_internal_exception_and_closes_window(
    app_rl: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = TrackingApp()
    app.config = app_module.AppConfig()
    app_rl["window_should_close_seq"] = [False, False, True]

    monkeypatch.setattr(app, "on_load", lambda: None)

    calls: list[str] = []

    state = {"first": True}

    def start_frame() -> None:
        calls.append("begin")
        if state["first"]:
            state["first"] = False
            raise RuntimeError("boom")

    monkeypatch.setattr(app, "_start_frame", start_frame)
    monkeypatch.setattr(app, "_end_frame", lambda: calls.append("end"))

    with pytest.raises(RuntimeError, match="boom"):
        app.run()

    assert calls == ["begin"]
    assert app.running is False
    assert app_rl["close_window"] == 1
