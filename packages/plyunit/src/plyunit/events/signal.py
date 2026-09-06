"""Core-safe one-to-many Signal (no cyclic dependencies).

Provides:
- ``Signal`` — simple pub/sub event with weak-ref listeners
- ``@on`` — decorator for declaring signal bindings from Unit methods
- ``wire_bindings`` / ``unwire_bindings`` — lifecycle wiring
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal
from weakref import WeakMethod

if TYPE_CHECKING:
    from plyunit.core.components.component import Component
    from plyunit.core.units.unit import Unit

# Attribute name attached to methods by @on
_BINDING_ATTR = "_plyunit_on_bindings"


class _ListenerRef:
    """Listener reference holding a weakref for bound methods.

    Bound methods (``obj.method``) are held via ``WeakMethod`` so the listener
    is released automatically when the ``obj`` instance is garbage-collected.
    Plain functions are held strongly because they have no lifecycle owner.

    Attributes:
        _strong: Strongly held callable (plain function), or ``None``.
        _weak: ``WeakMethod`` for a bound method, or ``None``.
    """

    __slots__ = ("_strong", "_weak")

    def __init__(self, callback: Callable[..., None]) -> None:
        """Create a ``_ListenerRef`` from a callback.

        Args:
            callback: A plain callable or a bound method.
        """
        self._strong: Callable[..., None] | None = None
        self._weak: Callable[[], Callable[..., None] | None] | None = None
        if hasattr(callback, "__self__") and callback.__self__ is not None:
            self._weak = WeakMethod(callback)
            return
        self._strong = callback

    def resolve(self) -> Callable[..., None] | None:
        """Resolve the original callable, or ``None`` if the target was GC'd.

        Returns:
            Callable[..., None] | None: The live callable, or ``None`` if the
            bound method target has been garbage-collected.
        """
        if self._strong is not None:
            return self._strong
        if self._weak is None:
            return None
        return self._weak()

    def matches(self, callback: Callable[..., None]) -> bool:
        """Check whether this ref belongs to the same ``callback``.

        Args:
            callback: The callable to match against.

        Returns:
            True if the resolved callable equals ``callback``.
        """
        resolved = self.resolve()
        return resolved is not None and resolved == callback


class Signal:
    """One-to-many slot for callbacks without cyclic dependencies.

    Supports adding/removing listeners per identity. Weak listeners (bound
    methods) are released automatically when the instance is GC'd; plain
    functions are held for as long as the ``Signal`` lives.

    Attributes:
        _name: Optional label for debugging.
        _listeners: Internal list of ``_ListenerRef``.
    """

    def __init__(self, name: str = "") -> None:
        """Initialize an empty Signal.

        Args:
            name: Optional diagnostic label (shown in ``__repr__``).
        """
        self._name = name
        self._listeners: list[_ListenerRef] = []

    def _compact_dead(self) -> None:
        """Drop weak listeners whose target has been GC'd."""
        self._listeners = [e for e in self._listeners if e.resolve() is not None]

    def connect(self, callback: Callable[..., None]) -> None:
        """Register a callback; idempotent for the same callback identity.

        Args:
            callback: Function or bound method to be called on ``emit``.
        """
        self._compact_dead()
        for entry in self._listeners:
            if entry.matches(callback):
                return
        self._listeners.append(_ListenerRef(callback))

    def disconnect(self, callback: Callable[..., None]) -> None:
        """Remove a callback if it is registered.

        Args:
            callback: The callable to remove (no-op if absent).
        """
        self._compact_dead()
        for index, entry in enumerate(self._listeners):
            if entry.matches(callback):
                self._listeners.pop(index)
                return

    def disconnect_all(self) -> None:
        """Remove all registered listeners from the signal.

        Returns:
            None: Does not return a value.
        """
        self._listeners.clear()

    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Call all live listeners with the given arguments.

        Args:
            *args: Positional args for the listeners.
            **kwargs: Keyword args for the listeners.
        """
        callbacks: list[Callable[..., None]] = []
        alive: list[_ListenerRef] = []
        for entry in self._listeners:
            listener = entry.resolve()
            if listener is None:
                continue
            callbacks.append(listener)
            alive.append(entry)
        self._listeners = alive
        for listener in callbacks:
            listener(*args, **kwargs)

    def __len__(self) -> int:
        """Count the number of live listeners.

        Returns:
            int: The listener count (dead weak refs are dropped first).
        """
        self._compact_dead()
        return len(self._listeners)

    def __repr__(self) -> str:
        """Build a string representation for debugging.

        Returns:
            str: A concise signal representation with name and listener count.
        """
        label = f"'{self._name}' " if self._name else ""
        return f"Signal({label}listeners={len(self._listeners)})"


class _SignalBinding:
    """Metadata for a single ``@on`` binding. Stored on the method at class creation.

    Attributes:
        target: Target child unit name, or ``None`` for ``self``.
        component_type: Target component type, or ``None`` if the target is
            a unit directly.
        event_name: Name of the Signal attribute to connect.
        scope: Lookup scope (``"scene"``, ``"global"``, ``"mixed"``).
    """

    __slots__ = ("component_type", "event_name", "scope", "target")
    target: str | None
    component_type: type[Component] | None
    event_name: str
    scope: Literal["scene", "global", "mixed"]

    def __init__(
        self,
        target: str | None,
        component_type: type[Component] | None = None,
        *,
        event_name: str,
        scope: Literal["scene", "global", "mixed"],
    ) -> None:
        """Initialize the binding metadata.

        Args:
            target: Child unit name or ``None``.
            component_type: Target component type.
            event_name: Signal name.
            scope: Lookup scope.
        """
        self.target = target
        self.component_type = component_type
        self.event_name = event_name
        self.scope = scope

    def __repr__(self) -> str:
        """Build a string representation for debugging.

        Returns:
            str: An ``@on(...)`` string with target, component, and event details.
        """
        if not self.component_type:
            return f"@on({self.target!r}, {self.event_name!r})"

        if isinstance(self.component_type, str):
            return f"@on({self.target!r}, {self.component_type}, {self.event_name!r})"
        return (
            f"@on({self.target!r}, {self.component_type.__name__}, {self.event_name!r})"
        )


def on(
    target: str | None,
    component: type[Component] | None = None,
    *,
    event: str,
    scope: Literal["scene", "global", "mixed"] = "mixed",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declarative signal binding for methods inside a Unit.

    Args:
        target: Child unit name (``str``) → looked up in ``self.u[target]``
            first, then in ``self.parent.u[target]`` if absent. ``None`` →
            the unit itself (``self``).
        component: If ``type[Component]`` → take the signal from the
            component of this type (the target unit must have it).
        event: Name of the Signal attribute to connect.
        scope: Lookup scope (``"scene"``, ``"global"``, ``"mixed"``).

    Returns:
        A decorator that attaches ``_SignalBinding`` metadata to the method.

    Raises:
        ValueError: If ``component`` is not a class type or ``scope`` is invalid.

    Examples:
        >>> @on("Enemy", event="died")
        >>> def _on_enemy_died(self): ...
        >>> @on("Enemy", Health, event="on_low_hp")
        >>> def _on_enemy_low_hp(self): ...
        >>> @on(None, event="on_child_removed")
        >>> def _on_child_removed(self): ...
    """

    if component is not None and not isinstance(component, type):
        raise ValueError("component harus berupa tipe class, bukan instance")

    if scope not in {"scene", "global", "mixed"}:
        raise ValueError("scope harus salah satu: scene, global, mixed")

    binding = _SignalBinding(target, component, event_name=event, scope=scope)

    def decorator(method: Callable[..., Any]) -> Callable[..., Any]:
        """Attach binding metadata to the method (multiple ``@on`` allowed)."""
        # Attach metadata to the method — safe because one method can have many @on
        existing: list[_SignalBinding] = getattr(method, _BINDING_ATTR, [])
        if not existing:
            # Create a new list so it is not shared with other methods
            existing = []
            setattr(method, _BINDING_ATTR, existing)
        existing.append(binding)
        return method

    return decorator


def wire_bindings(unit: Unit) -> list[tuple[Signal, Callable[..., Any]]]:
    """Scan all methods of a unit, resolve and connect all ``@on`` bindings.

    Iterates the MRO to catch ``@on`` from parent classes as well. Called
    AFTER ``on_ready()`` completes (children already exist).

    Args:
        unit: The Unit instance to scan.

    Returns:
        list[tuple[Signal, Callable]]: The list of ``(signal, callback)``
        pairs successfully connected. Stored in ``unit._plyunit_on_bindings``
        for later disconnecting.
    """

    connected: list[tuple[Signal, Callable[..., Any]]] = []

    # Iterate the class MRO to catch inherited @on too
    seen_names: set[str] = set()
    for cls in type(unit).__mro__:
        for attr_name, raw_method in vars(cls).items():
            if attr_name in seen_names:
                continue
            seen_names.add(attr_name)

            bindings: list[_SignalBinding] = getattr(raw_method, _BINDING_ATTR, [])
            if not bindings:
                continue

            # Bound method on the instance
            bound_callback = getattr(unit, attr_name)

            for binding in bindings:
                signal = _resolve_signal(unit, binding)
                for s in signal:
                    s.connect(bound_callback)
                    connected.append((s, bound_callback))

    if not hasattr(unit, "_plyunit_on_bindings"):
        unit._plyunit_on_bindings = []
    setters = getattr(unit, "_plyunit_on_bindings", [])
    for signal, value in setters:
        signal.set(value)

    return connected


def unwire_bindings(
    wired: list[tuple[Signal, Callable[..., Any]]] | None = None,
    *,
    unit: Unit | None = None,
) -> None:
    """Disconnect all previously wired signals.

    Called from ``_call_exit()``. If ``wired`` is not given, use
    ``unit._plyunit_on_bindings``.

    Args:
        wired: The list of ``(signal, callback)`` pairs to disconnect.
        unit: Fallback unit to fetch ``_plyunit_on_bindings`` from.
    """
    if wired is None and unit is not None:
        wired = getattr(unit, "_plyunit_on_bindings", [])

    if wired is None:
        return

    for signal, callback in wired:
        signal.disconnect(callback)
    wired.clear()


def _resolve_signal(unit: Unit, binding: _SignalBinding) -> list[Signal]:
    """Resolve a ``_SignalBinding`` to the list of actual ``Signal`` objects.

    Args:
        unit: The starting unit for the lookup.
        binding: Binding metadata.

    Returns:
        list[Signal]: The signals found. May be empty if the target or event
        is missing (silent fail with a warning — so ``@on`` does not crash
        the game).
    """

    # 1. Resolve target unit
    if binding.target is None:
        owners = [unit]
    else:
        owners = unit.group(binding.target, scope=binding.scope)

        if len(owners) == 0:
            warnings.warn(
                f"@on: target unit '{binding.target}' tidak ditemukan "
                "Binding diabaikan.",
                stacklevel=3,
            )
            return []

    # 2. Resolve signal holder (unit or component)
    if binding.component_type is not None:
        holders = []
        for owner in owners:
            # To resolve a component, the unit must have a 'components' dict.
            # If absent, the unit does not support components and the
            # binding is ignored.
            if not hasattr(owner, "components"):
                warnings.warn(
                    f"@on: unit '{owner.name}' tidak punya components. "
                    "Binding diabaikan.",
                    stacklevel=3,
                )
                continue

            # Ensure component_type exists in unit.components; if absent,
            # the unit does not have the intended component and the
            # binding is ignored.
            if binding.component_type not in owner.components:
                component_name = (
                    binding.component_type.__name__
                    if isinstance(binding.component_type, type)
                    else binding.component_type
                )
                warnings.warn(
                    f"@on: unit '{owner.name}' tidak punya component "
                    f"'{component_name}'. Binding diabaikan.",
                    stacklevel=3,
                )
                continue

            # owner is guaranteed to have this component because it was checked above
            holders.append(owner[binding.component_type])  # type: ignore
        if not holders:
            return []

    else:
        holders = owners

    # 3. Resolve signal attribute
    signals = []
    for holder in holders:
        signal = getattr(holder, binding.event_name, None)
        if signal is None or not isinstance(signal, Signal):
            warnings.warn(
                f"@on: '{type(holder).__name__}.{binding.event_name}' "
                f"bukan Signal atau tidak ada. Binding diabaikan.",
                stacklevel=3,
            )
            continue
        signals.append(signal)
    return signals
