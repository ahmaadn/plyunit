"""Structural typing interfaces for units: ``IUnit``, ``IServiceUnit``, ``INodeUnit``.

.. important::

    This module exists **only for static typing and for service adapters**.
    It declares *what* a unit looks like (attributes and method signatures),
    not *how* it behaves.

    The real implementations live in their own modules and remain the single
    source of truth for all behavior:

    - ``Unit``        → ``plyunit/core/units/unit.py``
    - ``ServiceUnit`` → ``plyunit/core/units/service_unit.py``
    - ``NodeUnit``    → ``plyunit/core/units/node_unit.py``

    Rules of thumb:

    - Use these protocols in **type hints** (parameters, return types,
      attributes) and in **adapters** that must accept any unit-like object
      without importing the concrete classes (avoids circular imports and
      keeps layers decoupled).
    - Do **not** put logic, state, or default behavior here. Every method body
      is ``...`` on purpose; changing behavior means editing the concrete
      class, not this file.
    - Keep this file in sync with the concrete classes: when a public member
      of ``Unit``/``ServiceUnit``/``NodeUnit`` is added, renamed, or removed,
      mirror the change here.
    - ``@runtime_checkable`` only verifies that members *exist*, not that
      their signatures or types match. Prefer static checking with pyrefly
      over ``isinstance`` against these protocols.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, Protocol, overload, runtime_checkable

if TYPE_CHECKING:
    from plyunit.backends.ports.handler import ShaderHandle
    from plyunit.backends.ports.renderer import ICanvas2D
    from plyunit.core.components.component import Component
    from plyunit.core.components.transform import TransformState
    from plyunit.core.types import RectType
    from plyunit.core.units.unit import QueryScope, UnitKind
    from plyunit.core.units.unit_registry import UnitRegistry
    from plyunit.rendering.enum import BlendMode
    from plyunit.rendering.render_context import RenderContext
    from plyunit.rendering.renderer import Renderer


@runtime_checkable
class IUnit(Protocol):
    """Typing contract for the common ancestor of every unit.

    Typing/adapter use only. The implementation is ``Unit`` in
    ``plyunit/core/units/unit.py``.

    Covers identity (name, tags, singleton kind), registry membership, and
    the scope-aware query API (``group``, ``find_by_*``, ``one``,
    ``one_or_none``). Anything satisfying this protocol can be typed as a
    unit without importing the concrete ``Unit`` class.
    """

    name: str
    tags: set[str]
    singleton_kind: UnitKind
    global_units: UnitRegistry
    units: UnitRegistry | None

    @property
    def is_unique(self) -> bool:
        """Whether this unit is marked as unique (indexed under unique_name)."""
        ...

    @property
    def is_singleton(self) -> bool:
        """Whether this unit is a singleton (``scene`` or ``service``)."""
        ...

    @property
    def can_unregister_from_global(self) -> bool:
        """Whether this unit may be unregistered from the global registry."""
        ...

    def destroy(self) -> None:
        """Destroy this unit and unregister it from its registry."""
        ...

    def _membership_registry(self) -> UnitRegistry | None:
        """Registry where this unit should be registered."""
        ...

    def _scene_registry(self) -> UnitRegistry | None:
        """Scene registry for ``scope="scene"`` queries."""
        ...

    def add_tag(self, tag: str) -> None:
        """Add a tag to this unit."""
        ...

    def has_tag(self, tag: str) -> bool:
        """Whether this unit has the given tag."""
        ...

    def set_tags(self, tags: set[str] | None = None) -> None:
        """Replace the existing tags."""
        ...

    def remove_tag(self, tag: str) -> None:
        """Remove a tag (ignored if absent)."""
        ...

    @overload
    def group[T: IUnit](
        self, unit_ref: type[T], *, scope: QueryScope = "mixed"
    ) -> list[T]: ...
    @overload
    def group(self, unit_ref: str, *, scope: QueryScope = "mixed") -> list[IUnit]: ...
    def group(self, unit_ref: Any, *, scope: QueryScope = "mixed") -> Any:
        """Query all units matching a class or name reference.

        Raises:
            ValueError: If ``scope`` is invalid.
        """
        ...

    def find_by_name(self, name: str, *, scope: QueryScope = "mixed") -> list[IUnit]:
        """Find units by name with scope resolution."""
        ...

    def find_by_tag(self, tag: str, *, scope: QueryScope = "mixed") -> list[IUnit]:
        """Find units by tag with scope resolution."""
        ...

    def find_unique_name(
        self, name: str, *, scope: QueryScope = "mixed"
    ) -> list[IUnit]:
        """Find units registered under a unique name."""
        ...

    @overload
    def one[T](self, unit_ref: type[T], *, scope: QueryScope = "mixed") -> T: ...
    @overload
    def one(self, unit_ref: str, *, scope: QueryScope = "mixed") -> Any: ...
    def one(self, unit_ref: Any, *, scope: QueryScope = "mixed") -> Any:
        """Query exactly one matching unit.

        Raises:
            NoResultFound: If no unit matches.
            MultipleResultsFound: If more than one unit matches.
            ValueError: If ``scope`` is invalid.
        """
        ...

    @overload
    def one_or_none[T](
        self, unit_ref: type[T], *, scope: QueryScope = "mixed"
    ) -> T | None: ...
    @overload
    def one_or_none(self, unit_ref: str, *, scope: QueryScope = "mixed") -> Any: ...
    def one_or_none(self, unit_ref: Any, *, scope: QueryScope = "mixed") -> Any:
        """Query one matching unit, or ``None``.

        Raises:
            ValueError: If ``scope`` is invalid.
        """
        ...


@runtime_checkable
class IServiceUnit(IUnit, Protocol):
    """Typing contract for global singleton services attached to an App.

    Typing/adapter use only. The implementation is ``ServiceUnit`` in
    ``plyunit/core/units/service_unit.py``; the constructor wrapping,
    registry hand-off, and attach/detach bookkeeping all live there.

    Intended for service adapters and for annotating code that receives "any
    service" without importing ``ServiceUnit`` directly.
    """

    def on_attach(self, app: Any) -> None:
        """Called when the service finishes creation with an active App.

        Args:
            app: The ``App`` instance hosting this service.
        """
        ...

    def on_detach(self, app: Any) -> None:
        """Called when the service is removed from the active App.

        Args:
            app: The ``App`` instance hosting this service.
        """
        ...

    def _attach_to_app(self, app: Any) -> None:
        """Attach to ``app`` via :meth:`on_attach`.

        Raises:
            RuntimeError: If already attached to another app.
        """
        ...

    def _detach_from_app(self, app: Any) -> None:
        """Detach from ``app`` via :meth:`on_detach`."""
        ...

    def _finish_service_init(self) -> None:
        """Finalize service initialization once construction completes."""
        ...


@runtime_checkable
class INodeUnit(IUnit, Protocol):
    """Typing contract for scene tree hierarchy units.

    Typing/adapter use only. The implementation is ``NodeUnit`` in
    ``plyunit/core/units/node_unit.py``; tree attach/detach policy, deferred
    structural ops, component lifecycle, and render submission are defined
    there and are **not** specified by this protocol.

    Describes the surface other layers rely on: a parent/children hierarchy,
    a transform, a component table, active/visible flags, and per-node render
    state. Implementation-only members (private flags such as
    ``_needs_component_start``, ``_scissor_rect``, ``_resolved_scissor``, and
    helpers such as ``_update_components``/``_call_on_ready``) are
    intentionally omitted.
    """

    parent: INodeUnit | None
    children: list[INodeUnit]

    components: OrderedDict[type[Component], Component]
    transform: TransformState

    active: bool
    visible: bool
    active_tree: bool
    visible_tree: bool

    z_index: int
    layer: int
    blend_mode: BlendMode | None
    shader: ShaderHandle | None
    y_sort_enabled: bool

    custom_draw_enabled: bool

    def attach(self, child: INodeUnit) -> INodeUnit:
        """Add ``child`` as a child of this node.

        Raises:
            TypeError: If ``child`` is not a node.
        """
        ...

    def detach(self, child: INodeUnit) -> None:
        """Detach ``child`` from this node (may be deferred mid-traversal)."""
        ...

    def traverse_preorder(self) -> Iterator[INodeUnit]:
        """Iterate the subtree in preorder, including ``self``."""
        ...

    def is_root(self) -> bool:
        """Whether this node has no parent."""
        ...

    def on_enter_tree(self) -> None:
        """Called when the node is attached to the scene tree."""
        ...

    def on_ready(self) -> None:
        """Called once when the node and all its parents are in the tree."""
        ...

    def on_exit_tree(self) -> None:
        """Called when the node is detached from the scene tree."""
        ...

    def update(self, dt: float) -> None:
        """Per fixed-step update hook."""
        ...

    def set_active(self, value: bool) -> None:
        """Set the local ``active`` flag."""
        ...

    def set_visible(self, value: bool) -> None:
        """Set the local ``visible`` flag."""
        ...

    def __getitem__[C: Component](self, key: type[C]) -> C:
        """Access a component by type (``node[SpriteRenderer]``)."""
        ...

    def iter_components(self) -> Iterable[Component]:
        """Iterate all components attached to this node."""
        ...

    def has_component(self, component_type: type[Component]) -> bool:
        """Whether the node has a component of the given type."""
        ...

    def add_component[C: Component](self, component: C) -> C:
        """Add a component (one per type).

        Raises:
            ValueError: If a component of the same type already exists.
        """
        ...

    def destroy_component(self, component: Component) -> None:
        """Remove and destroy a component."""
        ...

    def destroy_all_components(self) -> None:
        """Destroy every component attached to this node."""
        ...

    def world_transform_lerp(self, alpha: float | None = None) -> TransformState:
        """Interpolated world transform for smooth rendering."""
        ...

    def get_render_bounds(self) -> RectType | None:
        """World-space bounding box ``(x, y, w, h)``, or ``None`` if unknown."""
        ...

    def enable_custom_draw(self, enabled: bool = True) -> None:
        """Enable/disable explicit :meth:`draw` for this node."""
        ...

    def render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Submit this node for rendering."""
        ...

    def draw(self, canvas: ICanvas2D) -> None:
        """Draw this node on the canvas during the render phase."""
        ...

    def set_scissor(self, rect: RectType | None) -> None:
        """Enable/disable scissor clipping (world coordinates)."""
        ...

    def set_blend_mode(self, mode: BlendMode | None) -> None:
        """Set the blend mode for this node and its subtree."""
        ...

    def set_shader(self, shader: ShaderHandle | None) -> None:
        """Set the shader for this node and its subtree."""
        ...
