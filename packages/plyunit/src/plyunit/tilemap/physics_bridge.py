"""TileMapPhysicsBridge — adapter from baked tilemap data to Physics.

Converts :class:`BakedStaticBody` (a baker-produced TypedDict) into
:class:`~plyunit.backends.physics.pymunk.StaticBody` (pymunk-backed) and
registers it with :class:`~plyunit.backends.physics.pymunk.Physics` in
batches per chunk. Also installs the one-way platform handler.

Coordinate conventions:
- ``BakedStaticBody["world_pos"]`` = the body's top-left corner (tile top-left).
- Shape offsets/vertices in baked data are expressed relative to that
  top-left corner. Since ``BoxShape``/``CircleShape`` in the physics
  integration interpret ``offset`` as the shape center relative to the
  body, the bridge shifts box offsets so the center is correct.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plyunit.core.components.physics import (
    BoxShape,
    CircleShape,
    CollisionFilter,
    PhysicsShape,
    PolygonShape,
)

from .map_data import BakedStaticBody, PhysicsShape as BakedShape

if TYPE_CHECKING:
    import pymunk

logger = logging.getLogger(__name__)


def _is_static_body(obj: object) -> bool:
    """Duck-typed detection of ``StaticBody`` without importing the engine integration.

    Relies on ``type(obj).__name__`` so this module stays pure with no
    runtime dependency on :mod:`plyunit.backends.integrations`.

    Args:
        obj: Candidate object to check.

    Returns:
        bool: ``True`` if ``obj`` is a ``StaticBody`` with ``user_data``.
    """
    return type(obj).__name__ == "StaticBody" and hasattr(obj, "user_data")


class TileMapPhysicsBridge:
    """Bridge from baked tilemap data to Physics (backend-agnostic).

    Chunk-oriented lifecycle for compatibility with both eager spawn
    (on_ready) and streaming (ChunkTile load/unload per chunk).

    ``physics`` must expose:
    - ``add_static_batch`` / ``remove_static`` / ``add_pre_solve_handler``
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
        self._physics.add_pre_solve_handler(self._one_way_pre_solve)
        self._one_way_installed = True

    def _one_way_pre_solve(
        self,
        arbiter: pymunk.Arbiter,
        space: pymunk.Space,
        data: Any,
    ) -> None:
        """Filters collisions for one-way platforms at first contact.

        Disables the collision response unless the actor touches the
        platform from above (following the contact normal; the world is
        y-down). An actor can jump through the platform from below and
        only collides when landing from above.

        Args:
            arbiter: The pymunk arbiter currently being pre-solved.
            space: The pymunk space the arbiter belongs to.
            data: Extra handler data (unused).
        """
        shape_a, shape_b = arbiter.shapes
        a_data = getattr(shape_a.body, "data", None)
        b_data = getattr(shape_b.body, "data", None)

        static: Any | None = None
        static_is_a = False
        if _is_static_body(a_data):
            static, static_is_a = a_data, True
        elif _is_static_body(b_data):
            static, static_is_a = b_data, False
        if static is None:
            return

        ud = static.user_data
        if not isinstance(ud, dict) or not ud.get("is_one_way"):
            return

        nx, ny = arbiter.normal
        if not static_is_a:
            nx, ny = -nx, -ny  # point the normal from platform → actor

        # World is y-down: "up" = -y. Only process when the normal clearly
        # points up (actor above the platform). Side/below → ignored.
        if ny > -0.5:
            arbiter.process_collision = False

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
        kind = shape.get("kind", "box")
        if kind == "box":
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
        if kind == "circle":
            ox, oy = shape.get("offset", (0.0, 0.0))
            return CircleShape(
                radius=shape.get("radius", 0.0),
                offset=(ox, oy),
                friction=friction,
                elasticity=elasticity,
            )
        if kind == "polygon":
            verts = shape.get("vertices", [])
            return PolygonShape(
                vertices=[(float(v[0]), float(v[1])) for v in verts],
                friction=friction,
                elasticity=elasticity,
            )
        raise ValueError(f"Unknown baked shape kind: {kind!r}")
