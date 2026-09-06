"""Lazy facade for the active physics backend.

All public names (``Physics``, ``PhysicsBody``, ...) are forwarded lazily
from the active backend (see ``_selector.physics_module``) through
``__getattr__`` — this package can be imported even when pymunk is not
installed; an error only surfaces when an attribute is first accessed.

For a concrete host path (rare):

    from plyunit.backends.physics.pymunk import Physics
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from plyunit.backends._selector import physics_module

_active_backend = None


def _get_active_backend():
    """Return the active physics backend module, importing it on first use."""
    global _active_backend
    if _active_backend is None:
        _active_backend = import_module(physics_module())
    return _active_backend


# TYPE SAFE
if TYPE_CHECKING:
    from .pymunk import (
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


__all__ = (
    "AABB",
    "DYNAMIC_ACTOR",
    "DYNAMIC_SENSOR_TARGET",
    "PROJECTILE",
    "SENSOR",
    "WORLD_STATIC",
    "BodyType",
    "BoxShape",
    "CircleShape",
    "CollisionFilter",
    "CollisionInfo",
    "Physics",
    "PhysicsArea",
    "PhysicsBackend",
    "PhysicsBody",
    "PhysicsDebugDraw",
    "PhysicsHandle",
    "PhysicsShape",
    "PolygonShape",
    "SegmentShape",
    "StaticBody",
    "build_physics_service",
)

_SUBS = {
    # Debug
    "PhysicsDebugDraw": "debug_draw",
    # Entities (Components)
    "PhysicsArea": "physics_area",
    "PhysicsBody": "physics_body",
    # Static World
    "StaticBody": "static_body",
    # Service & Backend
    "PhysicsBackend": "pymunk_adapter",
    "Physics": "service",
}


def __getattr__(name: str):
    """Lazy dispatcher for attributes of the active physics backend.

    Args:
        name: The requested attribute name.

    Returns:
        The attribute value from the active physics backend.

    Raises:
        AttributeError: If the attribute is not found in the bundle or a submodule.
    """
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)
    # 1. Try the bundle root first.
    try:
        value = getattr(_get_active_backend(), name)
        globals()[name] = value
        return value
    except AttributeError:
        pass

    # 2. Try the explicit submodule (e.g. ``service``).
    sub = _SUBS.get(name)
    if sub is not None:
        try:
            value = getattr(import_module(f"{physics_module()}.{sub}"), name)
            globals()[name] = value
            return value
        except (ImportError, AttributeError) as exc:
            raise AttributeError(
                f"module 'plyunit.backends.physics' has no attribute {name!r} "
                f"(checked {_get_active_backend().__name__} and {sub})"
            ) from exc
    # 3. Final fallback: look for ``name`` as a submodule of the bundle.
    try:
        value = getattr(import_module(f"{physics_module()}.{name}"), name)
        globals()[name] = value
        return value
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            f"module 'plyunit.backends.physics' has no attribute {name!r} "
            f"(checked {_get_active_backend().__name__})"
        ) from exc


def __dir__() -> list[str]:
    """Return the attribute list for :func:`dir`.

    Returns:
        The sorted list of attribute names.
    """
    return sorted(set(globals()) | set(_SUBS))
