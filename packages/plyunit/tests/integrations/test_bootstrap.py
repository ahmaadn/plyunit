"""Tests for composition using selected backend factories and neutral ports."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import plyunit._bootstrap as bootstrap
from plyunit.core.app import App, AppConfig, AudioConfig, ImGuiConfig, PhysicsConfig
from plyunit.core.units.service_unit import ServiceUnit


@pytest.fixture
def bindings(monkeypatch):
    window, canvas = Mock(), object()
    batch = SimpleNamespace(
        capacity=16384,
        init=lambda *args, **kwargs: None,
        shutdown=lambda: None,
        submit_frame=lambda **kwargs: None,
    )
    factories = {
        "Window": Mock(return_value=window),
        "Canvas2D": Mock(return_value=canvas),
        "UnifiedBufferBatch": Mock(return_value=batch),
        "Assets": Mock(return_value=SimpleNamespace()),
        "Camera2D": Mock(return_value=SimpleNamespace()),
        "Audio": Mock(),
    }
    monkeypatch.setattr(bootstrap, "_load_backend_bindings", lambda: factories)
    return factories


class ConfigOnlyApp(App):
    def init(self, config):
        self.config = config


def test_init_default(bindings, monkeypatch) -> None:
    renderer, scene, animations = object(), object(), object()
    renderer_factory = Mock(return_value=renderer)
    monkeypatch.setattr("plyunit.rendering.renderer.Renderer", renderer_factory)
    monkeypatch.setattr("plyunit.services.scene_manager.SceneManager", lambda: scene)
    monkeypatch.setattr(
        "plyunit.services.animations.Animations", lambda **kwargs: animations
    )
    app = ConfigOnlyApp()
    config = AppConfig(title="test", window_width=100, window_height=80)

    assert bootstrap.init(app, config) is app
    assert app.window is bindings["Window"].return_value
    assert app.canvas is bindings["Canvas2D"].return_value
    assert app.renderer is renderer
    assert app.assets is bindings["Assets"].return_value
    assert app.animations is animations
    assert app.scene_manager is scene
    bindings["Assets"].assert_called_once_with(asset_base_path=config.assets_path)
    bindings["Camera2D"].assert_called_once_with(size=(100, 80), position=(50.0, 40.0))
    renderer_factory.assert_called_once_with(
        canvas=app.canvas,
        ubr=bindings["UnifiedBufferBatch"].return_value,
        max_sprites=config.max_sprites,
    )
    bindings["Audio"].from_config.assert_not_called()


def test_service_overrides_receive_app_and_none_disables(bindings, monkeypatch) -> None:
    monkeypatch.setattr(
        "plyunit.rendering.renderer.Renderer", lambda **kwargs: object()
    )
    custom_assets = object()
    factory = Mock(return_value=custom_assets)
    app = ConfigOnlyApp()
    bootstrap.init(app, asset=factory, animations=None, scene_manager=None, camera=None)
    factory.assert_called_once_with(app)
    assert app.assets is custom_assets
    assert app.animations is None
    assert app.scene_manager is None
    assert app.camera is None
    bindings["Assets"].assert_not_called()
    bindings["Camera2D"].assert_not_called()


def test_camera_override_keeps_factory_configuration(bindings, monkeypatch) -> None:
    monkeypatch.setattr(
        "plyunit.rendering.renderer.Renderer", lambda **kwargs: object()
    )
    camera = SimpleNamespace(position=(-120.0, 75.0), zoom=2.0)
    factory = Mock(return_value=camera)
    app = ConfigOnlyApp()

    bootstrap.init(app, camera=factory)

    factory.assert_called_once_with(app)
    assert app.camera is camera
    assert camera.position == (-120.0, 75.0)
    assert camera.zoom == 2.0
    bindings["Camera2D"].assert_not_called()


def test_bootstrap_optional_services_use_selected_adapters(bindings, monkeypatch):
    monkeypatch.setattr(
        "plyunit.rendering.renderer.Renderer", lambda **kwargs: object()
    )
    fake_physics = ModuleType("plyunit.backends.physics")
    physics_factory = Mock(return_value=object())
    monkeypatch.setattr(fake_physics, "Physics", physics_factory, raising=False)
    monkeypatch.setitem(sys.modules, fake_physics.__name__, fake_physics)
    fake_imgui = ModuleType("plyunit.backends.imgui")
    imgui_factory = Mock(return_value=object())
    monkeypatch.setattr(fake_imgui, "ImGui", imgui_factory, raising=False)
    monkeypatch.setitem(sys.modules, fake_imgui.__name__, fake_imgui)
    app = ConfigOnlyApp()
    config = AppConfig(
        physics=PhysicsConfig(enabled=True),
        imgui=ImGuiConfig(enabled=True),
        audio=AudioConfig(enabled=True),
    )

    bootstrap.init(app, config, scene_manager=None, animations=None)

    physics_factory.assert_called_once_with(
        gravity=config.physics.gravity,
        spatial_hash_dim=config.physics.spatial_hash_dim,
        spatial_hash_count=config.physics.spatial_hash_count,
        sleep_time_threshold=config.physics.sleep_time_threshold,
        idle_speed_threshold=config.physics.idle_speed_threshold,
        iterations=config.physics.iterations,
        damping=config.physics.damping,
        enable_spatial_hash=config.physics.enable_spatial_hash,
        world_bounds=config.physics.world_bounds,
    )
    imgui_factory.assert_called_once_with(
        dark_style=config.imgui.dark_style, no_ini=config.imgui.no_ini
    )
    bindings["Audio"].from_config.assert_called_once_with(config.audio)


def test_bindings_expose_only_current_backend_factories() -> None:
    from plyunit.backends.integrations import raylib

    actual = bootstrap._load_backend_bindings()
    assert set(actual) == {
        "Window",
        "Canvas2D",
        "UnifiedBufferBatch",
        "Assets",
        "Camera2D",
        "Audio",
    }
    for name, factory in actual.items():
        assert factory is getattr(raylib, name)


def test_optional_gpu_services_attach_after_window_and_batch_init(
    bindings, monkeypatch
) -> None:
    """ImGui attaches immediately, so the graphics context must already exist."""
    events = []
    window = bindings["Window"].return_value
    window.init_window.side_effect = lambda *args: events.append("window")
    bindings["UnifiedBufferBatch"].return_value.init = lambda *args: events.append(
        "batch"
    )
    monkeypatch.setattr(bootstrap, "_imgui", lambda app, config: events.append("imgui"))
    app = App()
    bootstrap.init(
        app,
        AppConfig(imgui=ImGuiConfig(enabled=True)),
        asset=None,
        scene_manager=None,
        animations=None,
        camera=None,
    )
    assert events == ["window", "batch", "imgui"]
    app.shutdown()


def test_default_resolution_and_factory_are_distinct() -> None:
    app = ConfigOnlyApp()
    default = Mock(return_value="default")
    assert bootstrap._service(app, bootstrap.DEFAULT, default) == "default"
    assert bootstrap._service(app, None, default) is None
    override = Mock(return_value="custom")
    assert bootstrap._service(app, override, default) == "custom"
    override.assert_called_once_with(app)
    default.assert_called_once()
