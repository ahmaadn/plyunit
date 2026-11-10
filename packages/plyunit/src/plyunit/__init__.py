"""plyunit - a Python-based 2D game engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from plyunit._version import __version__ as __version__

if TYPE_CHECKING:
    from plyunit._bootstrap import create_app, init
    from plyunit.backends import ports as ports
    from plyunit.backends.integrations import Canvas2D, UnifiedBufferBatch
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
    from plyunit.core.logging import configure_logging as configure_logging
    from plyunit.core.units import (
        MultipleResultsFound as MultipleResultsFound,
        NodeUnit as NodeUnit,
        NoResultFound as NoResultFound,
        QueryScope as QueryScope,
        SceneUnit as SceneUnit,
        ServiceUnit as ServiceUnit,
        Unit as Unit,
        UnitRegistry as UnitRegistry,
        units as units,
    )
    from plyunit.events.event_bus import EventBus as EventBus
    from plyunit.events.signal import Signal as Signal, on as on
    from plyunit.handler import (
        Font as Font,
        Image as Image,
        RenderTexture as RenderTexture,
        Shader as Shader,
        StreamingTexture as StreamingTexture,
        Texture2D as Texture2D,
    )
    from plyunit.rendering import (
        BlendMode as BlendMode,
        Layer as Layer,
        RenderContext as RenderContext,
        Renderer as Renderer,
        RenderPass as RenderPass,
        RenderState as RenderState,
    )
    from plyunit.service.audio import Audio, VoiceId
    from plyunit.services.animations import (
        AnimationClip as AnimationClip,
        AnimationFrame as AnimationFrame,
        Animations as Animations,
    )
    from plyunit.services.assets import Assets
    from plyunit.services.camera import Camera2D
    from plyunit.services.imgui import ImGui
    from plyunit.services.input import Gamepad, Input, Mouse, Touch
    from plyunit.services.physics import (
        BodyType as BodyType,
        BoxShape as BoxShape,
        CircleShape as CircleShape,
        CollisionFilter as CollisionFilter,
        CollisionInfo as CollisionInfo,
        Physics as Physics,
        PhysicsArea as PhysicsArea,
        PhysicsBody as PhysicsBody,
        PhysicsDebugDraw as PhysicsDebugDraw,
        PhysicsHandle as PhysicsHandle,
        PhysicsShape as PhysicsShape,
        PolygonShape as PolygonShape,
        SegmentShape as SegmentShape,
        StaticBody as StaticBody,
    )
    from plyunit.services.scene_manager import SceneManager as SceneManager
    from plyunit.services.shaders import Shaders
    from plyunit.services.spatial_index import SpatialIndex as SpatialIndex
    from plyunit.services.text import Text
    from plyunit.services.timers import (
        CoroutineHandle as CoroutineHandle,
        Timer as Timer,
        TimerHandle as TimerHandle,
        WaitToken as WaitToken,
    )
    from plyunit.services.tween import Tween as Tween, TweenAnimation as TweenAnimation
    from plyunit.services.window import Window
    from plyunit.tilemap import (
        AutotileProcessor as AutotileProcessor,
        TileMapNode as TileMapNode,
    )


_LAZY_MODULES = {
    # Backend-neutral contracts
    "ports": "plyunit.backends",
    "IAudio": "plyunit.backends.ports.audio",
    "FontHandle": "plyunit.backends.ports.handler",
    "ImageHandle": "plyunit.backends.ports.handler",
    "RenderTextureHandle": "plyunit.backends.ports.handler",
    "StreamingTextureHandle": "plyunit.backends.ports.handler",
    "Texture2DHandle": "plyunit.backends.ports.handler",
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
    "SpatialIndex": "plyunit.services.spatial_index",
    "CoroutineHandle": "plyunit.services.timers",
    "TimerHandle": "plyunit.services.timers",
    "Timer": "plyunit.services.timers",
    "WaitToken": "plyunit.services.timers",
    "Tween": "plyunit.services.tween",
    "TweenAnimation": "plyunit.services.tween",
    "EASINGS": "plyunit.utils.math.easing",
    "get_easing": "plyunit.utils.math.easing",
    # Backend-specific services selected only at the facade boundary
    "Gamepad": "plyunit.backends.integrations",
    "Input": "plyunit.backends.integrations",
    "Mouse": "plyunit.backends.integrations",
    "Touch": "plyunit.backends.integrations",
    "Audio": "plyunit.backends.integrations",
    "VoiceId": "plyunit.services.audio._types",
    "compute_spatial": "plyunit.services.audio.spatial",
    # Assets, text, and shared data
    "Animations": "plyunit.services.animations",
    "Assets": "plyunit.backends.integrations",
    "ImageProcessor": "plyunit.backends.integrations",
    "AnimationClip": "plyunit.services.animations",
    "AnimationFrame": "plyunit.services.animations",
    "TemplateText": "plyunit.backends.ports.text",
    "ShapedText": "plyunit.backends.ports.text",
    "Shaders": "plyunit.backends.integrations",
    "ShaderHandle": "plyunit.backends.ports.handler",
    "ShaderUniform": "plyunit._enums",
    "TextureFilter": "plyunit._enums",
    "TextureWrap": "plyunit._enums",
    "Text": "plyunit.backends.integrations",
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
    # _bootstrap
    "init": "plyunit._bootstrap",
    "create_app": "plyunit._bootstrap",
    # Integration backend
    "Camera2D": "plyunit.backends.integrations",
    "Canvas2D": "plyunit.backends.integrations",
    "UnifiedBufferBatch": "plyunit.backends.integrations",
    "StreamingTexture": "plyunit.backends.integrations",
    # Physics backend
    "AABB": "plyunit.services.physics",
    "DYNAMIC_ACTOR": "plyunit.services.physics",
    "DYNAMIC_SENSOR_TARGET": "plyunit.services.physics",
    "PROJECTILE": "plyunit.services.physics",
    "SENSOR": "plyunit.services.physics",
    "WORLD_STATIC": "plyunit.services.physics",
    "BodyType": "plyunit.services.physics",
    "BoxShape": "plyunit.services.physics",
    "CircleShape": "plyunit.services.physics",
    "CollisionFilter": "plyunit.services.physics",
    "CollisionInfo": "plyunit.services.physics",
    "PhysicsArea": "plyunit.services.physics",
    "PhysicsBody": "plyunit.services.physics",
    "PhysicsDebugDraw": "plyunit.services.physics",
    "PhysicsHandle": "plyunit.services.physics",
    "Physics": "plyunit.services.physics",
    "PhysicsShape": "plyunit.services.physics",
    "PolygonShape": "plyunit.services.physics",
    "SegmentShape": "plyunit.services.physics",
    "StaticBody": "plyunit.services.physics",
    # ImGui backend
    "ImGui": "plyunit.backends.imgui",
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
    "Audio",
    "AudioConfig",
    "AutotileProcessor",
    "BlendMode",
    "BodyType",
    "BoxShape",
    "Camera2D",
    "Canvas2D",
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
    "FontHandle",
    "Gamepad",
    "IAudio",
    "ImGui",
    "ImGuiConfig",
    "ImageHandle",
    "ImageProcessor",
    "Input",
    "Layer",
    "Mouse",
    "MultipleResultsFound",
    "NoResultFound",
    "NodeUnit",
    "Physics",
    "PhysicsArea",
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
    "RenderTextureHandle",
    "Renderer",
    "SceneManager",
    "SceneUnit",
    "SegmentShape",
    "ServiceUnit",
    "ShaderHandle",
    "ShaderUniform",
    "Shaders",
    "ShapedText",
    "Signal",
    "SpatialIndex",
    "StaticBody",
    "StreamingTexture",
    "StreamingTextureHandle",
    "TemplateText",
    "Text",
    "Texture2DHandle",
    "TextureFilter",
    "TextureWrap",
    "TileMapNode",
    "Timer",
    "TimerHandle",
    "Touch",
    "Transform2D",
    "TransformState",
    "TransformStore",
    "Tween",
    "TweenAnimation",
    "UnifiedBufferBatch",
    "Unit",
    "UnitNotSetError",
    "UnitRegistry",
    "VoiceId",
    "WaitToken",
    "Window",
    "builtin",
    "components",
    "compute_spatial",
    "configure_logging",
    "create_app",
    "get_easing",
    "init",
    "math",
    "on",
    "ports",
    "units",
)
