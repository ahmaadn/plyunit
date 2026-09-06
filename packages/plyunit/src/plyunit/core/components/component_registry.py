"""Process-global weak component registry (exact type only)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from weakref import WeakSet

if TYPE_CHECKING:
    from plyunit.core.components.component import Component
    from plyunit.core.units.node_unit import NodeUnit


class ComponentRegistry:
    """
    Maps component types to the weak set of owning units (exact type, not subclasses).
    """

    __slots__ = ("_by_type",)

    def __init__(self) -> None:
        """Initializes an empty component index."""
        self._by_type: dict[type, WeakSet] = {}

    def register(self, unit: NodeUnit, component_type: type[Component]) -> None:
        """Registers ``unit`` in the index for ``component_type``.

        Args:
            unit: The ``NodeUnit`` that owns the component.
            component_type: The component type (exact).
        """
        bucket = self._by_type.get(component_type)
        if bucket is None:
            bucket = WeakSet()
            self._by_type[component_type] = bucket
        bucket.add(unit)

    def unregister(self, unit: NodeUnit, component_type: type[Component]) -> None:
        """Removes ``unit`` from the index for ``component_type``.

        Args:
            unit: The ``NodeUnit`` to remove.
            component_type: The component type.
        """
        bucket = self._by_type.get(component_type)
        if bucket is None:
            return
        bucket.discard(unit)
        if not bucket:
            del self._by_type[component_type]

    def units_with(self, component_type: type[Component]) -> list[NodeUnit]:
        """Returns all units that own a component of type ``component_type``.

        Args:
            component_type: The component type to look up.

        Returns:
            list[NodeUnit]: The list of owning units (may be empty).
        """
        bucket = self._by_type.get(component_type)
        if bucket is None:
            return []
        return list(bucket)

    def clear(self) -> None:
        """Clears the entire component index."""
        self._by_type.clear()


components = ComponentRegistry()
"""Process-wide global registry for all components."""
