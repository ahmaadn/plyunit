"""Base class for editor UI panels."""

from __future__ import annotations

from abc import ABC, abstractmethod

import plyunit
from scripts.context import AppContext


class Panel(ABC):
    """Base class for docked or floating pieces of editor UI.

    Instances automatically receive the shared event bus and the app
    context at construction, so subclasses can communicate with
    services without explicit wiring.

    Attributes:
        bus: The editor event bus.
        context: The shared app state hub.
    """

    bus: plyunit.EventBus
    context: AppContext

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

        app = plyunit.units.one_or_none("@App")
        if app is None:
            raise RuntimeError(
                f"Cannot create {cls.__name__}: no '@App' unit is "
                "registered in the unit registry. Panels require the "
                "app context to reach shared editor state."
            )
        # pyrefly: ignore [bad-assignment]
        instance.context = app.context

        return instance

    @abstractmethod
    def draw(self) -> None:
        """Draw the panel.

        Docked panels draw content only (the caller owns
        ``imgui.begin``/``imgui.end``). Floating panels own their whole
        window.
        """
