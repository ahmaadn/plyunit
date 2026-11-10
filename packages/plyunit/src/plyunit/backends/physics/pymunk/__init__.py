"""Physics engine for Plyunit.

Uses pymunk (Chipmunk2D) as the backend, with the following features:
- Collision mask & layer system (32-bit bitmask, Godot-style).
- Spatial hash (pymunk built-in) for broad-phase dynamic entities.
- Quad tree (custom) for static world geometry.
- Sleeping (pymunk built-in) for idle bodies.
- Debug draw component (plug & play).
"""

from __future__ import annotations

try:
    __import__("pymunk")
except ImportError as exc:
    raise ImportError(
        "plyunit physics requires pymunk: uv sync --package plyunit --extra physics"
    ) from exc

from .debug_draw import PhysicsDebugDraw
from .physics_area import PhysicsArea
from .physics_body import PhysicsBody
from .service import Physics

__all__ = ("Physics", "PhysicsArea", "PhysicsBody", "PhysicsDebugDraw")
