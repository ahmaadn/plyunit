"""Base ``Unit`` class plus the ``UnitKind`` and ``QueryScope`` type aliases."""

from __future__ import annotations

import logging
from typing import Any, Literal, overload

from .unit_registry import NoResultFound, UnitRegistry, units

logger = logging.getLogger(__name__)

UnitKind = Literal["none", "scene", "service"]
"""Kind of unit singleton: ``none`` (not a singleton), ``scene``, or ``service``."""

QueryScope = Literal["scene", "global", "mixed"]
"""Unit query scope: ``scene``, ``global``, or ``mixed`` (scene-first)."""


class Unit:
    """
    Base class for Unit and UnitSingleton. Not used directly, but serves as a
    common ancestor for type checking.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        is_unique: bool = False,
        tags: set[str] | None = None,
        register: bool = False,
        unit_kind: UnitKind = "none",
    ) -> None:
        """Initialize the Unit with a name, tags, and optional registration.

        Args:
            name: Unit name (``None`` → class name).
            is_unique: Mark the unit as unique (indexed under unique_name).
            tags: Initial set of tags.
            register: Force registration in the global registry even if not a singleton.
            unit_kind: Singleton kind (``"none"`` | ``"scene"`` | ``"service"``).

        Raises:
            ValueError: If ``unit_kind`` is not a valid value.
        """

        self.name = self.__class__.__name__ if name is None else name
        self._is_unique = is_unique
        self.tags = set(tags if tags else [])

        if unit_kind not in {"none", "scene", "service"}:
            raise ValueError("unit_kind must be one of: none, scene, service")
        self.singleton_kind: UnitKind = unit_kind

        self.global_units: UnitRegistry = units
        self.units: UnitRegistry | None = units

        # State flags
        if self.is_singleton or register:
            # Auto-register singletons into the global registry
            self.global_units.register(self)

    @property
    def is_unique(self) -> bool:
        """Whether this unit is marked as unique (indexed under unique_name)."""
        return self._is_unique

    def destroy(self) -> None:
        """
        Destroy this unit, call on_exit and on_destroy for all components, and
        unregister it from the registry.
        """

        registry = self._membership_registry()
        if registry is not None:
            registry.unregister(self)

    @property
    def is_singleton(self) -> bool:
        """Whether this unit is a singleton (``scene`` or ``service``)."""
        return self.singleton_kind != "none"

    @property
    def can_unregister_from_global(self) -> bool:
        """Whether this unit may be unregistered from the global registry.

        Any unit can be explicitly removed from the registry.
        """
        return True

    def _membership_registry(self) -> UnitRegistry | None:
        """Returns the registry where this unit should be registered."""
        if self.is_singleton:
            return self.global_units
        return self.units

    def _scene_registry(self) -> UnitRegistry | None:
        """Returns the scene registry for ``scope="scene"`` queries.

        ``SceneUnit`` overrides this; ``NodeUnit`` uses ``_scene_tree``.
        """
        return None

    def add_tag(self, tag: str) -> None:
        """Add a *tag* to this unit.

        Args:
            tag: String label. Convention: lowercase, words separated by
                underscores. Examples: ``"enemy"``, ``"flying"``, ``"damageable"``.
        """

        if tag in self.tags:
            return
        self.tags.add(tag)
        registry = self._membership_registry()
        if registry is not None and registry.contains(self):
            registry.add_tag(self, tag)

    def has_tag(self, tag: str) -> bool:
        """Check whether this unit has the given *tag*.

        Args:
            tag: String label to check.
        Returns:
            True if this unit has the tag, False otherwise.
        """
        return tag in self.tags

    def set_tags(self, tags: set[str] | None = None) -> None:
        """Set the *tags* of this unit, replacing the existing tags.

        Args:
            tags: New set replacing the existing tags.
        """
        old_tags = set(self.tags)
        registry = self._membership_registry()

        if registry is not None and registry.contains(self):
            for old_tag in old_tags:
                registry.remove_tag(self, old_tag)

        self.tags = set(tags if tags else [])
        if registry is not None and registry.contains(self):
            for new_tag in self.tags:
                registry.add_tag(self, new_tag)

    def remove_tag(self, tag: str) -> None:
        """Dynamically remove a *tag* from this unit.

        Args:
            tag: Tag to remove. Silently ignored if absent.
        """
        if tag not in self.tags:
            return
        self.tags.discard(tag)
        registry = self._membership_registry()
        if registry is not None and registry.contains(self):
            registry.remove_tag(self, tag)

    @overload
    def group[T: Unit](
        self,
        unit_ref: type[T],
        *,
        scope: QueryScope = "mixed",
    ) -> list[T]: ...

    @overload
    def group(
        self,
        unit_ref: str,
        *,
        scope: QueryScope = "mixed",
    ) -> list[Unit]: ...

    def group[T: Unit](
        self,
        unit_ref: type[T] | str,
        *,
        scope: QueryScope = "mixed",
    ) -> list[Unit] | list[T]:
        """Query all units matching a class or name reference.

        Args:
            unit_ref: Unit class or name to match.
            scope: Query scope: ``"scene"``, ``"global"``, or ``"mixed"``.

        Returns:
            List of matching units (possibly empty).

        Raises:
            ValueError: If ``scope`` is not a valid value.
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        # if a service unit queries with a scope other than global,
        # that may indicate a bug.
        # ServiceUnit may only query the global registry.
        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.group(unit_ref)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                return []
            return scene_registry.group(unit_ref)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            scene_result = scene_registry.group(unit_ref)
            if len(scene_result) > 0:
                return scene_result

        return self.global_units.group(unit_ref)

    # --- explicit query helpers (by-name, by-tag, unique-name) --------------
    def find_by_name(self, name: str, *, scope: QueryScope = "mixed") -> list[Unit]:
        """Find units by name with scope resolution.

        Args:
            name: Unit name to search for.
            scope: One of `"scene"`, `"global"`, or `"mixed"`.

        Returns:
            List of units (possibly empty).
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.find_by_name(name)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                return []
            return scene_registry.find_by_name(name)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            scene_result = scene_registry.find_by_name(name)
            if len(scene_result) > 0:
                return scene_result

        return self.global_units.find_by_name(name)

    def find_by_tag(self, tag: str, *, scope: QueryScope = "mixed") -> list[Unit]:
        """Find units by tag with scope resolution.

        Args:
            tag: Tag to search for (without the `#` prefix).
            scope: `"scene"` | `"global"` | `"mixed"`.

        Returns:
            List of matching units.
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.find_by_tag(tag)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                return []
            return scene_registry.find_by_tag(tag)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            scene_result = scene_registry.find_by_tag(tag)
            if len(scene_result) > 0:
                return scene_result

        return self.global_units.find_by_tag(tag)

    def find_unique_name(self, name: str, *, scope: QueryScope = "mixed") -> list[Unit]:
        """Find units registered under a unique name.

        Args:
            name: Unique name to search for (without the `@` prefix).
            scope: `"scene"` | `"global"` | `"mixed"`.

        Returns:
            List containing the unique unit, or an empty list if none.
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.find_unique_name(name)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                return []
            return scene_registry.find_unique_name(name)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            scene_result = scene_registry.find_unique_name(name)
            if len(scene_result) > 0:
                return scene_result

        return self.global_units.find_unique_name(name)

    @overload
    def one[T](
        self,
        unit_ref: type[T],
        *,
        scope: QueryScope = "mixed",
    ) -> T: ...

    @overload
    def one(
        self,
        unit_ref: str,
        *,
        scope: QueryScope = "mixed",
    ) -> Any: ...

    def one[T](
        self,
        unit_ref: type[T] | str,
        *,
        scope: QueryScope = "mixed",
    ) -> Any:
        """Query exactly one unit matching a class or name reference.

        Args:
            unit_ref: Unit class or name to match.
            scope: Query scope: ``"scene"``, ``"global"``, or ``"mixed"``.

        Returns:
            The matching unit.

        Raises:
            NoResultFound: If no unit matches the reference.
            MultipleResultsFound: If more than one unit matches.
            ValueError: If ``scope`` is not a valid value.
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.one(unit_ref)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                raise NoResultFound(f"No unit found for reference: {unit_ref}")
            return scene_registry.one(unit_ref)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            result = scene_registry.one_or_none(unit_ref)
            if result is not None:
                return result

        return self.global_units.one(unit_ref)

    @overload
    def one_or_none[T](
        self,
        unit_ref: type[T],
        *,
        scope: QueryScope = "mixed",
    ) -> T | None: ...

    @overload
    def one_or_none(
        self,
        unit_ref: str,
        *,
        scope: QueryScope = "mixed",
    ) -> Any: ...

    def one_or_none[T](
        self,
        unit_ref: type[T] | str,
        *,
        scope: QueryScope = "mixed",
    ) -> Any:
        """Query one unit matching a class or name reference, or ``None``.

        Args:
            unit_ref: Unit class or name to match.
            scope: Query scope: ``"scene"``, ``"global"``, or ``"mixed"``.

        Returns:
            The matching unit, or ``None`` if no unit matches.

        Raises:
            ValueError: If ``scope`` is not a valid value.
        """
        if scope not in {"scene", "global", "mixed"}:
            raise ValueError("scope must be one of: scene, global, mixed")

        if self.singleton_kind == "service" and scope != "global":
            scope = "global"

        if scope == "global":
            return self.global_units.one_or_none(unit_ref)

        scene_registry = self._scene_registry()
        if scope == "scene":
            if scene_registry is None:
                return None
            return scene_registry.one_or_none(unit_ref)

        # mixed: scene-first with global fallback
        if scene_registry is not None:
            result = scene_registry.one_or_none(unit_ref)
            if result is not None:
                return result

        return self.global_units.one_or_none(unit_ref)
