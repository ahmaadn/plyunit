"""Events module — lazy ``EventBus`` facade and ``Signal`` utilities.

Exports ``EventBus``, ``Signal``, ``on``, ``wire_bindings``, and
``unwire_bindings``. See ``plyunit.events.signal`` for binding details.
"""

from .event_bus import EventBus
from .signal import Signal, on, unwire_bindings, wire_bindings

__all__ = [
    "EventBus",
    "Signal",
    "on",
    "unwire_bindings",
    "wire_bindings",
]
