"""``SceneUnit``: scene root unit managing transforms, state propagation, and
traversal."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from warnings import deprecated

from plyunit.rendering.enum import BlendMode, Layer
from plyunit.utils.geometry import (
    aabb_intersection,
    aabb_intersects,
    expand_aabb,
)

from .node_unit import NodeUnit
from .transform_store import TransformStore
from .unit import Unit
from .unit_registry import UnitRegistry

if TYPE_CHECKING:
    from plyunit.core.types import RectType
    from plyunit.rendering.renderer import Renderer

logger = logging.getLogger(__name__)


def _intersect_rects(a: RectType | None, b: RectType) -> RectType:
    """Return the intersection of two rects (``a`` ∩ ``b``).

    If ``a`` is ``None``, return ``b`` as-is.
    """
    if a is None:
        return b
    return aabb_intersection(a, b)


class SceneUnit(Unit):
    """
    Special unit that acts as the root of a scene's unit hierarchy.
    Responsible for managing world transforms, active/visible state
    propagation, and update/draw traversal.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        is_unique: bool = False,
        tags: set[str] | None = None,
    ) -> None:
        """Initialize the scene with an empty root node, registry, and
        ``TransformStore``.

        Args:
            name: Scene name (``None`` → class name).
            is_unique: Mark the scene as a unique unit.
            tags: Initial set of tags.
        """
        super().__init__(name, is_unique=is_unique, tags=tags, unit_kind="scene")
        self.scene_units: UnitRegistry | None = UnitRegistry()
        self.units = self.scene_units
        self.root = NodeUnit(name="Root", tags={"root"})
        self.transform_store = TransformStore()

        self._is_traversing = False
        self.is_loaded = False

        # Fixed step: spawn gate + deferred detach/destroy.
        self._stepping = False
        self._loading = False
        self._spawn_gated: list[NodeUnit] = []
        self._pending: list[tuple[str, NodeUnit, NodeUnit | None]] = []
        self._flushing = False

        self._cull_margin = 64.0
        self.profile_enabled = False
        self.frame_profile: dict[str, float] = {}
        self.last_frame_profile: dict[str, float] = {}

    def _dispatch_update(self, dt: float) -> None:
        """Dispatch update scene then sync transforms (PLAN frame order)."""
        owns_step = not self._stepping
        if owns_step:
            self._begin_step()
        update_start = time.perf_counter() if self.profile_enabled else 0.0
        self._is_traversing = True
        try:
            dirty_count = 0
            if self.profile_enabled:
                # Iterative preorder (mirrors traverse_preorder without a
                # recursive generator — fixed-step hot path).
                stack = [self.root]
                while stack:
                    unit = stack.pop()
                    if unit.transform.dirty:
                        dirty_count += 1
                    stack.extend(reversed(unit.children))

            self.update(dt)
            # Snapshot semantics: child refs are snapshotted when the parent
            # is popped; mid-step attaches hit the spawn gate and still skip.
            stack = [self.root]
            while stack:
                unit = stack.pop()
                if unit._pending_removal or unit._skip_update:
                    continue
                if unit.active_tree:
                    if unit._has_update_override:
                        unit.update(dt)
                    unit._update_components(dt)
                stack.extend(reversed(unit.children))
            if self.profile_enabled:
                self.frame_profile["update_nodes_ms"] = (
                    time.perf_counter() - update_start
                ) * 1000.0

            sync_start = time.perf_counter() if self.profile_enabled else 0.0
            recomputed = self.sync_hierarchy_and_world_transforms()
            spatial = self.one_or_none("@SpatialIndex", scope="global")
            if spatial is not None:
                # Incremental path (PLAN §6, M5): bootstrap once to insert the
                # scene root + pre-existing nodes, then upsert only moved/attached
                # nodes. Full refresh_scene stays available for debug / teleport.
                if not spatial._bootstrapped:
                    spatial.refresh_scene(self)
                else:
                    spatial.mark_dirty_many(recomputed)
                    spatial.flush_dirty()
            if self.profile_enabled:
                self.frame_profile["update_sync_ms"] = (
                    time.perf_counter() - sync_start
                ) * 1000.0
                self.frame_profile["transform_dirty_count"] = float(dirty_count)
            self._flush_pending()
            self._clear_spawn_gates()
        finally:
            self._is_traversing = False
            if owns_step:
                self._end_step()

    def dispatch_render(self, renderer: Renderer) -> None:
        """Dispatch render submit for the scene and its visible subtree.

        Uses a depth-first traversal with state inheritance: each node
        receives the resolved scissor/blend/shader from its parent, merges
        it with its own, then passes it down to its children.
        """
        render_start = time.perf_counter() if self.profile_enabled else 0.0
        self._is_traversing = True

        # TODO: deprecated in the future — scene-level render submit will be
        # replaced by the Root Node; the Root Node will be customizable via
        # the scene's __init__. Root Node rules: it must be named "root" and
        # carry the "root" tag.
        self.render_submit(renderer)
        try:
            view_rect = self._get_frustum_cull_rect()
            candidates: set[object] | None = None
            if view_rect is not None:
                spatial = self.one_or_none("@SpatialIndex", scope="global")
                if spatial is not None:
                    vx, vy, vw, vh = view_rect
                    candidates = set(spatial.query_aabb(vx, vy, vx + vw, vy + vh))
            self._traverse_render(
                self.root,
                renderer,
                parent_scissor=None,
                parent_blend=BlendMode.ALPHA,
                parent_shader=None,
                view_rect=view_rect,
                candidates=candidates,
            )
        finally:
            self._is_traversing = False
            if self.profile_enabled:
                self.frame_profile["render_submit_ms"] = (
                    time.perf_counter() - render_start
                ) * 1000.0
                self.last_frame_profile = dict(self.frame_profile)

    def _count_dirty_transforms(self) -> int:
        """Count nodes with ``transform.dirty`` for profiling."""
        return sum(1 for unit in self.root.traverse_preorder() if unit.transform.dirty)

    def _get_frustum_cull_rect(self) -> tuple[float, float, float, float] | None:
        """Get expanded camera view rect (x, y, w, h) for frustum culling.

        Camera2D.get_view_rect returns (left, top, right, bottom); converted
        to xywh before margin expand so aabb_intersects matches component bounds.
        """
        try:
            camera = self.one_or_none("@Camera2D", scope="global")
            if camera is None:
                return None
            left, top, right, bottom = camera.get_view_rect()
            xywh = (
                float(left),
                float(top),
                float(right) - float(left),
                float(bottom) - float(top),
            )
            return expand_aabb(xywh, self._cull_margin)
        except Exception:
            return None

    def _traverse_render(
        self,
        node: NodeUnit,
        renderer: Renderer,
        *,
        parent_scissor: tuple[float, float, float, float] | None = None,
        parent_blend: BlendMode = BlendMode.ALPHA,
        parent_shader=None,
        view_rect: tuple[float, float, float, float] | None = None,
        candidates: set[object] | None = None,
    ) -> None:
        """Recursive depth-first render submit with state inheritance.

        Algorithm:
        1. Resolve scissor: if the node has a _scissor_rect (world coords),
           convert it to screen coords and intersect it with parent_scissor.
        2. Set _resolved_scissor on the node (used by render_submit).
        3. Submit the node (render_submit + component renders).
        4. Recurse into children with the resolved scissor.

        Culled nodes skip submit but still recurse into children (state
        inheritance). Nodes with ``layer >= Layer.UI`` render in screen
        space without the camera, so they are never culled by the camera
        frustum.

        Args:
            node: Node currently being traversed.
            renderer: Renderer to submit to.
            parent_scissor: Resolved scissor from the parent (screen coords).
            view_rect: Camera frustum rect (world coords) for culling.
            candidates: SpatialIndex hits for view_rect when service is present.
        """
        if not node.visible_tree or node._pending_removal:
            return

        skip_submit = False
        # Layers >= UI render in screen space (``ui``/``debug`` passes
        # without a camera) — world camera frustum culling does not apply to them.
        if view_rect is not None and node.layer < Layer.UI:
            if candidates is not None:
                # SpatialIndex path: skip submit when not in candidates.
                # Nodes without bounds use point AABB at world position in refresh.
                if node is not self.root and node not in candidates:
                    skip_submit = True
            else:
                bounds = node.get_render_bounds()
                if bounds is None:
                    try:
                        pos = node.transform.world.position
                        x = float(pos[0])
                        y = float(pos[1])
                        bounds = (x, y, 0.0, 0.0)
                    except Exception:
                        bounds = None
                if bounds is not None and not aabb_intersects(view_rect, bounds):
                    # AABB fallback: skip submit but still recurse children.
                    skip_submit = True

        # Resolve the scissor for this node
        resolved_scissor = parent_scissor

        if node._scissor_rect is not None:
            # Convert world coords to screen coords
            node_scissor_screen = self._world_rect_to_screen(node._scissor_rect)

            if resolved_scissor is not None:
                # Intersect with the parent scissor
                resolved_scissor = _intersect_rects(
                    resolved_scissor, node_scissor_screen
                )
            else:
                resolved_scissor = node_scissor_screen

        # Store the resolved scissor on the node (node.render_submit will read it)
        node._resolved_scissor = resolved_scissor

        blend_mode = node.blend_mode if node.blend_mode is not None else parent_blend
        shader = node.shader if node.shader is not None else parent_shader

        if not skip_submit:
            needs_node_submit = (
                node._has_render_submit_override or node._should_submit_custom_draw()
            )
            # Alpha is always 1.0 on this path — identical to
            # ``transform.world`` without allocating a Transform2D per node
            # per frame.
            render_transform = node.transform.world
            if not needs_node_submit:
                handled_fast = self._submit_fast_render_components(
                    node,
                    renderer,
                    render_transform,
                    resolved_scissor=resolved_scissor,
                    blend_mode=blend_mode,
                    shader=shader,
                )
                if handled_fast:
                    context = None
                else:
                    context = self._context_for_node(
                        node,
                        renderer,
                        resolved_scissor=resolved_scissor,
                        blend_mode=blend_mode,
                        shader=shader,
                        render_transform=render_transform,
                    )
                    node._render_components(renderer, context)
            else:
                context = self._context_for_node(
                    node,
                    renderer,
                    resolved_scissor=resolved_scissor,
                    blend_mode=blend_mode,
                    shader=shader,
                    render_transform=render_transform,
                )
                node._call_render_submit(renderer, context)
                node._render_components(renderer, context)

            node._render_context = context
        else:
            node._render_context = None

        # Recurse into the child subtree (even when this node was culled)
        for child in node.children:
            self._traverse_render(
                child,
                renderer,
                parent_scissor=resolved_scissor,
                parent_blend=blend_mode,
                parent_shader=shader,
                view_rect=view_rect,
                candidates=candidates,
            )

    def _context_for_node(
        self,
        node: NodeUnit,
        renderer: Renderer,
        *,
        resolved_scissor: tuple[float, float, float, float] | None,
        blend_mode: BlendMode,
        shader,
        render_transform,
    ):
        """Build the ``RenderContext`` for a node's render submit.

        Args:
            node: Node to build the context for.
            renderer: Renderer that interns render states.
            resolved_scissor: Final scissor rect in screen coords.
            blend_mode: Resolved blend mode.
            shader: Resolved shader.
            render_transform: Transform used for rendering (interpolated).

        Returns:
            The render context used for the node's submit.
        """
        y_sort_origin = render_transform.position[1] if node.y_sort_enabled else 0.0
        return renderer.context_for_node(
            pass_name="ui" if node.layer >= Layer.UI else "world",
            layer=node.layer,
            z=node.z_index,
            scissor=resolved_scissor,
            blend_mode=blend_mode,
            shader=shader,
            y_sort=node.y_sort_enabled,
            y_sort_origin=y_sort_origin,
            world_transform=node.transform.world,
            render_transform=render_transform,
        )

    def _submit_fast_render_components(
        self,
        node: NodeUnit,
        renderer: Renderer,
        render_transform,
        *,
        resolved_scissor: tuple[float, float, float, float] | None,
        blend_mode: BlendMode,
        shader,
    ) -> bool:
        """Submit a node's render components without allocating a RenderContext.

        Allocation-free validation: the first renderable component without
        ``render_submit_fast`` (non-SpriteRenderer) makes the caller fall
        back to the full context path. Semantics are identical to the old
        ``isinstance(SpriteRenderer)`` validation, without per-node list
        building.
        """
        components = node.components
        if not components:
            return True

        for component in components.values():
            if component.is_destroyed or not component.enabled or not component.renders:
                continue
            if getattr(component, "render_submit_fast", None) is None:
                return False

        state_id = 0
        if (
            resolved_scissor is not None
            or blend_mode != BlendMode.ALPHA
            or shader is not None
        ):
            state_id = renderer.intern_state(
                scissor=resolved_scissor,
                blend_mode=blend_mode,
                shader=shader,
            )
        y_sort_origin = render_transform.position[1] if node.y_sort_enabled else 0.0
        pass_name = "ui" if node.layer >= Layer.UI else "world"
        screen_space = node.layer >= Layer.UI

        for component in components.values():
            if component.is_destroyed or not component.enabled or not component.renders:
                continue
            component.render_submit_fast(
                renderer,
                render_transform,
                pass_name=pass_name,
                state_id=state_id,
                y_sort=node.y_sort_enabled,
                y_sort_origin=y_sort_origin,
                screen_space=screen_space,
            )
        return True

    def _world_rect_to_screen(
        self, rect: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Convert a rectangle from world coordinates to screen coordinates.

        Uses the App's active camera when available. If there is no
        camera, world coords == screen coords.

        Args:
            rect: (x, y, width, height) in world coordinates.

        Returns:
            Tuple ``(x, y, width, height)`` in screen coordinates.
        """
        camera = self.one_or_none("@Camera2D", scope="global")
        if camera is None:
            return rect

        x, y, w, h = rect

        # Convert the top-left and bottom-right corners
        sx1, sy1 = camera.world_to_screen(x, y)
        sx2, sy2 = camera.world_to_screen(x + w, y + h)

        # Ensure width/height are positive
        sw = abs(sx2 - sx1)
        sh = abs(sy2 - sy1)
        sx = min(sx1, sx2)
        sy = min(sy1, sy2)

        return (sx, sy, sw, sh)

    def sync_hierarchy_and_world_transforms(self) -> list:
        """Sync active/visible state and recompute world transforms.

        Propagates ``active``/``visible`` into ``active_tree``/``visible_tree``
        and runs ``TransformStore.sync()`` to recompute the world transform
        for every node.

        Returns:
            list: The ``NodeUnit``s whose world transforms were recomputed
            in this call (for incremental ``SpatialIndex`` upsert).
        """
        self.root.active_tree = self.root.active
        self.root.visible_tree = self.root.visible

        stack: list[NodeUnit] = [self.root]
        while stack:
            unit = stack.pop()
            for child in reversed(unit.children):
                child.active_tree = unit.active_tree and child.active
                child.visible_tree = unit.visible_tree and child.visible
                stack.append(child)

        indices = self.transform_store.sync()
        if not indices:
            return []
        nodes = self.transform_store
        recomputed: list[NodeUnit] = []
        for i in indices:
            node = nodes._nodes[i]
            if node is not None:
                recomputed.append(node)
        return recomputed

    def _attach_subtree(self, unit: NodeUnit) -> None:
        """Register full subtree, then on_enter_tree preorder (sibling queries OK).

        Attach mid fixed-step sets spawn gate (skip update until next step).
        """
        subtree = list(unit.traverse_preorder())
        for node in subtree:
            if node.is_singleton:
                raise ValueError("NodeUnit cannot be singleton in SceneTree")

        gate = self.is_loaded and self._stepping and not self._loading

        for node in subtree:
            node._scene_tree = self
            node.units = self.scene_units
            if self.scene_units is not None:
                self.scene_units.register(node)
            self.transform_store.bind(node)
            if gate:
                node._skip_update = True
                self._spawn_gated.append(node)
            else:
                node._skip_update = False

        spatial = self.one_or_none("@SpatialIndex", scope="global")
        if spatial is not None:
            for node in subtree:
                spatial.attach(node)

        for node in subtree:
            node.on_enter_tree()

    def _detach_subtree(self, unit: NodeUnit) -> None:
        """Detach unit + descendants: exit_tree children-first, no destroy."""
        spatial = self.one_or_none("@SpatialIndex", scope="global")
        if spatial is not None:
            for node in unit.traverse_preorder():
                spatial.detach(node)
        for child in list(unit.children):
            self._detach_subtree(child)
        if self.scene_units is not None:
            self.scene_units.unregister(unit)

        self.transform_store.unbind(unit)
        unit.on_exit_tree()
        unit._scene_tree = None
        unit._skip_update = False
        unit._pending_removal = False
        unit.units = unit.global_units

    def _destroy_subtree(self, unit: NodeUnit) -> None:
        """Destroy unit + descendants (components, exit_tree, unbind)."""
        spatial = self.one_or_none("@SpatialIndex", scope="global")
        if spatial is not None:
            for node in unit.traverse_preorder():
                spatial.detach(node)
        for child in list(unit.children):
            self._destroy_subtree(child)

        unit.destroy_all_components()

        if unit.parent is not None:
            unit.parent.children.remove(unit)
            unit.parent = None

        if self.scene_units is not None:
            self.scene_units.unregister(unit=unit)

        self.transform_store.unbind(unit)
        unit.on_exit_tree()
        unit._scene_tree = None
        unit._skip_update = False
        unit._pending_removal = False
        unit.units = unit.global_units

    def _scene_registry(self) -> UnitRegistry | None:
        """Returns this scene's own registry for scene-scoped queries."""
        return self.scene_units

    def destroy(self) -> None:
        """Unload the tree before removing the scene from the global registry."""
        if self.is_loaded:
            self.unload()
        super().destroy()

    @property
    def is_traversing(self) -> bool:
        """Whether the scene tree is currently traversing update/draw."""
        return self._is_traversing

    @property
    def _defer_tree_ops(self) -> bool:
        """Whether tree operations (attach/detach/destroy) must be deferred."""
        return self._is_traversing or self._flushing

    def _begin_step(self) -> None:
        """Internal hook: open the spawn-gate window for this fixed step."""
        if self._stepping:
            return
        self._stepping = True

    def _end_step(self) -> None:
        """Internal hook: close the spawn-gate window."""
        if self._spawn_gated:
            self._clear_spawn_gates()
        self._stepping = False

    def _clear_spawn_gates(self) -> None:
        """Internal hook: open the spawn gate for every gated node."""
        for node in self._spawn_gated:
            node._skip_update = False
        self._spawn_gated.clear()

    def _enqueue_detach(self, parent: NodeUnit | None, child: NodeUnit) -> None:
        """Internal hook: enqueue detaching ``child`` from ``parent`` for a
        later flush."""
        if child._pending_removal:
            return
        self._mark_hidden(child)
        self._pending.append(("detach", child, parent))

    def _enqueue_destroy(self, unit: NodeUnit) -> None:
        """Internal hook: enqueue destroying ``unit`` at a later flush.

        Destroy wins over a pending detach for the same unit.
        """
        # Destroy wins over a pending detach for the same unit.
        for i, (kind, u, parent) in enumerate(self._pending):
            if u is unit:
                if kind == "destroy":
                    return
                self._pending[i] = ("destroy", unit, parent)
                return
        self._mark_hidden(unit)
        self._pending.append(("destroy", unit, unit.parent))

    def _mark_hidden(self, unit: NodeUnit) -> None:
        """Internal hook: mark ``unit``'s subtree as hidden and unregister it."""
        for node in unit.traverse_preorder():
            node._pending_removal = True
            if self.scene_units is not None:
                self.scene_units.unregister(node)

    def _flush_pending(self) -> None:
        """Internal hook: flush all pending detach/destroy ops at the end of the
        phase."""
        if not self._pending:
            return
        self._flushing = True
        try:
            # Process until empty; re-entrant enqueue from exit_tree is OK.
            for _ in range(16):
                if not self._pending:
                    break
                kind, unit, parent = self._pending.pop(0)
                if kind == "destroy":
                    unit._pending_removal = False
                    if unit._scene_tree is not None:
                        self._destroy_subtree(unit)
                    else:
                        unit.destroy_all_components()
                else:
                    if unit.parent is not parent:
                        unit._pending_removal = False
                        continue
                    if parent is not None:
                        parent.children.remove(unit)
                    unit.parent = None
                    self._detach_subtree(unit)
            else:
                if self._pending:
                    logger.error(
                        "Pending tree ops flush stalled (%d left); clearing",
                        len(self._pending),
                    )
                    self._pending.clear()
        finally:
            self._flushing = False

    def set_registry(self, registry: UnitRegistry | None) -> None:
        """Set the registry for this scene tree and every unit in it.

        Args:
            registry: The new registry, or ``None`` to remove it.
        """
        if registry is self.scene_units:
            return

        if self.scene_units is not None:
            for unit in self.root.traverse_preorder():
                self.scene_units.unregister(unit)

        self.scene_units = registry
        self.units = registry

        for unit in self.root.traverse_preorder():
            unit.units = registry if registry is not None else unit.global_units

        if self.scene_units is None:
            return

        for unit in self.root.traverse_preorder():
            self.scene_units.register(unit)

    def on_load(self) -> None:
        """
        Called when the scene is loaded. Override for unit-level or
        scene-dependent state initialization.
        """
        pass

    def on_unload(self) -> None:
        """
        Called when the scene is unloaded. Override for unit-level or
        scene-dependent state cleanup.
        """
        pass

    def load(self) -> None:
        """
        Load the scene and every unit in it. Called once when the scene is
        first activated.
        """
        if self.is_loaded:
            return
        self.is_loaded = True
        # Attaches during load skip the spawn gate — a fresh scene may update
        # in the next fixed step as usual.
        self._loading = True
        try:
            self.on_load()
            # Attach the root to the scene tree to initialize registry and lifecycle
            self._attach_subtree(self.root)

            # Call on_ready after all units are loaded and on_enter_tree has run
            self.root._call_on_ready()
        finally:
            self._loading = False

    def unload(self) -> None:
        """
        Unload the scene and every unit in it. Called once when the scene is
        deactivated.
        """
        if not self.is_loaded:
            return

        self.on_unload()

        # Destroy the root subtree so components and units leave the tree
        # correctly (on_exit_tree is called). Topo maintenance is disabled —
        # the store is replaced right after, so a reassign cascade would
        # just waste time (and cascade without bound on large scenes).
        self.transform_store.begin_suppress_topo()
        try:
            self._destroy_subtree(self.root)
        finally:
            self.transform_store.end_suppress_topo()

        self._pending.clear()
        self._spawn_gated.clear()
        self._stepping = False

        self.set_registry(None)

        # Reset tree to ensure scene-level runtime objects are cleaned up.
        self.transform_store = TransformStore()
        self.root = NodeUnit(name="Root", tags={"root"})
        self.is_loaded = False

    def update(self, dt: float) -> None:
        """Override for scene-level update logic."""
        pass

    @deprecated(
        "Versi mendatang Scene tidak bisa melakaukan render sumbit,"
        "gunakan node root sebagai gantinya"
    )
    def render_submit(self, renderer: Renderer) -> None:
        """Override for scene-level render submit logic."""
        pass
