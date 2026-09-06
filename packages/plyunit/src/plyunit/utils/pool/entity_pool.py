"""Generation-based entity pool for ``NodeUnit`` reuse."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plyunit.core.units.node_unit import NodeUnit


@dataclass(frozen=True, slots=True)
class EntityHandle:
    """Lightweight handle to an entity in an ``EntityPool``.

    Attributes:
        index: Internal pool slot index.
        generation: Slot generation number; bumped on every ``release``
            so old handles automatically become stale.
    """

    index: int
    generation: int


class EntityPool:
    """Pool of ``NodeUnit`` entities addressed via generation-checked handles.

    The ``release`` contract (execution order):

    1. Generation / aliveness check (a stale handle is a no-op).
    2. Detach from the scene tree when currently attached.
    3. Remove from the global ``SpatialIndex`` service, if any.
    4. Call ``entity.reset()`` when implemented.
    5. Call ``component.reset()`` on every attached component.
    6. Mark dead, bump the generation, and return the slot to the free list.

    Pooled units and components may implement ``reset()`` to clear runtime
    state before reuse. Stale handles never resolve to a live entity after
    ``release``.

    Attributes:
        _factory: Callable that creates a new ``NodeUnit`` when a slot is empty.
        _capacity: Current pool capacity (doubled by ``_grow``).
        _entities: Per-slot entity list.
        _generations: Per-slot generation number list.
        _live: Per-slot active flag list.
        _free: Stack of empty slot indices for ``acquire``.
    """

    __slots__ = (
        "_capacity",
        "_entities",
        "_factory",
        "_free",
        "_generations",
        "_live",
    )

    def __init__(
        self,
        factory: Callable[[], NodeUnit],
        *,
        capacity: int = 64,
    ) -> None:
        """Initialize the pool with a factory and an initial capacity.

        Args:
            factory: Function that creates a new ``NodeUnit`` when a slot is empty.
            capacity: Initial pool capacity.

        Raises:
            ValueError: If ``capacity < 1``.
        """
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._factory = factory
        self._capacity = capacity
        self._entities: list[NodeUnit | None] = [None] * capacity
        self._generations: list[int] = [0] * capacity
        self._live: list[bool] = [False] * capacity
        self._free: list[int] = list(range(capacity - 1, -1, -1))

    def acquire(self) -> EntityHandle:
        """Take an entity from the pool, creating a new one when a slot is empty.

        Returns:
            EntityHandle: Handle pointing to the newly active slot.

        Note:
            The pool auto-grows (``_grow``) when the free list is exhausted.
        """
        if not self._free:
            self._grow()
        index = self._free.pop()
        entity = self._entities[index]
        if entity is None:
            entity = self._factory()
            self._entities[index] = entity
        self._live[index] = True
        return EntityHandle(index=index, generation=self._generations[index])

    def release(self, handle: EntityHandle) -> None:
        """Return an entity to the pool, running the full cleanup contract.

        Args:
            handle: Handle of the entity to release. Stale handles are ignored.

        Note:
            Follows the contract in the class docstring: detach → spatial
            remove → ``reset()`` → bump generation → return the slot.
        """
        if not self.is_alive(handle):
            return
        index = handle.index
        entity = self._entities[index]
        if entity is None:
            return

        # Resolve spatial before detaching (off-tree lookup loses global services).
        spatial = entity.one_or_none("@SpatialIndex", scope="global")

        scene = entity._scene_tree
        if scene is not None:
            parent = entity.parent
            if parent is not None:
                parent.detach(entity)
            elif scene._defer_tree_ops:
                scene._enqueue_detach(None, entity)
            else:
                scene._detach_subtree(entity)

        if spatial is not None:
            spatial.remove(entity)

        if hasattr(entity, "reset"):
            entity.reset()  # type: ignore[attr-defined]

        for component in list(entity.components.values()):
            if hasattr(component, "reset"):
                component.reset()  # type: ignore[attr-defined]

        self._live[index] = False
        self._generations[index] = (self._generations[index] + 1) & 0x7FFFFFFF
        self._free.append(index)

    def get(self, handle: EntityHandle) -> NodeUnit | None:
        """Resolve a handle to a live entity or ``None``.

        Args:
            handle: The handle to resolve.

        Returns:
            NodeUnit | None: The live entity, or ``None`` if the handle is stale.
        """
        if not self.is_alive(handle):
            return None
        return self._entities[handle.index]

    def is_alive(self, handle: EntityHandle) -> bool:
        """Check whether a handle is still alive (valid index + matching generation).

        Args:
            handle: The handle to test.

        Returns:
            bool: ``True`` if the handle points to an active, live slot.
        """
        index = handle.index
        if index < 0 or index >= len(self._entities):
            return False
        return self._live[index] and self._generations[index] == handle.generation

    def _grow(self) -> None:
        """Double the pool capacity when the free list is exhausted."""
        old = self._capacity
        new_cap = old * 2
        self._entities.extend([None] * old)
        self._generations.extend([0] * old)
        self._live.extend([False] * old)
        self._free.extend(range(new_cap - 1, old - 1, -1))
        self._capacity = new_cap
