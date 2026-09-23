"""EventBus service: priority-ordered listeners with immediate and deferred dispatch."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from weakref import WeakMethod

from plyunit.core.units.service_unit import ServiceUnit


class _ListenerRef:
    """Wrap a listener for weak referencing of bound methods.

    Bound methods are stored via :class:`weakref.WeakMethod` (auto-cleaned
    when the owner dies). Plain callables are stored strongly.

    Attributes:
        _strong: Strong reference to a non-method callable.
        _weak: Weak ref to a bound method (``None`` if not a method).
    """

    __slots__ = ("_strong", "_weak")

    def __init__(self, callback: Callable[..., None]) -> None:
        """Initialize the wrapper: weak for bound methods, strong for the rest.

        Args:
            callback: The listener to wrap.
        """
        self._strong: Callable[..., None] | None = None
        self._weak: Callable[[], Callable[..., None] | None] | None = None

        if hasattr(callback, "__self__") and callback.__self__ is not None:
            self._weak = WeakMethod(callback)
            return

        self._strong = callback

    def resolve(self) -> Callable[..., None] | None:
        """Resolve the original callable; ``None`` if the weak ref is dead."""
        if self._strong is not None:
            return self._strong
        if self._weak is None:
            return None
        return self._weak()

    def matches(self, callback: Callable[..., None]) -> bool:
        """Compare the resolved callable with a target callback.

        Args:
            callback: The listener to match against.

        Returns:
            bool: ``True`` if it equals the live listener.
        """
        resolved = self.resolve()
        if resolved is None:
            return False
        return resolved == callback


@dataclass(slots=True)
class _ListenerEntry:
    """Listener entry with priority and subscribe order.

    Attributes:
        ref: Weak/strong ref to the callable.
        priority: Execution priority (higher = runs first).
        seq: Subscribe sequence number (for stable order on equal priority).
    """

    ref: _ListenerRef
    priority: int
    seq: int


class EventBus(ServiceUnit):
    """Deferred event bus with priority-ordered listeners.

    - ``publish`` dispatches immediately (priority order).
    - ``defer`` queues events; ``dispatch`` drains a snapshot FIFO and
      publishes each item (listeners deferred during dispatch wait until
      the next ``dispatch``).
    - Higher ``priority`` runs first; equal priority keeps subscribe order.
    """

    def __init__(self) -> None:
        """Initialize the EventBus (ServiceUnit) with an empty default state."""
        super().__init__(name="EventBus", tags={"service", "events"})
        self._listeners: dict[str, list[_ListenerEntry]] = defaultdict(list)
        self._queue: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._seq = 0

    def _compact_dead(self, event_name: str) -> None:
        """Drop dead listeners (invalid weak refs) for a given event."""
        listeners = self._listeners.get(event_name)
        if not listeners:
            return

        alive = [entry for entry in listeners if entry.ref.resolve() is not None]
        if alive:
            self._listeners[event_name] = alive
        else:
            del self._listeners[event_name]

    def has_listeners(self, event_name: str) -> bool:
        """Check whether an event has any live listeners.

        Args:
            event_name: The event name.

        Returns:
            bool: ``True`` if at least one active listener exists.
        """
        self._compact_dead(event_name)
        listeners = self._listeners.get(event_name)
        return bool(listeners)

    def subscribe(
        self,
        event_name: str,
        listener: Callable[..., Any],
        *,
        priority: int = 0,
    ) -> None:
        """Register a listener for an event.

        Args:
            event_name: The event name.
            listener: Callable handler.
            priority: Priority (higher is called first).
        """
        self._compact_dead(event_name)
        entry = _ListenerEntry(
            ref=_ListenerRef(listener),
            priority=int(priority),
            seq=self._seq,
        )
        self._seq += 1
        bucket = self._listeners[event_name]
        # Keep sorted by (-priority, seq): higher priority first, stable ties.
        insert_at = len(bucket)
        for i, existing in enumerate(bucket):
            if (entry.priority, -entry.seq) > (existing.priority, -existing.seq):
                insert_at = i
                break
        bucket.insert(insert_at, entry)

    def unsubscribe(self, event_name: str, listener: Callable[..., None]) -> None:
        """Remove a listener from an event (no-op if not registered).

        Args:
            event_name: The event name.
            listener: The previously subscribed callable.
        """
        self._compact_dead(event_name)
        listeners = self._listeners.get(event_name)
        if not listeners:
            return

        for index, entry in enumerate(listeners):
            if entry.ref.matches(listener):
                listeners.pop(index)
                break

        if not listeners:
            del self._listeners[event_name]

    def publish(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event immediately (synchronous, priority order).

        Listeners that call :meth:`defer` from inside a handler will not be
        processed until the next :meth:`dispatch`.

        Args:
            event_name: The event name.
            *args: Positional arguments for the listeners.
            **kwargs: Keyword arguments for the listeners.
        """
        listeners = self._listeners.get(event_name)
        if not listeners:
            return

        callbacks: list[Callable[..., None]] = []
        alive: list[_ListenerEntry] = []

        for entry in listeners:
            resolved = entry.ref.resolve()
            if resolved is None:
                continue
            callbacks.append(resolved)
            alive.append(entry)

        if alive:
            self._listeners[event_name] = alive
        else:
            del self._listeners[event_name]

        for callback in callbacks:
            callback(*args, **kwargs)

    def defer(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Queue an event for the next dispatch via :meth:`dispatch`.

        Args:
            event_name: The event name.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        self._queue.append((event_name, args, kwargs))

    def dispatch(self) -> None:
        """Publish all queued events in a FIFO snapshot.

        Events deferred via :meth:`defer` during dispatch join the next
        queue (the snapshot is taken once at the start).
        """
        if not self._queue:
            return
        # Snapshot once — events deferred during this drain wait for next dispatch.
        pending = self._queue
        self._queue = []
        for event_name, args, kwargs in pending:
            self.publish(event_name, *args, **kwargs)

    def clear_queue(self) -> None:
        """Discard all pending events without publishing them."""
        self._queue.clear()
