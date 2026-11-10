"""Compose backend adapters and backend-neutral application services."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, cast

from typing_extensions import Sentinel

if TYPE_CHECKING:
    from plyunit.backends.imgui import ImGui
    from plyunit.backends.physics import Physics
    from plyunit.backends.ports.assets import IAssets
    from plyunit.backends.ports.audio import IAudio
    from plyunit.backends.ports.camera2d import ICamera2D
    from plyunit.core.app import App, AppConfig, PhysicsConfig
    from plyunit.core.schema_config import AudioConfig, ImGuiConfig
    from plyunit.services.animations import Animations
    from plyunit.services.scene_manager import SceneManager


type Service[T: App, S] = Callable[[T], S]

DEFAULT = Sentinel("DEFAULT")


def _load_backend_bindings():
    """Collect factories at the composition root, never inside domain services."""
    from plyunit.backends._selector import integration_module

    module_name = integration_module()
    # A static import lets Nuitka discover the stock backend's dependencies.
    if module_name == "plyunit.backends.integrations.raylib":
        from plyunit.backends.integrations import raylib as bundle
    else:
        bundle = import_module(module_name)
    return {
        "Window": bundle.Window,
        "Canvas2D": bundle.Canvas2D,
        "UnifiedBufferBatch": bundle.UnifiedBufferBatch,
        "Assets": bundle.Assets,
        "Camera2D": bundle.Camera2D,
        "Audio": bundle.Audio,
    }


def _physics[T: App](app: T, cfg: PhysicsConfig) -> Physics:
    """Build and inject the configured physics adapter."""
    from plyunit.backends.physics import Physics

    return Physics(
        gravity=cfg.gravity,
        spatial_hash_dim=cfg.spatial_hash_dim,
        spatial_hash_count=cfg.spatial_hash_count,
        sleep_time_threshold=cfg.sleep_time_threshold,
        idle_speed_threshold=cfg.idle_speed_threshold,
        iterations=cfg.iterations,
        damping=cfg.damping,
        enable_spatial_hash=cfg.enable_spatial_hash,
        world_bounds=cfg.world_bounds,
    )


def _imgui[T: App](app: T, cfg: ImGuiConfig) -> ImGui:
    """Build the selected ImGui adapter from application configuration."""
    from plyunit.backends.imgui import ImGui

    return ImGui(dark_style=cfg.dark_style, no_ini=cfg.no_ini)


def _audio(app: App, cfg: AudioConfig) -> IAudio:
    """Build the selected audio adapter from application configuration."""
    return _load_backend_bindings()["Audio"].from_config(cfg)


def _service[T: App, S](
    app: T,
    spec: Service[T, S] | DEFAULT | None,
    default_factory: Callable[[], S],
) -> S:
    """Resolve a factory for ready service fields, with None as a disabled sentinel."""
    if spec is DEFAULT:
        return default_factory()
    if spec is None:
        return cast(S, None)
    return spec(app)


def init[T: App](
    app: T,
    config: AppConfig | str | None = None,
    *,
    asset: Service[T, IAssets] | DEFAULT | None = DEFAULT,
    animations: Service[T, Animations] | DEFAULT | None = DEFAULT,
    scene_manager: Service[T, SceneManager] | DEFAULT | None = DEFAULT,
    camera: Service[T, ICamera2D] | DEFAULT | None = DEFAULT,
) -> T:
    """Wire an application to the selected backend and initialize its window.

    Backend-specific implementations are chosen here. Core code receives
    services through ports and keeps resource handles opaque. Optional physics,
    audio, and ImGui services are retained by the application service registry.

    Args:
        app: Application to initialize.
        config: Application configuration, a JSON config path, or ``None`` for
            defaults.
        asset: ``DEFAULT`` for the selected assets adapter, ``None`` to disable,
            or a factory receiving the application.
        animations: Service override with the same semantics as ``asset``.
        scene_manager: Service override with the same semantics as ``asset``.
        camera: Service override with the same semantics as ``asset``.

    Returns:
        The initialized application.
    """
    from plyunit.core.app import AppConfig
    from plyunit.rendering.renderer import Renderer
    from plyunit.services.animations import Animations
    from plyunit.services.scene_manager import SceneManager

    cfg = (
        AppConfig.from_file(config)
        if isinstance(config, str)
        else config or AppConfig()
    )
    cfg.validate()
    bindings = _load_backend_bindings()
    app.window = bindings["Window"]()
    app.canvas = bindings["Canvas2D"]()
    app.renderer = Renderer(
        canvas=app.canvas,
        ubr=bindings["UnifiedBufferBatch"](),
        max_sprites=cfg.max_sprites,
    )
    app.scene_manager = _service(app, scene_manager, SceneManager)
    app.assets = _service(
        app, asset, lambda: bindings["Assets"](asset_base_path=cfg.assets_path)
    )
    animation_path = cfg.animation_path or cfg.assets_path
    app.animations = _service(
        app, animations, lambda: Animations(asset_base_path=animation_path)
    )
    app.camera = _service(
        app,
        camera,
        lambda: bindings["Camera2D"](
            size=(cfg.window_width, cfg.window_height),
            position=(cfg.window_width / 2.0, cfg.window_height / 2.0),
        ),
    )
    app.init(cfg)
    if cfg.physics.enabled:
        _physics(app, cfg.physics)
    if cfg.imgui.enabled:
        _imgui(app, cfg.imgui)
    if cfg.audio.enabled:
        _audio(app, cfg.audio)
    if cfg.log_file_path is not None:
        app.setup_logging(cfg.log_level, str(cfg.log_file_path))
    return app


def create_app(config: AppConfig | str | None = None) -> App:
    """Create and initialize a default application.

    Args:
        config: Application configuration, a config path, or ``None`` for defaults.

    Returns:
        The initialized application.
    """
    from plyunit.core.app import App

    return init(App(), config)


__all__ = ["DEFAULT", "Service", "create_app", "init"]
