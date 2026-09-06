"""plyunit — lightweight units for a Python-based 2D game engine.

This module is a package-level *facade* that exposes all public names via
lazy resolution. It uses ``__getattr__`` so that only the sub-packages that
are actually accessed get imported, reducing startup time and the cost of
optional dependencies (raylib, pymunk, and imgui are not loaded by a plain
``import plyunit``).

Usage example:
    >>> import plyunit
    >>> plyunit.__version__
    '0.1.0'
    >>> from plyunit import Audio  # lazy
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plyunit._version import __version__ as __version__

if TYPE_CHECKING:
    from plyunit.assets import (
        AnimationClip as AnimationClip,
        AnimationFrame as AnimationFrame,
        Animations as Animations,
        Assets as Assets,
        ShaderHandle as ShaderHandle,
        Shaders as Shaders,
        ShaderUniform as ShaderUniform,
        TemplateText as TemplateText,
        Text as Text,
    )
    from plyunit.audio import (
        Audio as Audio,
        AudioBackend as AudioBackend,
        IAudioBackend as IAudioBackend,
        VoiceId as VoiceId,
        compute_spatial as compute_spatial,
    )
    from plyunit.backends import interfaces as interfaces
    from plyunit.backends.imgui import (
        ImGui as ImGui,
        ImGuiBackend as ImGuiBackend,
        build_imgui_service as build_imgui_service,
    )
    from plyunit.backends.integrations import (
        AssetsLoader as AssetsLoader,
        BatchingBackend as BatchingBackend,
        Camera2D as Camera2D,
        Canvas as Canvas,
        Font as Font,
        ShaderLoader as ShaderLoader,
        StreamingTexture as StreamingTexture,
        Window as Window,
        create_app as create_app,
        get_assets_loader as get_assets_loader,
        get_shader_loader as get_shader_loader,
        init as init,
    )
    from plyunit.backends.physics import (
        AABB as AABB,
        DYNAMIC_ACTOR as DYNAMIC_ACTOR,
        DYNAMIC_SENSOR_TARGET as DYNAMIC_SENSOR_TARGET,
        PROJECTILE as PROJECTILE,
        SENSOR as SENSOR,
        WORLD_STATIC as WORLD_STATIC,
        BodyType as BodyType,
        BoxShape as BoxShape,
        CircleShape as CircleShape,
        CollisionFilter as CollisionFilter,
        CollisionInfo as CollisionInfo,
        Physics as Physics,
        PhysicsArea as PhysicsArea,
        PhysicsBackend as PhysicsBackend,
        PhysicsBody as PhysicsBody,
        PhysicsDebugDraw as PhysicsDebugDraw,
        PhysicsHandle as PhysicsHandle,
        PhysicsShape as PhysicsShape,
        PolygonShape as PolygonShape,
        SegmentShape as SegmentShape,
        StaticBody as StaticBody,
        build_physics_service as build_physics_service,
    )
    from plyunit.core.app import (
        App as App,
        AppConfig as AppConfig,
        AudioConfig as AudioConfig,
        ImGuiConfig as ImGuiConfig,
        PhysicsConfig as PhysicsConfig,
    )
    from plyunit.core.components import (
        Component as Component,
        ComponentNotFoundError as ComponentNotFoundError,
        ComponentRegistry as ComponentRegistry,
        UnitNotSetError as UnitNotSetError,
        builtin as builtin,
        components as components,
    )
    from plyunit.core.components.transform import (
        Transform2D as Transform2D,
        TransformState as TransformState,
    )
    from plyunit.core.logging import configure_logging as configure_logging
    from plyunit.core.units import (
        MultipleResultsFound as MultipleResultsFound,
        NodeUnit as NodeUnit,
        NoResultFound as NoResultFound,
        QueryScope as QueryScope,
        SceneUnit as SceneUnit,
        ServiceUnit as ServiceUnit,
        TransformStore as TransformStore,
        Unit as Unit,
        UnitRegistry as UnitRegistry,
        units as units,
    )
    from plyunit.events.event_bus import EventBus as EventBus
    from plyunit.events.signal import Signal as Signal, on as on
    from plyunit.rendering import (
        BlendMode as BlendMode,
        DrawScope as DrawScope,
        Layer as Layer,
        RenderContext as RenderContext,
        Renderer as Renderer,
        RenderPass as RenderPass,
        RenderState as RenderState,
    )
    from plyunit.services.input import (
        Gamepad as Gamepad,
        Input as Input,
        Mouse as Mouse,
        Touch as Touch,
    )
    from plyunit.services.scene_manager import SceneManager as SceneManager
    from plyunit.services.spatial import SpatialIndex as SpatialIndex
    from plyunit.services.timers import (
        CoroutineHandle as CoroutineHandle,
        Timer as Timer,
        TimerHandle as TimerHandle,
        WaitToken as WaitToken,
    )
    from plyunit.services.tween import Tween as Tween, TweenAnimation as TweenAnimation
    from plyunit.tilemap import (
        AutotileProcessor as AutotileProcessor,
        TileMapNode as TileMapNode,
    )
    from plyunit.utils import math as math
    from plyunit.utils.math.easing import EASINGS as EASINGS, get_easing as get_easing
    from plyunit.utils.pool import (
        EntityHandle as EntityHandle,
        EntityPool as EntityPool,
    )


_LAZY_MODULES = {
    # Interface
    "interfaces": "plyunit.backends",
    # Core components
    "Component": "plyunit.core.components",
    "ComponentNotFoundError": "plyunit.core.components",
    "ComponentRegistry": "plyunit.core.components",
    "UnitNotSetError": "plyunit.core.components",
    "builtin": "plyunit.core.components",
    "components": "plyunit.core.components",
    "Transform2D": "plyunit.core.components.transform",
    "TransformState": "plyunit.core.components.transform",
    # Units and pools
    "MultipleResultsFound": "plyunit.core.units",
    "NodeUnit": "plyunit.core.units",
    "NoResultFound": "plyunit.core.units",
    "QueryScope": "plyunit.core.units",
    "SceneUnit": "plyunit.core.units",
    "ServiceUnit": "plyunit.core.units",
    "TransformStore": "plyunit.core.units",
    "Unit": "plyunit.core.units",
    "UnitRegistry": "plyunit.core.units",
    "units": "plyunit.core.units",
    "EntityHandle": "plyunit.utils.pool",
    "EntityPool": "plyunit.utils.pool",
    "math": "plyunit.utils",
    # App and engine services
    "App": "plyunit.core.app",
    "AppConfig": "plyunit.core.app",
    "AudioConfig": "plyunit.core.app",
    "ImGuiConfig": "plyunit.core.app",
    "PhysicsConfig": "plyunit.core.app",
    "Window": "plyunit.backends.integrations",
    "configure_logging": "plyunit.core.logging",
    "EventBus": "plyunit.events.event_bus",
    "Signal": "plyunit.events.signal",
    "on": "plyunit.events.signal",
    "SceneManager": "plyunit.services.scene_manager",
    "SpatialIndex": "plyunit.services.spatial",
    "CoroutineHandle": "plyunit.services.timers",
    "TimerHandle": "plyunit.services.timers",
    "Timer": "plyunit.services.timers",
    "WaitToken": "plyunit.services.timers",
    "Tween": "plyunit.services.tween",
    "TweenAnimation": "plyunit.services.tween",
    "EASINGS": "plyunit.utils.math.easing",
    "get_easing": "plyunit.utils.math.easing",
    # Input service
    "Gamepad": "plyunit.services.input",
    "Input": "plyunit.services.input",
    "Mouse": "plyunit.services.input",
    "Touch": "plyunit.services.input",
    # Audio service
    "AudioBackend": "plyunit.audio",
    "Audio": "plyunit.audio",
    "IAudioBackend": "plyunit.audio",
    "VoiceId": "plyunit.audio",
    "compute_spatial": "plyunit.audio",
    # Assets and text
    "Animations": "plyunit.assets",
    "Assets": "plyunit.assets",
    "AssetsLoader": "plyunit.backends.integrations",
    "AnimationClip": "plyunit.assets",
    "AnimationFrame": "plyunit.assets",
    "TemplateText": "plyunit.assets",
    "get_assets_loader": "plyunit.backends.integrations",
    "Shaders": "plyunit.assets",
    "ShaderHandle": "plyunit.assets",
    "ShaderLoader": "plyunit.backends.integrations",
    "ShaderUniform": "plyunit.assets",
    "get_shader_loader": "plyunit.backends.integrations",
    "Text": "plyunit.assets",
    "Font": "plyunit.backends.integrations",
    # Rendering
    "BlendMode": "plyunit.rendering",
    "DrawScope": "plyunit.rendering",
    "Layer": "plyunit.rendering",
    "RenderContext": "plyunit.rendering",
    "Renderer": "plyunit.rendering",
    "RenderPass": "plyunit.rendering",
    "RenderState": "plyunit.rendering",
    # Tilemap
    "TileMapNode": "plyunit.tilemap",
    "AutotileProcessor": "plyunit.tilemap",
    # Integration backend
    "init": "plyunit.backends.integrations",
    "create_app": "plyunit.backends.integrations",
    "Camera2D": "plyunit.backends.integrations",
    "Canvas": "plyunit.backends.integrations",
    "BatchingBackend": "plyunit.backends.integrations",
    "StreamingTexture": "plyunit.backends.integrations",
    # Physics backend
    "AABB": "plyunit.backends.physics",
    "DYNAMIC_ACTOR": "plyunit.backends.physics",
    "DYNAMIC_SENSOR_TARGET": "plyunit.backends.physics",
    "PROJECTILE": "plyunit.backends.physics",
    "SENSOR": "plyunit.backends.physics",
    "WORLD_STATIC": "plyunit.backends.physics",
    "BodyType": "plyunit.backends.physics",
    "BoxShape": "plyunit.backends.physics",
    "CircleShape": "plyunit.backends.physics",
    "CollisionFilter": "plyunit.backends.physics",
    "CollisionInfo": "plyunit.backends.physics",
    "PhysicsArea": "plyunit.backends.physics",
    "PhysicsBackend": "plyunit.backends.physics",
    "PhysicsBody": "plyunit.backends.physics",
    "PhysicsDebugDraw": "plyunit.backends.physics",
    "PhysicsHandle": "plyunit.backends.physics",
    "Physics": "plyunit.backends.physics",
    "PhysicsShape": "plyunit.backends.physics",
    "PolygonShape": "plyunit.backends.physics",
    "SegmentShape": "plyunit.backends.physics",
    "StaticBody": "plyunit.backends.physics",
    "build_physics_service": "plyunit.backends.physics",
    # ImGui backend
    "ImGui": "plyunit.backends.imgui",
    "ImGuiBackend": "plyunit.backends.imgui",
    "build_imgui_service": "plyunit.backends.imgui",
}


def __getattr__(name: str):
    """Lazy attribute resolver for submodules / sub-facades.

    Looks up ``name`` in ``_LAZY_MODULES``; if found, imports the target
    module, fetches the attribute, caches it in ``globals()`` so subsequent
    lookups are instant, and returns the attribute value.

    If the name does not exist as an attribute of the target module, the
    resolver tries importing it as a submodule (e.g. ``builtin`` →
    ``…components.builtin``).

    Args:
        name: The requested attribute name (``Audio``, ``Input``, etc.).

    Returns:
        The resolved attribute from the target module.

    Raises:
        AttributeError: If ``name`` is not in ``_LAZY_MODULES``, or the
            target module has neither that attribute nor a matching
            submodule.
    """
    module_name = _LAZY_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'plyunit' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    try:
        value = getattr(module, name)
    except AttributeError:
        # The name may be a submodule not yet imported by the parent package.
        try:
            value = importlib.import_module(f"{module_name}.{name}")
        except ImportError:
            raise AttributeError(
                f"module {module_name!r} has no attribute {name!r}"
            ) from None
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Full list of attributes available to ``dir(plyunit)``.

    Combines the names already cached in ``globals()`` with all
    ``_LAZY_MODULES`` entries (the lazy resolver). Useful for IDE
    autocomplete and ``help()``.

    Returns:
        A sorted list of attribute names.
    """
    return sorted(set(globals()) | set(_LAZY_MODULES))


__all__ = (
    "AABB",
    "DYNAMIC_ACTOR",
    "DYNAMIC_SENSOR_TARGET",
    "EASINGS",
    "PROJECTILE",
    "SENSOR",
    "WORLD_STATIC",
    "AnimationClip",
    "AnimationFrame",
    "Animations",
    "App",
    "AppConfig",
    "Assets",
    "AssetsLoader",
    "Audio",
    "AudioBackend",
    "AudioConfig",
    "AutotileProcessor",
    "BatchingBackend",
    "BlendMode",
    "BodyType",
    "BoxShape",
    "Camera2D",
    "Canvas",
    "CircleShape",
    "CollisionFilter",
    "CollisionInfo",
    "Component",
    "ComponentNotFoundError",
    "ComponentRegistry",
    "CoroutineHandle",
    "DrawScope",
    "EntityHandle",
    "EntityPool",
    "EventBus",
    "Font",
    "Gamepad",
    "IAudioBackend",
    "ImGui",
    "ImGuiBackend",
    "ImGuiConfig",
    "Input",
    "Layer",
    "Mouse",
    "MultipleResultsFound",
    "NoResultFound",
    "NodeUnit",
    "Physics",
    "PhysicsArea",
    "PhysicsBackend",
    "PhysicsBody",
    "PhysicsConfig",
    "PhysicsDebugDraw",
    "PhysicsHandle",
    "PhysicsShape",
    "PolygonShape",
    "QueryScope",
    "RenderContext",
    "RenderPass",
    "RenderState",
    "Renderer",
    "SceneManager",
    "SceneUnit",
    "SegmentShape",
    "ServiceUnit",
    "ShaderHandle",
    "ShaderLoader",
    "ShaderUniform",
    "Shaders",
    "Signal",
    "SpatialIndex",
    "StaticBody",
    "StreamingTexture",
    "TemplateText",
    "Text",
    "TileMapNode",
    "Timer",
    "TimerHandle",
    "Touch",
    "Transform2D",
    "TransformState",
    "TransformStore",
    "Tween",
    "TweenAnimation",
    "Unit",
    "UnitNotSetError",
    "UnitRegistry",
    "VoiceId",
    "WaitToken",
    "Window",
    "build_imgui_service",
    "build_physics_service",
    "builtin",
    "components",
    "compute_spatial",
    "configure_logging",
    "create_app",
    "get_assets_loader",
    "get_easing",
    "get_shader_loader",
    "init",
    "math",
    "on",
    "units",
)
