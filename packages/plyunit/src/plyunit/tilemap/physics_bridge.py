"""Convert baked tilemap collision data through the configured physics service.

Box offsets describe top-left corners in baked data, so conversion shifts them
by half the box size to match the portable engine shape's center convention.
Native collision callbacks belong to the selected physics backend.
"""

from __future__ import annotations

import logging
from typing import Any

from plyunit.core.components.physics import (
    BoxShape,
    CircleShape,
    CollisionFilter,
    PhysicsShape,
    PolygonShape,
)

from .map_data import BakedStaticBody, PhysicsShape as BakedShape

logger = logging.getLogger(__name__)


class TileMapPhysicsBridge:
    """Bridge from baked tilemap data to Physics (backend-agnostic).

    Chunk-oriented lifecycle for compatibility with both eager spawn
    (on_ready) and streaming (ChunkTile load/unload per chunk).

    ``physics`` must expose:
    - ``add_static_batch`` / ``remove_static`` / ``install_one_way_handler``
    - ``create_static_body(...)`` factory (wired by the physics integration)
    """

    def __init__(
        self,
        physics: Any,
        tile_size: int = 16,
        chunk_size: int = 16,
    ) -> None:
        """Initializes the bridge with the Physics instance and tilemap dimensions.

        Args:
            physics: Backend-agnostic Physics used to add/remove static
                bodies and install handlers.
            tile_size: Size of one tile edge in pixels.
            chunk_size: Number of tiles per chunk side (square).
        """
        self._physics = physics
        self._tile_size = tile_size
        self._chunk_size = chunk_size
        self._one_way_installed = False

    # ------------------------------------------------------------------
    # Spawn / despawn
    # ------------------------------------------------------------------

    def spawn_bodies(self, bodies: list[BakedStaticBody]) -> list[int]:
        """Converts and registers a batch of static bodies with Physics.

        Args:
            bodies: Bake results (:class:`BakedStaticBody`) to spawn.

        Returns:
            list[int]: IDs of the created static bodies (empty for empty input).
        """
        if not bodies:
            return []
        statics = [self._to_static(b) for b in bodies]
        self._physics.add_static_batch(statics)
        return [s.id for s in statics]

    def despawn_bodies(self, ids: list[int]) -> None:
        """Removes a batch of static bodies by id.

        Args:
            ids: IDs of the static bodies to remove.
        """
        for sid in ids:
            self._physics.remove_static(sid)

    # ------------------------------------------------------------------
    # One-way platform
    # ------------------------------------------------------------------

    def install_one_way_handler(self) -> None:
        """Installs the pre-solve handler for one-way platforms (idempotent).

        Repeated calls never add the handler more than once.
        """
        if self._one_way_installed:
            return
        self._physics.install_one_way_handler()
        self._one_way_installed = True

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _to_static(self, body: BakedStaticBody) -> Any:
        """Converts one baked body into a static body via the physics factory."""
        wx, wy = body["world_pos"]
        friction = body.get("friction", 0.5)
        restitution = body.get("restitution", 0.0)
        shape = self._to_shape(body["shape"], friction, restitution)
        return self._physics.create_static_body(
            position=(wx, wy),
            shapes=[shape],
            filter=CollisionFilter(
                layer=body.get("physics_layer", 1),
                mask=body.get("physics_mask", 0xFFFFFFFF),
                group=0,
            ),
            user_data={
                "is_one_way": body.get("is_one_way", False),
                "friction": friction,
                "restitution": restitution,
            },
        )

    def _to_shape(
        self,
        shape: BakedShape,
        friction: float,
        elasticity: float,
    ) -> PhysicsShape:
        """Converts one baked shape dict into a :class:`PhysicsShape`."""
        kind = shape["kind"]
        if shape["kind"] == "box":
            ox, oy = shape.get("offset", (0.0, 0.0))
            sw, sh = shape.get("size", (0.0, 0.0))
            # baked offset = box top-left relative to the tile; BoxShape uses
            # the center → shift by half the size.
            return BoxShape(
                width=sw,
                height=sh,
                offset=(ox + sw / 2.0, oy + sh / 2.0),
                friction=friction,
                elasticity=elasticity,
            )
        if shape["kind"] == "circle":
            ox, oy = shape.get("offset", (0.0, 0.0))
            return CircleShape(
                radius=shape.get("radius", 0.0),
                offset=(ox, oy),
                friction=friction,
                elasticity=elasticity,
            )
        if shape["kind"] == "polygon":
            verts = shape.get("vertices", [])
            return PolygonShape(
                vertices=[(float(v[0]), float(v[1])) for v in verts],
                friction=friction,
                elasticity=elasticity,
            )
        raise ValueError(f"Unknown baked shape kind: {kind!r}")
