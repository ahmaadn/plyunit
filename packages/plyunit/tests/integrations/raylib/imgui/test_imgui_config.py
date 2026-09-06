from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import plyunit.core.app as app_module
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


def test_imgui_config_defaults() -> None:
    cfg = app_module.ImGuiConfig()
    assert cfg.enabled is False
    assert cfg.dark_style is True
    assert cfg.no_ini is True
    cfg.validate()


def test_app_config_includes_imgui() -> None:
    cfg = app_module.AppConfig()
    assert isinstance(cfg.imgui, app_module.ImGuiConfig)
    assert cfg.imgui.enabled is False


def test_app_config_from_dict_nested_imgui() -> None:
    cfg = app_module.AppConfig.from_dict(
        {
            "title": "ImGuiCfg",
            "window_width": 640,
            "window_height": 360,
            "imgui": {"enabled": True, "dark_style": False, "no_ini": False},
        }
    )
    assert cfg.imgui.enabled is True
    assert cfg.imgui.dark_style is False
    assert cfg.imgui.no_ini is False


def test_build_imgui_service_from_config() -> None:
    from plyunit.backends.imgui.raylib import ImGui, build_imgui_service

    svc = build_imgui_service(
        app_module.ImGuiConfig(enabled=True, dark_style=False, no_ini=True)
    )
    assert isinstance(svc, ImGui)
    assert svc.active is False


def test_imgui_service_draw_callbacks() -> None:
    from plyunit.backends.imgui.raylib.service import ImGui

    svc = ImGui()
    calls: list[str] = []

    def panel_a() -> None:
        calls.append("a")

    def panel_b() -> None:
        calls.append("b")

    svc.add_draw(panel_a)
    svc.add_draw(panel_b)
    svc.add_draw(panel_a)  # idempotent
    assert len(svc._draw_callbacks) == 2

    for cb in list(svc._draw_callbacks):
        cb()
    assert calls == ["a", "b"]

    svc.remove_draw(panel_a)
    svc.set_draw(panel_b)
    assert svc._draw_callbacks == [panel_b]
    svc.clear_draw()
    assert svc._draw_callbacks == []


def test_imgui_service_manual_frame_and_detach() -> None:
    from plyunit.backends.imgui.raylib.service import ImGui

    class FakeBackend:
        def __init__(self) -> None:
            self.setup_calls = 0
            self.shutdown_calls = 0
            self.new_frame_calls = 0
            self.render_calls = 0
            self.draw_ran = False

        def setup(self, *, dark_style: bool = True, no_ini: bool = True) -> None:
            self.setup_calls += 1
            self.dark_style = dark_style
            self.no_ini = no_ini

        def shutdown(self) -> None:
            self.shutdown_calls += 1

        def new_frame(self, delta_time: float | None = None) -> None:
            self.new_frame_calls += 1
            self.last_dt = delta_time

        def render(self) -> None:
            self.render_calls += 1

        def want_capture_mouse(self) -> bool:
            return False

        def want_capture_keyboard(self) -> bool:
            return False

    backend = FakeBackend()
    # pyrefly: ignore [bad-argument-type]
    svc = ImGui(backend=backend, dark_style=False, no_ini=True)

    app = SimpleNamespace(window=SimpleNamespace(dt=0.016))
    svc.set_draw(lambda: setattr(backend, "draw_ran", True))
    # pyrefly: ignore [bad-argument-type]
    svc.on_attach(app)

    assert backend.setup_calls == 1
    assert svc.active is True

    # Inactive service: frame() is a no-op before attach.
    svc._active = False
    svc.frame()
    assert backend.new_frame_calls == 0
    svc._active = True

    # frame() without dt falls back to app.window.dt.
    svc.frame()
    assert backend.new_frame_calls == 1
    assert backend.last_dt == 0.016
    assert backend.draw_ran is True
    assert backend.render_calls == 1

    # Explicit dt wins.
    svc.frame(0.033)
    assert backend.new_frame_calls == 2
    assert backend.last_dt == 0.033

    # pyrefly: ignore [bad-argument-type]
    svc.on_detach(app)
    assert backend.shutdown_calls == 1
    assert svc.active is False

    # After detach, frame() is a no-op.
    svc.frame()
    assert backend.new_frame_calls == 2
    assert backend.render_calls == 2
