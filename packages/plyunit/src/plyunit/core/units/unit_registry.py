"""Unit registry with identity-keyed indexes and string-reference queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from .unit import Unit

TAG_QUERY = "#"
"""Prefix that marks a string unit reference as a tag query."""

UNIQUE_QUERY = "@"
"""Prefix that marks a string unit reference as a unique-name query."""


class NoResultFound(LookupError):
    """Raised when `.one()` is called but no rows match."""


class MultipleResultsFound(LookupError):
    """Raised when `.one()` is called but multiple rows match."""


class UnitRegistry:
    """Strong, indexed owner for units.

    Every index stores units by identity. This keeps registered units alive while
    making membership, exact removal, and singular lookup constant-time. List
    queries still cost O(number of results) because they materialize a list.
    """

    def __init__(self) -> None:
        """Initialize empty identity-keyed indexes and service lifecycle state."""
        self._members: dict[int, Unit] = {}
        self._by_name: dict[str, dict[int, Unit]] = {}
        self._by_tag: dict[str, dict[int, Unit]] = {}
        self._by_type: dict[type, dict[int, Unit]] = {}
        self._unique_candidates: dict[str, dict[int, Unit]] = {}
        self._unique_name: dict[str, Unit] = {}

        # Registry-owned lifecycle state for services. OrderedDict gives reverse
        # teardown order without a second list of service instances on App.
        self._service_order: dict[int, Unit] = {}
        self._active_app: Unit | None = None

    def __getitem__(self, key):
        """Shortcut for :meth:`one` (supports string or ``type``)."""
        return self.one(key)

    @staticmethod
    def _tag_key(tag: str) -> str:
        """Normalize a tag for case-insensitive index lookups."""
        return tag.lower()

    def contains(self, unit: Unit) -> bool:
        """Return whether this exact object is registered."""
        return self._members.get(id(unit)) is unit

    def register(self, unit: Unit) -> None:
        """Register ``unit`` in name, tag, type, and unique indexes."""
        unit_id = id(unit)
        if self._members.get(unit_id) is unit:
            return

        self._members[unit_id] = unit
        self._by_name.setdefault(unit.name, {})[unit_id] = unit
        for tag in unit.tags:
            self._by_tag.setdefault(self._tag_key(tag), {})[unit_id] = unit
        self._by_type.setdefault(type(unit), {})[unit_id] = unit

        if unit.is_unique:
            candidates = self._unique_candidates.setdefault(unit.name, {})
            candidates[unit_id] = unit
            self._unique_name.setdefault(unit.name, unit)

        if unit.singleton_kind == "service":
            self._service_order[unit_id] = unit
            if getattr(unit, "_service_init_complete", False):
                self._service_ready(unit)

    def _service_ready(self, service: Unit) -> None:
        """Attach a fully initialized service to the active App, if any."""
        app = self._active_app
        if app is None or getattr(service, "_is_app_root", False):
            return
        attach = getattr(service, "_attach_to_app", None)
        if attach is not None:
            attach(app)

    def activate_app(self, app: Unit) -> None:
        """Set the active App and attach all already-ready services to it."""
        previous = self._active_app
        if previous is app:
            return
        if previous is not None:
            for service in reversed(tuple(self._service_order.values())):
                if service is previous:
                    continue
                detach = getattr(service, "_detach_from_app", None)
                if detach is not None:
                    detach(previous)
        self._active_app = app
        for service in self._service_order.values():
            if getattr(service, "_is_app_root", False) or not getattr(
                service, "_service_init_complete", False
            ):
                continue
            attach = getattr(service, "_attach_to_app", None)
            if attach is not None:
                attach(app)

    def services_for_app(self, app: Unit) -> list[Unit]:
        """Return this App's attached services in reverse registration order."""
        return [
            service
            for service in reversed(tuple(self._service_order.values()))
            if getattr(service, "_attached_app", None) is app
        ]

    def _remove_from_bucket(
        self, buckets: dict[Any, dict[int, Unit]], key: Any, unit_id: int
    ) -> None:
        """Drop ``unit_id`` from ``buckets[key]``; remove the bucket when empty."""
        bucket = buckets.get(key)
        if bucket is None:
            return
        if not isinstance(bucket, dict):
            return
        bucket.pop(unit_id, None)
        if not bucket:
            buckets.pop(key, None)

    def unregister(self, unit: Unit) -> None:
        """Remove ``unit`` from every index and release registry ownership."""
        unit_id = id(unit)
        if self._members.get(unit_id) is not unit:
            return

        detach_error: BaseException | None = None
        if unit.singleton_kind == "service":
            detach = getattr(unit, "_detach_from_app", None)
            app = getattr(unit, "_attached_app", None)
            if detach is not None and app is not None:
                try:
                    detach(app)
                except BaseException as exc:
                    detach_error = exc
            self._service_order.pop(unit_id, None)

        self._remove_from_bucket(self._by_name, unit.name, unit_id)
        for tag in unit.tags:
            self._remove_from_bucket(self._by_tag, self._tag_key(tag), unit_id)
        self._remove_from_bucket(self._by_type, type(unit), unit_id)

        if unit.is_unique:
            candidates = self._unique_candidates.get(unit.name)
            if candidates is not None:
                candidates.pop(unit_id, None)
                if candidates:
                    self._unique_name[unit.name] = next(iter(candidates.values()))
                else:
                    self._unique_candidates.pop(unit.name, None)
                    self._unique_name.pop(unit.name, None)

        self._members.pop(unit_id, None)
        if self._active_app is unit:
            self._active_app = None
        if detach_error is not None:
            raise detach_error

    remove = unregister

    def find_by_name(self, name: str) -> list[Unit]:
        """Return all registered units with the given name."""
        return list(self._by_name.get(name, {}).values())

    def find_by_tag(self, tag: str) -> list[Unit]:
        """Return all registered units carrying the given tag."""
        return list(self._by_tag.get(self._tag_key(tag), {}).values())

    def find_unique_name(self, name: str) -> list[Unit]:
        """Return the unique unit registered under ``name`` (empty list if none)."""
        unit = self._unique_name.get(name)
        return [unit] if unit is not None else []

    def add_tag(self, unit: Unit, tag: str) -> None:
        """Index ``tag`` for an already-registered ``unit``.

        Args:
            unit: Registered unit to index.
            tag: Tag to add to the tag index.
        """
        if not self.contains(unit):
            return
        self._by_tag.setdefault(self._tag_key(tag), {})[id(unit)] = unit

    def remove_tag(self, unit: Unit, tag: str) -> None:
        """Remove ``tag`` from the tag index for a registered ``unit``.

        Args:
            unit: Registered unit to update.
            tag: Tag to remove from the tag index.
        """
        self._remove_from_bucket(self._by_tag, self._tag_key(tag), id(unit))

    def group[T](self, unit_ref: type[T] | str) -> list[T] | list[Unit]:
        """Query units by type, name, ``#tag``, or ``@unique_name`` reference.

        Args:
            unit_ref: Unit class, plain name, ``"#tag"``, or ``"@unique_name"``.

        Returns:
            List of matching units (possibly empty).
        """
        if not isinstance(unit_ref, str):
            return list(self._by_type.get(unit_ref, {}).values())
        if unit_ref:
            if unit_ref[0] == TAG_QUERY:
                return self.find_by_tag(unit_ref[1:])
            if unit_ref[0] == UNIQUE_QUERY:
                return self.find_unique_name(unit_ref[1:])
        return self.find_by_name(unit_ref)

    @staticmethod
    def _one_from_bucket[T](bucket, label: str | T | type[T]) -> T:
        """Return the single unit in ``bucket``; raise on empty or ambiguous."""
        if not bucket:
            raise NoResultFound(f"No rows found for {label} one()")
        if len(bucket) > 1:
            raise MultipleResultsFound(f"Multiple rows found for {label} one()")
        return next(iter(bucket.values()))

    @staticmethod
    def _one_or_none_from_bucket[T](bucket, label: str | T | type[T]) -> T | None:
        """Return the single unit in ``bucket`` or ``None``; raise if ambiguous."""
        if not bucket:
            return None
        if len(bucket) > 1:
            raise MultipleResultsFound(f"Multiple rows found for {label} one_or_none()")
        return next(iter(bucket.values()))

    @overload
    def one[T](self, unit_ref: type[T]) -> T: ...
    @overload
    def one(self, unit_ref: str) -> Any: ...
    def one[T](self, unit_ref: type[T] | str) -> Any:
        """Query exactly one unit by type, name, ``#tag``, or ``@unique_name``.

        Args:
            unit_ref: Unit class, plain name, ``"#tag"``, or ``"@unique_name"``.

        Returns:
            The matching unit.

        Raises:
            NoResultFound: If no unit matches the reference.
            MultipleResultsFound: If more than one unit matches.
        """
        if not isinstance(unit_ref, str):
            return self._one_from_bucket(self._by_type.get(unit_ref), unit_ref)
        if unit_ref:
            if unit_ref[0] == TAG_QUERY:
                return self._one_from_bucket(
                    self._by_tag.get(self._tag_key(unit_ref[1:])), unit_ref
                )
            if unit_ref[0] == UNIQUE_QUERY:
                unit = self._unique_name.get(unit_ref[1:])
                if unit is None:
                    raise NoResultFound(f"No rows found for {unit_ref} one()")
                return unit
        return self._one_from_bucket(self._by_name.get(unit_ref), unit_ref)

    @overload
    def one_or_none[T](self, unit_ref: type[T]) -> T | None: ...
    @overload
    def one_or_none(self, unit_ref: str) -> Any: ...
    def one_or_none[T](self, unit_ref: type[T] | str) -> Any:
        """Query one unit by type, name, ``#tag``, or ``@unique_name``, or ``None``.

        Args:
            unit_ref: Unit class, plain name, ``"#tag"``, or ``"@unique_name"``.

        Returns:
            The matching unit, or ``None`` if no unit matches.

        Raises:
            MultipleResultsFound: If more than one unit matches.
        """
        if not isinstance(unit_ref, str):
            return self._one_or_none_from_bucket(self._by_type.get(unit_ref), unit_ref)
        if unit_ref:
            if unit_ref[0] == TAG_QUERY:
                return self._one_or_none_from_bucket(
                    self._by_tag.get(self._tag_key(unit_ref[1:])), unit_ref
                )
            if unit_ref[0] == UNIQUE_QUERY:
                return self._unique_name.get(unit_ref[1:])
        return self._one_or_none_from_bucket(self._by_name.get(unit_ref), unit_ref)


units = UnitRegistry()
"""Global process-wide registry for units registered as singletons."""
