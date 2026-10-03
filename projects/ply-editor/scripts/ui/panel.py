"""Base class for editor UI panels."""

from __future__ import annotations

from abc import ABC, abstractmethod

import plyunit
from scripts.app.context import Context


class Panel(ABC):
    """Base class for docked or floating pieces of editor UI.

    Panels are thin views: they read shared state from the context and
    publish intents on the event bus. Both are handed in explicitly at
    construction — no hidden lookups, so a panel can also be built in
    tests with fakes.

    Args:
        ctx: The shared app state hub.
        bus: The event bus used to publish user intents.

    Attributes:
        ctx: The shared app state hub.
        bus: The editor event bus.
    """

    bus: plyunit.EventBus
    ctx: Context

    # Query
    one = plyunit.units.one
    one_or_none = plyunit.units.one_or_none
    group = plyunit.units.group

    def __new__(cls, *args, **kwargs):
        """Create the panel and auto-attach the bus and app context.

        Looks up ``@EventBus`` and ``@App`` in the unit registry and
        stores them on the new instance, bridging UI panels to
        services without explicit wiring.

        Args:
            *args: Subclass constructor positional arguments; accepted
                for signature compatibility and ignored.
            **kwargs: Subclass constructor keyword arguments; accepted
                for signature compatibility and ignored.

        Returns:
            A new panel instance with ``bus`` and ``context`` set.

        Raises:
            RuntimeError: When ``@EventBus`` or ``@App`` is not
                registered in the unit registry.
        """
        instance = super().__new__(cls)

        bus = plyunit.units.one_or_none("@EventBus")
        if bus is None:
            raise RuntimeError(
                f"Cannot create {cls.__name__}: no '@EventBus' unit is "
                "registered in the unit registry. Panels require the "
                "editor event bus to communicate with services."
            )
        # pyrefly: ignore [bad-assignment]
        instance.bus = bus

        ctx = plyunit.units.one_or_none("@Context")
        if ctx is None:
            raise RuntimeError(
                f"Cannot create {cls.__name__}: no '@ctx' unit is "
                "registered in the unit registry. Panels require the "
                "Context to reach shared editor state."
            )
        # pyrefly: ignore [bad-assignment]
        instance.ctx = ctx

        return instance

    @abstractmethod
    def draw(self) -> None:
        """Draw the panel.

        Docked panels draw content only (the caller owns
        ``imgui.begin``/``imgui.end``). Floating panels own their whole
        window.
        """
