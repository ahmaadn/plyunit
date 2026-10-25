from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING

from typing_extensions import Sentinel

if TYPE_CHECKING:
    from plyunit.assets.animations import Animations
    from plyunit.assets.assets import Assets
    from plyunit.audio.service import Audio
    from plyunit.backends.imgui import ImGui
    from plyunit.backends.integrations import Camera2D
    from plyunit.backends.physics import Physics
    from plyunit.core.app import App, AppConfig, PhysicsConfig
    from plyunit.core.schema_config import AudioConfig, ImGuiConfig
    from plyunit.services.scene_manager import SceneManager


type Service[T: App, S] = Callable[[T], S]

DEFAULT = Sentinel("DEFAULT")


def _load_backend_bindings():
    from plyunit.backends._selector import integration_module

    """Import the selected integration backend and collect its factories."""
    integ = integration_module()
    # Static branch so Nuitka traces the raylib imports.
    if integ == "plyunit.backends.integrations.raylib":
        from plyunit.backends.integrations.raylib.core import get_window
        from plyunit.backends.integrations.raylib.drawing import (
            get_batching_backend,
            get_canvas,
        )

        return {
            "get_window": get_window,
            "get_canvas": get_canvas,
            "get_batching_backend": get_batching_backend,
        }

    bundle = import_module(integ)
    return {
        "get_window": bundle.get_window,
        "get_canvas": bundle.get_canvas,
        "get_batching_backend": bundle.get_batching_backend,
    }


def _physics[T: App](app: T, cfg: PhysicsConfig) -> Physics:
    """Build a ``Physics`` service from a ``PhysicsConfig`` (factory composition root).

    Separates backend parameterization from ``Physics``: the pymunk backend
    is built here and then injected into ``Physics`` via DI.
    """
    from plyunit.backends.physics import Physics, PhysicsBackend

    return Physics(
        PhysicsBackend(
            gravity=cfg.gravity,
            spatial_hash_dim=cfg.spatial_hash_dim,
            spatial_hash_count=cfg.spatial_hash_count,
            sleep_time_threshold=cfg.sleep_time_threshold,
            idle_speed_threshold=cfg.idle_speed_threshold,
            iterations=cfg.iterations,
            damping=cfg.damping,
            enable_spatial_hash=cfg.enable_spatial_hash,
        ),
        world_bounds=cfg.world_bounds,
    )


def _imgui[T: App](app: T, cfg: ImGuiConfig) -> ImGui:
    from plyunit.backends.imgui import ImGui

    """Build ``ImGui`` from ``ImGuiConfig`` (composition-root factory)."""
    return ImGui(
        dark_style=cfg.dark_style,
        no_ini=cfg.no_ini,
    )


def _audio(app: App, cfg: AudioConfig) -> Audio:
    """Build ``Audio`` from the app's audio config (composition-root factory)."""
    from plyunit.audio.service import Audio

    return Audio.from_config(cfg)


def _service[T: App, S](
    app: T,
    spec: Service[T, S] | DEFAULT | None,
    default_factory: Callable[[], S],
) -> S | None:
    """Resolve a service override.

    ``DEFAULT`` builds the stock service, ``None`` disables it, and any
    other value is treated as a factory that receives ``app``.
    """
    if spec is DEFAULT:
        return default_factory()
    if spec is None:
        return None
    return spec(app)


def init[T: App](
    app: T,
    config: AppConfig | str | None = None,
    *,
    asset: Service[T, Assets] | DEFAULT | None = DEFAULT,
    animations: Service[T, Animations] | DEFAULT | None = DEFAULT,
    scene_manager: Service[T, SceneManager] | DEFAULT | None = DEFAULT,
    camera: Service[T, Camera2D] | DEFAULT | None = DEFAULT,
) -> T:
    """Wire ``app`` with the active backend's window + canvas + services.

    Sets ``app.window``, ``app.canvas``, ``app.renderer``,
    ``app.scene_manager``, ``app.assets``, ``app.animations`` directly,
    then calls ``app.init(cfg)``.

    If ``cfg.physics.enabled`` is True, the active physics backend
    service is built and held by the registry.

    If ``cfg.imgui.enabled`` is True, the imgui service is built and
    held by the registry.

    If ``cfg.audio.enabled`` is True, the audio service is built and
    held by the registry.

    Args:
        app: The ``App`` instance to bootstrap.
        config: ``AppConfig`` or a config file path. ``None`` = default.
        asset: ``DEFAULT`` for the stock ``Assets``, ``None`` to disable,
            or a factory receiving ``app``.
        animations: Same semantics as ``asset``, for ``Animations``.
        scene_manager: Same semantics as ``asset``, for ``SceneManager``.

    Returns:
        The bootstrapped ``App``.
    """

    from plyunit.assets.animations import Animations
    from plyunit.assets.assets import Assets
    from plyunit.backends.integrations import Camera2D
    from plyunit.core.app import AppConfig
    from plyunit.rendering.renderer import Renderer
    from plyunit.services.scene_manager import SceneManager

    bindings = _load_backend_bindings()
    cfg = (
        AppConfig.from_file(config)
        if isinstance(config, str)
        else config or AppConfig()
    )
    cfg.validate()

    # Wire platform-specific bits directly onto the app (generic names).
    app.window = bindings["get_window"]()
    app.canvas = bindings["get_canvas"]()

    ubr = bindings["get_batching_backend"]()
    app.renderer = Renderer(canvas=app.canvas, ubr=ubr, max_sprites=cfg.max_sprites)
    app.scene_manager = _service(app, scene_manager, SceneManager)
    app.assets = _service(app, asset, lambda: Assets(asset_base_path=cfg.assets_path))
    animation_path = cfg.animation_path or cfg.assets_path
    app.animations = _service(
        app, animations, lambda: Animations(asset_base_path=animation_path)
    )
    app.camera = _service(
        app, camera, lambda: Camera2D(size=(cfg.window_width, cfg.window_height))
    )

    if cfg.physics.enabled:
        _physics(app, cfg.physics)

    if cfg.imgui.enabled:
        _imgui(app, cfg.imgui)

    if cfg.audio.enabled:
        _audio(app, cfg.audio)

    app.init(cfg)
    # Optional logging — only when a file path is given
    if cfg.log_file_path is not None:
        app.setup_logging(app.config.log_level, app.config.log_file_path)
    return app


def create_app(config: AppConfig | str | None = None) -> App:
    """Shortcut: build a default ``App`` then ``init`` it.

    Args:
        config: ``AppConfig`` or a config file path. ``None`` = default.

    Returns:
        The bootstrapped ``App``.
    """
    from plyunit.core.app import App

    return init(App(), config)


__all__ = ["init"]
