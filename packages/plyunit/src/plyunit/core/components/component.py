from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plyunit.core.units.node_unit import NodeUnit
    from plyunit.rendering.render_context import RenderContext
    from plyunit.rendering.renderer import Renderer


class ComponentNotFoundError(Exception):
    """Raised when a component lookup fails."""


class UnitNotSetError(Exception):
    """Raised when a component is used before being attached to a unit."""


class Component:
    """Base class for components attached to a ``NodeUnit``.

    Components follow the lifecycle ``on_attach`` → ``on_start`` → ``update``
    (per fixed step) → ``render_submit`` (per frame) → ``on_destroy``. The
    ``updates``/``renders`` flags are used to skip hooks that are not
    overridden by a subclass.
    """

    updates: bool = False
    """``True`` if the subclass overrides ``update`` (invoked every fixed step)."""

    renders: bool = False
    """``True`` if the subclass overrides ``render_submit``."""

    render_kind: str | None = None
    """Render kind identifier (e.g. ``"sprite"``) used for renderer routing."""

    def __init__(self, name: str | None = None) -> None:
        """Initializes the component's default state and auto-detects hook overrides.

        Args:
            name: Component name (``None`` → the class name).
        """
        self.enabled = True
        self.unit: NodeUnit = None  # type: ignore[assignment]
        self._name = self.__class__.__name__ if name is None else name
        self._started = False
        self._destroyed = False
        self.updates = self.updates or type(self).update is not Component.update
        self.renders = (
            self.renders or type(self).render_submit is not Component.render_submit
        )

    def on_attach(self) -> None:
        """Called when the component is attached to a unit, before on_ready."""
        pass

    def on_start(self) -> None:
        """Called once when the unit first enters the scene."""
        pass

    def update(self, dt: float) -> None:
        """Called every fixed timestep (dt in seconds)."""
        pass

    def render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Called every render frame, before the draw() of all components."""
        pass

    def on_destroy(self) -> None:
        """Called when the unit leaves the scene or is destroyed."""
        pass

    @property
    def is_started(self) -> bool:
        """Whether on_start has been called."""
        return self._started

    @property
    def is_destroyed(self) -> bool:
        """Whether the component has been destroyed."""
        return self._destroyed
