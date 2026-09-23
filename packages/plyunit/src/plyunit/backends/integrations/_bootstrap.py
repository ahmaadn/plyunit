"""Composition root for the active integration backend.

This module wires engine-level services (Renderer, SceneManager,
Assets, Animations) together with the window + canvas + batcher from
the active integration backend. It is the *only* place where
``plyunit.backends.integrations.<name>`` is imported at runtime —
everywhere else users reach these services through lazy facades
(``plyunit.services.input``, ``plyunit.audio``, etc.).

Generic adapter names (``Window``, ``Canvas``) — not ``Raylib*`` —
symmetric with the Assets pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plyunit.backends._selector import integration_module

if TYPE_CHECKING:
    from plyunit.core.app import App, AppConfig


def init[T: App](app: T, config: AppConfig | str | None = None) -> T:
    """Wire ``app`` with the active backend's window + canvas + services.

    Sets ``app.window``, ``app.canvas``, ``app.renderer``,
    ``app.scene_manager``, ``app.assets``, ``app.animations`` directly,
    then calls ``app.init(cfg)``.

    If ``cfg.physics.enabled`` is True, the active physics backend
    service is built via ``build_physics_service`` and held by the
    registry.

    If ``cfg.imgui.enabled`` is True, the imgui service is built and
    held by the registry.

    If ``cfg.audio.enabled`` is True, the audio service is built and
    held by the registry.

    Args:
        app: The ``App`` instance to bootstrap.
        config: ``AppConfig`` or a config file path. ``None`` = default.

    Returns:
        The bootstrapped ``App``.
    """
    from importlib import import_module

    from plyunit.assets.animations import Animations
    from plyunit.core.app import AppConfig
    from plyunit.rendering.renderer import Renderer
    from plyunit.services.scene_manager import SceneManager

    integ = integration_module()  # the selected integration backend module path
    # Static chain so Nuitka traces every branch.
    if integ == "plyunit.backends.integrations.raylib":
        from plyunit.assets.assets import Assets
        from plyunit.backends.integrations.raylib.core import get_window
        from plyunit.backends.integrations.raylib.drawing import (
            get_batching_backend,
            get_canvas,
        )
    else:
        from plyunit.assets.assets import Assets

        bundle = import_module(integ)
        get_batching_backend = bundle.get_batching_backend
        get_window = bundle.get_window
        get_canvas = bundle.get_canvas

    cfg = (
        AppConfig.from_file(config)
        if isinstance(config, str)
        else config or AppConfig()
    )
    cfg.validate()

    ubr = get_batching_backend()

    # Wire platform-specific bits directly onto the app (generic names).
    app.window = get_window()
    app.canvas = get_canvas()
    app.renderer = Renderer(
        canvas=app.canvas,
        ubr=ubr,
    )
    app.scene_manager = SceneManager()
    app.assets = Assets()
    app.animations = Animations()

    app.init(cfg)

    if cfg.physics.enabled:
        from plyunit.backends.physics import build_physics_service

        build_physics_service(cfg.physics)

    if cfg.imgui.enabled:
        from plyunit.backends.imgui import build_imgui_service

        build_imgui_service(cfg.imgui)

    if cfg.audio.enabled:
        from plyunit.audio.service import Audio

        Audio.from_config(cfg.audio)

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
