from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import plyunit.core.app as app_module
from plyunit.backends.ports.imgui import ImGuiPort
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
    cfg = app_module.AppConfig.from_dict({
        "title": "ImGuiCfg",
        "window_width": 640,
        "window_height": 360,
        "imgui": {"enabled": True, "dark_style": False, "no_ini": False},
    })
    assert cfg.imgui.enabled is True
    assert cfg.imgui.dark_style is False
    assert cfg.imgui.no_ini is False


def test_build_imgui_service_from_config() -> None:
    from plyunit.backends.imgui.raylib_integration import ImGui

    cfg = app_module.ImGuiConfig(enabled=True, dark_style=False, no_ini=True)
    svc = ImGui(dark_style=cfg.dark_style, no_ini=cfg.no_ini)
    assert isinstance(svc, ImGui)
    assert isinstance(svc, ImGuiPort)
    assert svc.active is False
    assert svc.context is None
    assert svc._dark_style is False
    assert svc._no_ini is True


def test_imgui_service_draw_callbacks() -> None:
    from plyunit.backends.imgui.raylib_integration import ImGui

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
    svc.remove_draw(panel_a)
    svc.set_draw(panel_b)
    svc.set_draw(None)
    assert svc._draw_callbacks == []


def test_imgui_service_manual_frame_and_detach(monkeypatch: pytest.MonkeyPatch) -> None:
    from plyunit.backends.imgui.raylib_integration import ImGui

    events: list[str | tuple[str, float]] = []
    create_context = Mock(side_effect=lambda: events.append("create_context"))
    destroy_context = Mock(side_effect=lambda: events.append("destroy_context"))
    begin_frame = Mock(side_effect=lambda dt: events.append(("begin_frame", dt)))
    render = Mock(side_effect=lambda: events.append("render"))
    svc = ImGui(dark_style=False, no_ini=True)
    monkeypatch.setattr(svc, "_create_context", create_context)
    monkeypatch.setattr(svc, "_destroy_context", destroy_context)
    monkeypatch.setattr(svc, "_begin_frame", begin_frame)
    monkeypatch.setattr(svc, "_render", render)

    app = Mock(spec=app_module.App, window=SimpleNamespace(dt=0.016))
    svc.set_draw(lambda: events.append("draw"))
    svc.frame()
    assert events == []

    svc.on_attach(app)
    create_context.assert_called_once_with()
    assert svc._app is app
    assert svc.active is True

    svc.frame()
    begin_frame.assert_called_once_with(0.016)
    render.assert_called_once_with()
    assert events == ["create_context", ("begin_frame", 0.016), "draw", "render"]

    events.clear()
    svc.frame(0.033)
    begin_frame.assert_called_with(0.033)
    assert events == [("begin_frame", 0.033), "draw", "render"]

    svc.on_detach(app)
    destroy_context.assert_called_once_with()
    assert svc.active is False
    assert svc._app is None

    events.clear()
    svc.frame()
    assert events == []
    assert begin_frame.call_count == 2
    assert render.call_count == 2


def test_imgui_service_default_dt_without_window() -> None:
    from plyunit.backends.imgui.raylib_integration import ImGui

    svc = ImGui()
    assert svc._default_dt() == 0.0
    svc._app = Mock(spec=app_module.App, window=None)
    assert svc._default_dt() == 0.0
