"""Lazy facade for the active physics backend."""

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
        Physics,
        PhysicsArea,
        PhysicsBody,
        PhysicsDebugDraw,
    )


__all__ = ("Physics", "PhysicsArea", "PhysicsBody", "PhysicsDebugDraw")

_SUBS = {
    "PhysicsDebugDraw": "debug_draw",
    "PhysicsArea": "physics_area",
    "PhysicsBody": "physics_body",
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
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    try:
        value = getattr(_get_active_backend(), name)
        globals()[name] = value
        return value
    except AttributeError:
        pass

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
