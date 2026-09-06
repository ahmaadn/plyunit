"""``NodeUnit``: scene tree hierarchy unit with components and update/draw lifecycle."""

from __future__ import annotations

import inspect
import weakref
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, overload

from plyunit.core.components.component import Component
from plyunit.core.components.component_registry import components as component_registry
from plyunit.core.components.transform import TransformState
from plyunit.rendering.enum import BlendMode, Layer

from .unit import Unit

if TYPE_CHECKING:
    from plyunit.backends.interfaces.i_renderer import ICanvas2D
    from plyunit.core.types import RectType, ShaderType
    from plyunit.rendering.render_context import RenderContext
    from plyunit.rendering.renderer import Renderer

    from .scene_unit import SceneUnit
    from .transform_store import TransformStore


class NodeUnit(Unit):
    """Scene tree hierarchy unit with components and an update/draw lifecycle.

    ``NodeUnit`` is a non-singleton unit that can have a parent and
    children (a tree). Each node stores a ``TransformState`` (local/world),
    a set of components, and local active/visible flags that the parent
    propagates into ``active_tree``/``visible_tree``.
    """

    custom_draw_enabled = False
    """Global flag (overridable per-instance via :meth:`enable_custom_draw`)
    for whether :meth:`draw` must be submitted explicitly to the renderer."""

    def __init__(
        self,
        name: str | None = None,
        *,
        is_unique: bool = False,
        tags: set[str] | None = None,
    ) -> None:
        """Initialize a ``NodeUnit`` with empty tree state, components, and transform.

        Args:
            name: Node name (``None`` → class name).
            is_unique: Mark as a unique unit.
            tags: Initial set of tags.
        """
        super().__init__(
            name, is_unique=is_unique, tags=tags, register=False, unit_kind="none"
        )
        self.parent: NodeUnit | None = None
        self.children: list[NodeUnit] = []

        # Reference to the root unit for subtree attach
        self._scene_tree: SceneUnit | None = None

        # For fast lookup using a dict
        self.components: OrderedDict[type[Component], Component] = OrderedDict()

        # Flag marking that new components were added and on_start
        # must run before the next update
        self._needs_component_start = False

        # Fast-path flag: True if any component has ``updates=True``.
        # Maintained on component add/destroy (rare events) so that
        # ``_update_components`` can skip entirely for nodes that
        # only have render-only components (e.g. SpriteRenderer).
        self._any_updating_components = False

        # Weakref cache of the Window service for ``world_transform_lerp``
        # (avoids a registry query per node per frame).
        self._window_ref: weakref.ref | None = None

        # Local active flag (update is processed)
        self.active = True

        # Local visible flag (draw is called)
        self.visible = True

        # Active flag combined with the parent (update is processed)
        self.active_tree = True

        # Visible flag combined with the parent (draw is called)
        self.visible_tree = True

        # Local and world transform (world computed from the parent)
        self.transform = TransformState()
        self._transform_index: int = -1
        self._transform_store: TransformStore | None = None

        self._is_ready = False
        # Spawn gate: skip update until the end of the fixed step (mid-step attach).
        self._skip_update: bool = False
        # Deferred detach/destroy: hide now, remove the structure at flush.
        self._pending_removal: bool = False

        self.z_index = 0  # for render sorting, mutable at runtime
        self.layer = 0

        # Scissor clipping for this node's subtree. None = no scissor.
        # rect is in world coordinates: (x, y, width, height).
        # Conversion to screen coords happens during render traversal.
        self._scissor_rect: RectType | None = None

        # Resolved scissor in screen coords (computed during render traversal).
        # This is the intersection with the parent scissor plus world→screen conversion.
        self._resolved_scissor: RectType | None = None

        # Blend mode for this node. None = inherit from parent.
        self.blend_mode: BlendMode | None = None

        # Shader for this node. None = inherit from parent.
        self.shader: ShaderType | None = None

        # Y-sort: if True, z_index is ignored and the Y position is used as the
        # sort key.
        self.y_sort_enabled: bool = False
        self._render_context: RenderContext | None = None
        self._has_update_override = type(self).update is not NodeUnit.update
        self._has_render_submit_override = (
            type(self).render_submit is not NodeUnit.render_submit
        )
        self._render_submit_accepts_context = self._method_accepts_context(
            type(self).render_submit
        )
        self._has_draw_override = type(self).draw is not NodeUnit.draw

    @staticmethod
    def _method_accepts_context(method) -> bool:
        """
        Check whether the signature of ``method`` accepts ``RenderContext`` as
        the second parameter.

        Returns ``True`` if ``method`` has at least 3 positional parameters
        (``self``, ``renderer``, ``context``) or ``*args``.
        """
        try:
            parameters = inspect.signature(method).parameters.values()
        except (TypeError, ValueError):
            return True
        try:
            parameters = inspect.signature(method).parameters.values()
        except (TypeError, ValueError):
            return True

        positional_count = 0
        for parameter in parameters:
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                return True
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }:
                positional_count += 1
        return positional_count >= 3

    def destroy(self) -> None:
        """Destroy the unit and call its components' ``on_exit``/``on_destroy``.

        If called while the scene is traversing/flushing, structural teardown
        is deferred to the phase-end flush: the subtree is immediately hidden
        from queries and walks (mark + hide), but the components'
        ``on_exit_tree``/``on_destroy`` only run at flush.
        """
        scene = self._scene_tree
        if scene is not None and scene._defer_tree_ops:
            scene._enqueue_destroy(self)
            return

        for component in list(self.components.values()):
            self.destroy_component(component)

        super().destroy()
        if scene is not None:
            scene._destroy_subtree(self)

    def traverse_preorder(self) -> Iterator[NodeUnit]:
        """Iterate the subtree in preorder (root → children → grandchildren).

        Yields:
            NodeUnit: Every node in the subtree, including ``self``.
        """
        yield self
        for child in self.children:
            yield from child.traverse_preorder()

    def attach(self, child: NodeUnit):
        """Add *child* as a child of this unit. If the parent is already
        ready, the child becomes ready immediately as well.

        Args:
            child: Child unit to add.

        Returns:
            The same child (fluent).

        Raises:
            TypeError: If ``child`` is not a ``NodeUnit`` instance.
        """

        if not isinstance(child, NodeUnit):
            raise TypeError("Child must be an instance of NodeUnit")

        # Attach policy: the structure is ALWAYS immediate (goes straight into
        # children + registry + on_enter_tree/on_ready), even while the tree is
        # being traversed — the update walk uses a preorder snapshot, so it is
        # safe. Only the first tick is deferred: if the attach happens mid
        # fixed step, the subtree hits the spawn gate (skip this update step,
        # start updating on the next step). See SceneUnit._attach_subtree.

        if child.parent is self:
            return

        # In-scene reparent: keep TransformStore slots; only rewire hierarchy.
        same_scene = (
            self._scene_tree is not None
            and child._scene_tree is self._scene_tree
            and child._transform_store is self._scene_tree.transform_store
            and child._transform_index >= 0
            and self._transform_store is self._scene_tree.transform_store
            and self._transform_index >= 0
        )
        if same_scene:
            old_parent = child.parent
            if old_parent is not None:
                old_parent.children.remove(child)
            self.children.append(child)
            child.parent = self
            self._scene_tree.transform_store.reparent(child, self)
            return

        if child.parent is not None:
            child.parent.detach(child)

        self.children.append(child)
        child.parent = self

        # If the parent is already in the scene tree,
        # attach the child subtree to the scene tree right away
        if self._scene_tree:
            self._scene_tree._attach_subtree(child)

            # Call on_ready for the child and all its descendants,
            # so they can resolve other units in the same subtree.
            child._call_on_ready()

    def _call_on_ready(self) -> None:
        """Internal hook: call :meth:`on_ready` for the entire subtree.

        Called once when the unit and all its parents are attached to the
        scene tree. Units that are ready can resolve other units in the same
        subtree.
        """

        for child in self.traverse_preorder():
            if child._is_ready:
                continue

            child.on_ready()
            child._is_ready = True

    def on_ready(self) -> None:
        """
        Lifecycle hook: called once when this unit and all its parents are
        attached to the scene tree.

        Override for initialization that needs other units in the subtree
        (e.g. caching component references, querying siblings, etc.).
        """
        pass

    def detach(self, child: NodeUnit) -> None:
        """Detach a child from this unit.

        While the scene is traversing/flushing, structural removal is deferred
        to the phase-end flush (the subtree is immediately hidden from
        query/walk via mark).

        Args:
            child: Child unit to detach.
        """
        if child.parent is not self:
            return

        # Detach policy: while the scene is traversing/flushing, structural
        # removal is deferred to the phase-end flush (the subtree is
        # immediately hidden from query/walk via mark). Outside of that,
        # removal is immediate — the update/late walks use snapshots, so it
        # stays safe.
        scene = self._scene_tree
        if scene is not None and scene._defer_tree_ops:
            scene._enqueue_detach(self, child)
            return

        self.children.remove(child)
        child.parent = None

        if scene is not None:
            scene._detach_subtree(child)

    def _scene_registry(self):
        """Scene registry for ``scope="scene"`` queries.

        Returns ``scene_tree.scene_units`` if the node is inside a scene
        tree, or ``None`` if it is an orphan.
        """
        if self._scene_tree is None:
            return None
        return self._scene_tree.scene_units

    def is_root(self) -> bool:
        """Whether this node is a root (no parent)."""
        return self.parent is None

    def set_active(self, value: bool) -> None:
        """Set the local ``active`` flag (update is processed)."""
        self.active = bool(value)

    def set_visible(self, value: bool) -> None:
        """Set the local ``visible`` flag (draw is called)."""
        self.visible = bool(value)

    def world_transform_lerp(self, alpha: float | None = None):
        """Interpolated world transform for smooth rendering.

        Args:
            alpha: Interpolation parameter in ``[0.0, 1.0]``. ``None`` → use
                ``Window.alpha`` from the service, or ``1.0`` if the service
                is unavailable.

        Returns:
            Transform2D: The interpolated world transform.
        """
        render_alpha = alpha
        if render_alpha is None:
            # Weakref cache: the Window service is a global singleton — a
            # registry query per node per frame is too costly on the render hot path.
            window = self._window_ref() if self._window_ref is not None else None
            if window is None:
                window = self.one_or_none("Window", scope="global")
                if window is not None:
                    self._window_ref = weakref.ref(window)
            if window is not None:
                render_alpha = window.alpha
        if render_alpha is None:
            render_alpha = 1.0
        return self.transform.lerp_world(render_alpha)

    def get_render_bounds(self) -> RectType | None:
        """Return world-space bounding box (x, y, w, h) or None if unknown.

        Used by frustum culling to skip off-screen nodes.
        Aggregates bounds from all renderable components.
        """
        from plyunit.utils.geometry import aabb_union

        result = None
        for component in self.iter_components():
            if hasattr(component, "get_render_bounds"):
                bounds = component.get_render_bounds()
                if bounds is not None:
                    result = bounds if result is None else aabb_union(result, bounds)
        return result

    def on_enter_tree(self) -> None:
        """
        Lifecycle hook: called when this unit (and all its parents) are
        attached to the scene tree.

        Override for early setup that needs scene context (e.g. accessing
        ``SpatialIndex``, reading game config, etc.).
        """

    def on_exit_tree(self) -> None:
        """Lifecycle hook: called when the unit is detached from the scene tree.

        Either directly, or because its parent was detached. Override to clean
        up resources.
        """

    def __getitem__[C: Component](self, key: type[C]) -> C:
        """Access a component by type (``unit[SpriteRenderer]``)."""
        return self.components[key]  # type: ignore

    def iter_components(self) -> Iterable[Component]:
        """Iterate all components attached to this unit."""
        return iter(self.components.values())

    def has_component(self, component_type: type[Component]) -> bool:
        """Check whether this unit has a component of the given type.

        Args:
            component_type: Component type to check.

        Returns:
            bool: ``True`` if the unit has that component.
        """
        return component_type in self.components

    def add_component[C: Component](self, component: C) -> C:
        """Add a component to this unit.

        Args:
            component: Component to add.

        Returns:
            The same component (fluent).
        """
        if self.components.get(type(component), None):
            raise ValueError(
                f"Unit '{self.name}' sudah punya komponen '{type(component).__name__}'."
                " Tidak boleh ada dua komponen dengan tipe yang sama."
            )

        ctype = type(component)
        self.components[ctype] = component
        component.unit = self
        component.on_attach()
        component_registry.register(self, ctype)
        self._needs_component_start = True
        if component.updates:
            self._any_updating_components = True
        return component

    def destroy_component(self, component: Component) -> None:
        """Remove a component from this unit.

        Args:
            component: Component to remove.
        """
        ctype = type(component)

        if component.is_destroyed:
            if self.components.get(ctype, None) is component:
                del self.components[ctype]
                component_registry.unregister(self, ctype)
                self._any_updating_components = any(
                    c.updates for c in self.components.values()
                )
            if component.unit is not None:
                component.unit = None
            return  # Already destroyed, no need to call on_destroy again

        component.on_destroy()
        component._destroyed = True

        if self.components.get(ctype, None) is component:
            self.components.pop(ctype, None)
            component_registry.unregister(self, ctype)
            self._any_updating_components = any(
                c.updates for c in self.components.values()
            )
        component.unit = None

    def destroy_all_components(self) -> None:
        """Destroy every component attached to this unit."""
        for component in list(self.components.values()):
            self.destroy_component(component)

    def _update_components(self, dt: float) -> None:
        """Internal hook: run ``on_start`` then ``update`` for each component.

        A snapshot is taken so components may add/destroy other components
        during update.

        Args:
            dt: Fixed-step delta time in seconds.
        """
        # Snapshot: components may add/destroy other components during update.
        if self._needs_component_start:
            for component in list(self.components.values()):
                if component.is_started:
                    continue
                component.on_start()
                component._started = True
            self._needs_component_start = False

        # Fast path: nodes without updating components (e.g. only SpriteRenderer)
        # skip the list snapshot + empty loop entirely.
        if not self._any_updating_components:
            return

        for component in list(self.components.values()):
            if component.is_destroyed or not component.enabled or not component.updates:
                continue
            component.update(dt)

    def _render_components(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Internal hook: call ``render_submit`` for each component.

        Args:
            renderer: Renderer to submit to.
            context: Optional ``RenderContext`` (scissor/blend/shader pass).
        """
        for component in self.components.values():
            if component.is_destroyed or not component.enabled or not component.renders:
                continue
            component.render_submit(renderer, context)

    def enable_custom_draw(self, enabled: bool = True) -> None:
        """Enable/disable explicit :meth:`draw` for this node.

        Args:
            enabled: ``True`` to enable, ``False`` to disable.
        """
        self.custom_draw_enabled = bool(enabled)

    def _should_submit_custom_draw(self) -> bool:
        """Whether the node must perform an explicit :meth:`render_submit`.

        ``True`` if ``custom_draw_enabled`` is set, or :meth:`draw` is
        overridden on a subclass, or ``draw`` is present in the instance
        ``__dict__``.
        """
        return (
            self.custom_draw_enabled
            or self._has_draw_override
            or "draw" in self.__dict__
        )

    def _call_render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Internal hook: call :meth:`render_submit` with the correct signature.

        Detects whether the overridden :meth:`render_submit` accepts
        ``context`` or not.

        Args:
            renderer: Renderer to submit to.
            context: Optional ``RenderContext``.
        """
        if self._render_submit_accepts_context:
            self.render_submit(renderer, context)
        else:
            self.render_submit(renderer)  # type: ignore[misc]

    def update(self, dt: float) -> None:
        """Per fixed-step update hook (empty by default, override in subclasses)."""
        pass

    @overload
    def render_submit(self, renderer: Renderer) -> None: ...
    @overload
    def render_submit(self, renderer: Renderer, context: RenderContext) -> None: ...
    def render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """
        Submit this unit for rendering. Submitted units are processed in the
        render phase, where their draw() function is called.

        Scissor, blend mode, and shader are passed as per-item render state,
        not as separate draw commands. This state is already computed during
        the render traversal (in SceneUnit._traverse_render).
        """
        if not self._should_submit_custom_draw():
            return

        if context is None:
            world_tf = self.world_transform_lerp(1.0)
            y_sort_origin = world_tf.position[1] if self.y_sort_enabled else 0.0
            context = renderer.context_for_node(
                pass_name="ui" if self.layer >= Layer.UI else "world",
                layer=self.layer,
                z=self.z_index,
                scissor=self._resolved_scissor,
                blend_mode=self.blend_mode
                if self.blend_mode is not None
                else BlendMode.ALPHA,
                shader=self.shader,
                y_sort=self.y_sort_enabled,
                y_sort_origin=y_sort_origin,
                world_transform=self.transform.world,
                render_transform=world_tf,
            )

        renderer.render_custom(
            z=context.z,
            layer=context.layer,
            draw_func=self.draw,
            pass_name=context.pass_name,
            state_id=context.state_id,
            y_sort=context.y_sort,
            y_sort_origin=context.y_sort_origin,
            screen_space=context.screen_space,
        )

    def draw(self, canvas: ICanvas2D) -> None:
        """Draw this unit on the canvas during the render phase.

        Render order is already arranged by ``z`` and ``layer`` at submit
        time, so ``draw`` only needs to write to the canvas according to the
        position/orientation computed in :meth:`render_submit`.
        """
        pass

    # ------------------------------------------------------------------
    # Render State API
    # ------------------------------------------------------------------

    def set_scissor(self, rect: RectType | None) -> None:
        """Enable or disable scissor clipping for this node.

        Every child in this subtree will be clipped by *rect*.
        If a child node also enables a scissor, the child's area is
        intersected with the parent scissor (nested scissor).

        Args:
            rect: ``(x, y, width, height)`` in **world coordinates**,
                  or ``None`` to disable the scissor.
        """
        self._scissor_rect = rect

    def set_blend_mode(self, mode: BlendMode | None) -> None:
        """Set the blend mode for this node and its subtree.

        Args:
            mode: BlendMode, or None to inherit from the parent.
        """
        self.blend_mode = mode

    def set_shader(self, shader: ShaderType | None) -> None:
        """Set the shader for this node and its subtree.

        Args:
            shader: Shader program, or None to inherit from the parent.
        """
        self.shader = shader
