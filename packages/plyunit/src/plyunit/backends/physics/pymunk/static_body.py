"""StaticBody — static body representation for world geometry.

NOT a ``NodeUnit`` subclass. It is managed directly by the QuadTree and
``Physics`` to avoid thousands of nodes in the scene tree.

Usage example::

    static = StaticBody(
        position=(100, 200),
        shapes=[BoxShape(width=32, height=32)],
    )
    physics_service.add_static(static)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import pymunk

from plyunit.core.components.physics import CollisionFilter, PhysicsShape

_static_id_counter = itertools.count(1)


@dataclass
class StaticBody:
    """Static body representation (tile, wall, tree) — NOT a NodeUnit.

    Managed by the QuadTree for spatial queries and synced into the pymunk
    Space as pymunk static bodies.

    Attributes:
        position: World position (x, y).
        shapes: The list of collision shapes that make up this body.
        filter: The default collision filter for all shapes.
        user_data: Custom data that can be attached by the user.
        id: Unique auto-generated ID.
    """

    position: tuple[float, float] = (0.0, 0.0)
    shapes: list[PhysicsShape] = field(default_factory=list)
    filter: CollisionFilter = field(default_factory=CollisionFilter)
    user_data: Any = None
    id: int = field(default_factory=lambda: next(_static_id_counter))

    # Internal pymunk references — managed by PhysicsBackend
    _pm_body: pymunk.Body | None = field(default=None, repr=False, compare=False)
    _pm_shapes: list[pymunk.Shape] = field(
        default_factory=list, repr=False, compare=False
    )
