from __future__ import annotations

import math
from dataclasses import dataclass

from plyunit.utils.math.utils import lerp


@dataclass(slots=True)
class Transform2D:
    """Position, rotation, scale — a simple 2D transform for local/world composition.

    Transform2D is a snapshot of 3 geometric parameters at a single point in time.
    It is NOT state that changes over time — it is immutable data.

    Attributes:
        position (tuple[float, float]): Position in coordinate space (x, y).
            May be local coordinates (relative to the parent) or world coordinates
            (absolute in the game world), depending on the context of use.

        rotation (float): Rotation in degrees (0-360).
            Positive = counter-clockwise. May be local or world depending on context.

        scale (tuple[float, float]): Scale (sx, sy), where (1.0, 1.0) = no scaling.
            Values < 1.0 = shrink, > 1.0 = enlarge.
            May be local or world depending on context.

    Note:
        - Transform2D itself does not know whether it is LOCAL or WORLD — that is
          determined by context (where it is stored or how it is used).
        - The combine() method is the key: it turns a LOCAL transform into a WORLD
          transform by composing it with the parent's world transform.
    """

    position: tuple[float, float] = (0.0, 0.0)
    rotation: float = 0.0  # degrees
    scale: tuple[float, float] = (1.0, 1.0)

    def copy(self) -> Transform2D:
        """Creates a copy of this transform."""
        return Transform2D(
            position=(self.position[0], self.position[1]),
            rotation=self.rotation,
            scale=(self.scale[0], self.scale[1]),
        )

    def set_from(self, other: Transform2D) -> None:
        """Copies the values from another Transform2D object without new memory
        allocation."""
        self.position = other.position
        self.rotation = other.rotation
        self.scale = other.scale

    def combine(
        self, parent_world: Transform2D, out: Transform2D | None = None
    ) -> Transform2D:
        """Combines this local transform with the parent's world transform to get a new
        world transform.
        KEY CONCEPT:
        ============
        LOCAL transform = position/rotation/scale RELATIVE to the parent
        WORLD transform = position/rotation/scale ABSOLUTE in the game world

        Formula:
            world_transform = local_transform COMBINED_WITH parent_world_transform

        Example:
            Parent at (100, 100), rotation 0°, scale (1, 1)
            Child LOCAL position = (10, 0) — meaning "10 pixels to the right of
                the parent"
            Child WORLD position = (100 + 10, 100 + 0) = (110, 100)

            Parent at (100, 100), rotation 90°, scale (1, 1)
            Child LOCAL position = (10, 0) — still "10 local units forward"
            But because the parent is rotated 90°, "forward" now = "up"
            Child WORLD position ≈ (100, 110)

        Args:
            parent_world: The parent node's world transform.
                         This MUST already be in world space (absolute).
            out: Optional target Transform2D object for in-place assignment.

        Returns:
            A new Transform2D (or a reference to ``out``) that represents this
            node's absolute position/rotation/scale in the game world.
        """

        scaled_x = self.position[0] * parent_world.scale[0]
        scaled_y = self.position[1] * parent_world.scale[1]

        parent_rad = math.radians(parent_world.rotation)
        cos_r = math.cos(parent_rad)
        sin_r = math.sin(parent_rad)

        rotated_x = (scaled_x * cos_r) - (scaled_y * sin_r)
        rotated_y = (scaled_x * sin_r) + (scaled_y * cos_r)

        new_pos = (
            parent_world.position[0] + rotated_x,
            parent_world.position[1] + rotated_y,
        )
        new_rot = parent_world.rotation + self.rotation
        new_scale = (
            parent_world.scale[0] * self.scale[0],
            parent_world.scale[1] * self.scale[1],
        )

        if out is not None:
            out.position = new_pos
            out.rotation = new_rot
            out.scale = new_scale
            return out

        return Transform2D(
            position=new_pos,
            rotation=new_rot,
            scale=new_scale,
        )


class TransformState:
    """Local/world transform state plus a cache for cross-frame interpolation.

    KEY DIFFERENCE:
    ===============
    Transform2D = Snapshot of geometry data at one point in time (immutable)
    TransformState = Mutable state that changes over time + caching for rendering

    LIFECYCLE:
    ==========
    1. User changes the LOCAL position via set_position() → dirty = True
    2. System computes the WORLD position via recalc_world() → dirty = False
    3. System renders: interpolates between previous_world and world using alpha

    Attributes:
        local (Transform2D): The transform in LOCAL coordinates (relative to the
            parent). This is the "input" — the user mutates this one via
            set_position(), etc.

        world (Transform2D): The transform in WORLD coordinates (absolute).
            Computed from local + the parent's world transform.
            This is the "output" used for physics/rendering.

        previous_world (Transform2D): Snapshot of the world transform from the
            PREVIOUS frame. KEY for interpolation! Stored when recalc_world()
            is called.

            Example timeline:
                Frame 60Hz: [Physics Update] recalc_world() → previous_world = (0,0),
                    world = (10,10)
                Frame 120Hz render A: a=0.5 → interpolate between previous(0,0)
                    and current(10,10) = render at (5,5)
                Frame 120Hz render B: a=1.0 → interpolate between previous(0,0)
                    and current(10,10) = render at (10,10)
                Frame 120Hz render C: a=0.5 → interpolate between previous(0,0)
                    and current(10,10) = render at (5,5)
                [Physics Update] recalc_world() → previous_world = (10,10),
                    world = (20,20)
                Frame 120Hz render D: a=0.5 → interpolate between previous(10,10)
                    and current(20,20) = render at (15,15)

        dirty (bool): Flag for whether the world transform is stale and needs to
            be recomputed.
            True = there is a local change, world has not been updated yet
            False = world is up-to-date with local

    ALPHA CONCEPT:
    ==============
    Alpha is the interpolation parameter in the range [0.0, 1.0] that represents:
        "How far along are we between the last physics frame and the next one?"

    - a = 0.0: Physics just updated → use previous_world (stale data)
    - a = 0.5: Halfway → interpolate to the midpoint
    - a = 1.0: Nearly at the next physics update → use world (latest)

    Linear interpolation formula:
        result = previous_world + (world - previous_world) * alpha
               = previous_world * (1 - alpha) + world * alpha

    VISUALIZATION:
    ==============
    Physics Rate = 60 Hz (update every 16.67ms)
    Render Rate = 120 Hz (render every 8.33ms)

    ms  0.0    8.3   16.7   25.0   33.3   41.7   50.0
        |------|------|------|------|------|------|
    PHY [U]                  [U]                  [U]
    REN [a=0.0] [a=0.5] [a=1.0] [a=0.5] [a=0.0]

    At the render where a=0.5 (midway between updates):
        interpolated = lerp(prev_pos, curr_pos, 0.5) = (prev + curr) / 2

    Result: motion looks smooth, not choppy!
    """

    __slots__ = (
        "_store",
        "_store_index",
        "dirty",
        "local",
        "previous_world",
        "world",
    )

    def __init__(self) -> None:
        """
        Initializes the local transform, current world, previous world, and dirty flag.
        """
        self.local = Transform2D()
        self.world = self.local.copy()
        self.previous_world = self.local.copy()
        self.dirty = True
        self._store = None
        self._store_index = -1

    def bind_store(self, store, index: int) -> None:
        """
        Internal hook: links this state to a ``TransformStore`` at slot ``index``.
        """
        self._store = store
        self._store_index = index

    def unbind_store(self) -> None:
        """Internal hook: unlinks this state from its ``TransformStore``."""
        self._store = None
        self._store_index = -1

    def set_position(self, x: float, y: float) -> None:
        """Sets the local position, then marks the state dirty so world is recomputed.

        LOCAL = relative to the parent node.
        This change does NOT automatically update the world transform.

        Workflow:
            1. User: sprite.transform.set_position(10, 20)
            2. Local updated: local.position = (10.0, 20.0)
            3. Flag: dirty = True (world is now stale)
            4. Later, system: sprite.transform.recalc_world(parent_world)
            5. World updated: world = local.combine(parent_world)
            6. Flag: dirty = False

        Args:
            x, y: Local coordinates as floats.
        """
        fx, fy = float(x), float(y)
        self.local.position = (fx, fy)
        if self._store is not None and self._store_index >= 0:
            self._store.write_local(self._store_index, x=fx, y=fy)
        else:
            self.mark_dirty()

    def set_rotation(self, deg: float) -> None:
        """Sets the local rotation (degrees), then marks the state dirty.

        Rotation is in degrees (0-360), positive = counter-clockwise.
        This is the LOCAL rotation relative to the parent.

        Args:
            deg: Rotation in degrees.
        """
        fr = float(deg)
        self.local.rotation = fr
        if self._store is not None and self._store_index >= 0:
            self._store.write_local(self._store_index, rot=fr)
        else:
            self.mark_dirty()

    def set_scale(self, x: float, y: float) -> None:
        """Sets the local scale, then marks the state dirty.

        LOCAL scale (not world).
        (1.0, 1.0) = no scaling, (2.0, 2.0) = 2x larger.

        Args:
            x, y: Local scale for the X and Y axes.
        """
        fx, fy = float(x), float(y)
        self.local.scale = (fx, fy)
        if self._store is not None and self._store_index >= 0:
            self._store.write_local(self._store_index, sx=fx, sy=fy)
        else:
            self.mark_dirty()

    def mark_dirty(self) -> None:
        """Marks that the world transform needs to be recomputed.

        Called every time the local transform changes.
        Signals to the system that compute() or recalc_world() must be called
        before the world transform can be used.

        Optimization: the system does not need to recompute world if nothing
        changed.
        """
        self.dirty = True
        if self._store is not None and self._store_index >= 0:
            self._store.mark_dirty_subtree(self._store_index)

    def apply_physics_state(
        self,
        local_pos: tuple[float, float],
        local_rot: float,
        world_pos: tuple[float, float],
        world_rot: float,
        previous_world_pos: tuple[float, float],
        previous_world_rot: float,
        *,
        previous_world_scale: tuple[float, float] | None = None,
        world_scale: tuple[float, float] | None = None,
    ) -> None:
        """Write local+world without full dirty cascade (physics post-step)."""
        if self._store is not None and self._store_index >= 0:
            self._store.apply_physics_state(
                self._store_index,
                local_pos,
                local_rot,
                world_pos,
                world_rot,
                previous_world_pos,
                previous_world_rot,
                previous_world_scale=previous_world_scale,
                world_scale=world_scale,
            )
            return
        self.local.position = (float(local_pos[0]), float(local_pos[1]))
        self.local.rotation = float(local_rot)
        self.world.position = (float(world_pos[0]), float(world_pos[1]))
        self.world.rotation = float(world_rot)
        if world_scale is not None:
            self.world.scale = (float(world_scale[0]), float(world_scale[1]))
        self.previous_world.position = (
            float(previous_world_pos[0]),
            float(previous_world_pos[1]),
        )
        self.previous_world.rotation = float(previous_world_rot)
        if previous_world_scale is not None:
            self.previous_world.scale = (
                float(previous_world_scale[0]),
                float(previous_world_scale[1]),
            )
        else:
            self.previous_world.scale = self.world.scale
        self.dirty = False

    def recalc_world(self, parent_world: Transform2D | None) -> None:
        """Computes the new world transform and stores the previous world snapshot
        for interpolation.

        IMPORTANT: This is the function that MOVES the state forward in time.

        Workflow:
            1. Save the PREVIOUS world (for interpolation):
                previous_world = world (copy)
            2. Compute the CURRENT world: world = local.combine(parent_world)
            3. Clear the dirty flag: dirty = False

        Result:
            - previous_world: position from the LAST frame
            - world: position for the CURRENT frame
            - Both values are used in lerp_world(alpha) for smooth rendering

        Args:
            parent_world: The parent node's world transform, or None if top-level.
                         If None, world = local (no parent influence).

        Timeline:
            Physics Update 1: recalc_world(parent) → prev=(0,0), world=(10,10)
            Physics Update 2: recalc_world(parent) → prev=(10,10), world=(20,20)
            Physics Update 3: recalc_world(parent) → prev=(20,20), world=(30,30)
        """
        self.previous_world.set_from(self.world)
        if parent_world is None:
            self.world.set_from(self.local)
        else:
            self.local.combine(parent_world, out=self.world)
        self.dirty = False

    def reset_interpolation(self) -> None:
        """Aligns previous_world with world so there is no interpolation jitter on
        this frame.
        Called on teleport or when an entity has just been spawned.
        """
        self.previous_world.set_from(self.world)

    def lerp_world(self, alpha: float) -> Transform2D:
        """Linearly interpolates from previous_world to world with alpha in the
        range 0.0 to 1.0.

        THIS IS WHAT POWERS SMOOTH RENDERING!

        Concept:
            Do not render the object at its world position directly.
            Interpolate between the previous position (previous_world) and the
            current position (world). Use alpha to decide how far between the
            two we are.

        Formula:
            result = previous + (current - previous) * alpha
                   = previous * (1 - alpha) + current * alpha

        Example:
            previous_world.position = (0, 0)    # last frame's position
            world.position = (100, 100)         # current frame's position

            lerp_world(0.0) → render at (0, 0)      [just updated]
            lerp_world(0.25) → render at (25, 25)   [25% of the way]
            lerp_world(0.5) → render at (50, 50)    [50% of the way]
            lerp_world(0.75) → render at (75, 75)   [75% of the way]
            lerp_world(1.0) → render at (100, 100)  [nearly the next update]

        Result: motion looks smooth even when the physics update rate < render rate!

        Args:
            alpha: Interpolation parameter [0.0, 1.0].
                0.0 = render at previous_world (fresh update)
                1.0 = render at world (old, stale)

        Returns:
            A Transform2D representing the interpolated world position.
            This is the one that must be used for rendering this frame.
        """
        # Fast path alpha >= 1.0: result is identical to world — skip the 6
        # lerp calls + tuple arithmetic (the hot render traversal path
        # calls this per sprite per frame with alpha=1.0).
        world = self.world
        if alpha >= 1.0:
            return Transform2D(
                position=world.position,
                rotation=world.rotation,
                scale=world.scale,
            )
        previous = self.previous_world
        return Transform2D(
            position=(
                lerp(previous.position[0], world.position[0], alpha),
                lerp(previous.position[1], world.position[1], alpha),
            ),
            rotation=lerp(previous.rotation, world.rotation, alpha),
            scale=(
                lerp(previous.scale[0], world.scale[0], alpha),
                lerp(previous.scale[1], world.scale[1], alpha),
            ),
        )
