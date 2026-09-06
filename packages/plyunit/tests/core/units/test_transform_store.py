from __future__ import annotations

import math

from plyunit.core.components.transform import Transform2D
from plyunit.core.units.node_unit import NodeUnit
from plyunit.core.units.scene_unit import SceneUnit


def test_world_matches_combine_after_sync():
    scene = SceneUnit(name="Scene")
    scene.load()
    parent = NodeUnit(name="Parent")
    child = NodeUnit(name="Child")
    scene.root.attach(parent)
    parent.attach(child)

    parent.transform.set_position(100.0, 50.0)
    parent.transform.set_rotation(90.0)
    child.transform.set_position(10.0, 0.0)

    scene.sync_hierarchy_and_world_transforms()

    expected = Transform2D(position=(10.0, 0.0)).combine(parent.transform.world)
    assert math.isclose(
        child.transform.world.position[0], expected.position[0], abs_tol=1e-9
    )
    assert math.isclose(
        child.transform.world.position[1], expected.position[1], abs_tol=1e-9
    )
    assert math.isclose(child.transform.world.rotation, expected.rotation, abs_tol=1e-9)


def test_parent_index_less_than_child():
    scene = SceneUnit(name="Scene")
    scene.load()
    parent = NodeUnit(name="P")
    child = NodeUnit(name="C")
    scene.root.attach(parent)
    parent.attach(child)
    assert parent._transform_index >= 0
    assert child._transform_index >= 0
    assert parent._transform_index < child._transform_index


def test_update_then_sync_reflects_local_writes():
    scene = SceneUnit(name="Scene")
    scene.load()
    node = NodeUnit(name="N")

    class Mover(NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            self.transform.set_position(42.0, 7.0)

    mover = Mover(name="Mover")
    scene.root.attach(mover)
    scene._dispatch_update(0.016)
    assert math.isclose(mover.transform.world.position[0], 42.0)
    assert math.isclose(mover.transform.world.position[1], 7.0)
    assert mover.transform.dirty is False


def test_unbind_on_detach():
    scene = SceneUnit(name="Scene")
    scene.load()
    node = NodeUnit(name="N")
    scene.root.attach(node)
    assert node._transform_index >= 0
    scene.root.detach(node)
    assert node._transform_index < 0
    assert node._transform_store is None


def test_apply_physics_state_keeps_soa_aligned():
    scene = SceneUnit(name="Scene")
    scene.load()
    node = NodeUnit(name="Body")
    scene.root.attach(node)
    scene.sync_hierarchy_and_world_transforms()

    node.transform.apply_physics_state(
        (3.0, 4.0),
        15.0,
        (3.0, 4.0),
        15.0,
        (1.0, 2.0),
        5.0,
    )
    idx = node._transform_index
    store = scene.transform_store
    assert math.isclose(float(store._local_x[idx]), 3.0)
    assert math.isclose(float(store._world_x[idx]), 3.0)
    assert node.transform.dirty is False
    assert math.isclose(node.transform.world.position[0], 3.0)


def test_reparent_and_setters_scale_rotation():
    scene = SceneUnit(name="Scene")
    scene.load()
    a = NodeUnit(name="A")
    b = NodeUnit(name="B")
    c = NodeUnit(name="C")
    scene.root.attach(a)
    a.attach(b)
    scene.root.attach(c)
    b.transform.set_rotation(45.0)
    b.transform.set_scale(2.0, 3.0)
    c.attach(b)
    assert b.parent is c
    assert c._transform_index < b._transform_index
    scene.sync_hierarchy_and_world_transforms()
    assert b.transform.dirty is False


def test_store_grow_and_swap_with_last_unbind():
    scene = SceneUnit(name="Scene")
    scene.transform_store = scene.transform_store.__class__(capacity=2)
    scene.load()
    nodes = [NodeUnit(name=f"N{i}") for i in range(5)]
    for n in nodes:
        scene.root.attach(n)
    assert all(n._transform_index >= 0 for n in nodes)
    store = scene.transform_store
    count_before = store.count
    middle = nodes[1]
    middle_idx = middle._transform_index
    last_node = None
    for n in nodes:
        if n._transform_index == store.count - 1:
            last_node = n
            break
    scene.root.detach(middle)
    assert middle._transform_index < 0
    assert store.count == count_before - 1
    # Dense: no free-list holes; last live node moved into the hole when needed.
    live = [n for n in nodes if n is not middle]
    assert all(0 <= n._transform_index < store.count for n in live)
    if (
        last_node is not None
        and last_node is not middle
        and middle_idx < count_before - 1
    ):
        assert last_node._transform_index == middle_idx
    again = NodeUnit(name="Reuse")
    scene.root.attach(again)
    assert again._transform_index == store.count - 1


def test_in_scene_reparent_uses_store_reparent():
    scene = SceneUnit(name="Scene")
    scene.load()
    a = NodeUnit(name="A")
    b = NodeUnit(name="B")
    c = NodeUnit(name="C")
    scene.root.attach(a)
    a.attach(b)
    scene.root.attach(c)
    b_idx_before = b._transform_index
    c.attach(b)
    assert b.parent is c
    assert b._transform_index >= 0
    assert b._transform_store is scene.transform_store
    # In-scene reparent keeps the same store; index may move for topo.
    assert c._transform_index < b._transform_index
    scene.sync_hierarchy_and_world_transforms()
    assert b.transform.dirty is False
    _ = b_idx_before


def test_clean_sync_preserves_previous_world_stability():
    scene = SceneUnit(name="Scene")
    scene.load()
    n = NodeUnit(name="Stable")
    scene.root.attach(n)
    n.transform.set_position(1.0, 2.0)
    scene.sync_hierarchy_and_world_transforms()
    prev = n.transform.previous_world.position
    scene.sync_hierarchy_and_world_transforms()
    assert n.transform.previous_world.position == n.transform.world.position
    _ = prev


def test_apply_physics_off_tree():
    n = NodeUnit(name="Off")
    n.transform.apply_physics_state(
        (1.0, 2.0),
        10.0,
        (1.0, 2.0),
        10.0,
        (0.0, 0.0),
        0.0,
        world_scale=(1.0, 1.0),
        previous_world_scale=(1.0, 1.0),
    )
    assert n.transform.world.position == (1.0, 2.0)
    assert n.transform.dirty is False


def test_freshly_bound_node_does_not_interpolate_from_origin():
    """A newly attached node must not be lerped from (0, 0).

    Regression: spawning a box/circle via mouse click used to draw at the
    top-left, then "teleport" to the cursor position on the next frame.
    """
    scene = SceneUnit(name="Scene")
    scene.load()

    node = NodeUnit(name="Spawned")
    node.transform.set_position(640.0, 360.0)
    scene.root.attach(node)

    scene.sync_hierarchy_and_world_transforms()

    assert node.transform.world.position == (640.0, 360.0)
    assert node.transform.previous_world.position == (640.0, 360.0)
    # Any alpha must yield the spawn position, not a lerp from the origin.
    for alpha in (0.0, 0.25, 0.5, 1.0):
        lerped = node.transform.lerp_world(alpha)
        assert math.isclose(lerped.position[0], 640.0, abs_tol=1e-9)
        assert math.isclose(lerped.position[1], 360.0, abs_tol=1e-9)


def test_fresh_flag_cleared_so_later_motion_still_interpolates():
    """The fresh flag applies only once; subsequent motion still interpolates."""
    scene = SceneUnit(name="Scene")
    scene.load()

    node = NodeUnit(name="Spawned")
    node.transform.set_position(100.0, 100.0)
    scene.root.attach(node)
    scene.sync_hierarchy_and_world_transforms()

    node.transform.set_position(200.0, 100.0)
    scene.sync_hierarchy_and_world_transforms()

    assert node.transform.previous_world.position == (100.0, 100.0)
    assert node.transform.world.position == (200.0, 100.0)
    mid = node.transform.lerp_world(0.5)
    assert math.isclose(mid.position[0], 150.0, abs_tol=1e-9)


def test_spawn_position_set_after_attach_also_collapses_interpolation():
    """set_position after attach (the TransformStore path) also skips lerping from the origin."""
    scene = SceneUnit(name="Scene")
    scene.load()

    node = NodeUnit(name="Spawned")
    scene.root.attach(node)
    node.transform.set_position(320.0, 240.0)

    scene.sync_hierarchy_and_world_transforms()

    assert node.transform.world.position == (320.0, 240.0)
    assert node.transform.previous_world.position == (320.0, 240.0)


def _assert_store_links_consistent(scene: SceneUnit) -> None:
    """TransformStore invariant: sibling chains acyclic, parents consistent,
    no out-of-range links, root has no sibling."""
    from plyunit.core.units.transform_store import _NONE

    store = scene.transform_store
    count = store._count
    for i in range(count):
        for field in ("_first_child", "_next_sibling"):
            v = getattr(store, field)[i]
            assert v == _NONE or 0 <= v < count, (
                f"{field}[{i}]={v} out of dense range [0,{count})"
            )
        if store._parent[i] == _NONE:
            assert store._next_sibling[i] == _NONE, f"root {i} punya sibling"
    for p in range(count):
        child = store._first_child[p]
        seen: set[int] = set()
        while child != _NONE:
            assert child not in seen, f"cycle di sibling chain slot {p}"
            assert store._parent[child] == p, (
                f"child {child} parent-nya {store._parent[child]}, bukan {p}"
            )
            seen.add(child)
            child = store._next_sibling[child]


def test_random_tree_teardown_keeps_store_consistent():
    """Regression: random-tree teardown once caused slot corruption.

    Latent bug in ``unbind``: ``last`` was computed before the
    ``_ensure_topo`` cascade; nested unbinds relocated from slots already
    vacated (overwriting other nodes' data). Under certain failure modes
    the sibling chain formed a cycle → infinite loop during teardown of
    large scenes (the 2000-node benchmark hung on exit).
    """
    import random

    rng = random.Random(42)
    scene = SceneUnit(name="Scene")
    scene.load()
    store = scene.transform_store

    nodes = [NodeUnit(name=f"n{i}") for i in range(48)]
    for i, n in enumerate(nodes):
        parent = scene.root if i < 6 else rng.choice(nodes[:i])
        parent.attach(n)

    _assert_store_links_consistent(scene)
    assert store.count == 49  # 48 node + root

    # Destroy random children-first (mirroring _destroy_subtree) until empty.
    remaining = list(nodes)
    while remaining:
        victim = rng.choice(remaining)
        remaining.remove(victim)
        victim.destroy()
        _assert_store_links_consistent(scene)

    assert store.count == 1  # only the root remains
    _assert_store_links_consistent(scene)


def test_scene_unload_large_tree_completes():
    """Regression: unloading a large scene used to hang / hit RecursionError.

    The ``unbind → _ensure_topo → _reassign_subtree_high → unbind``
    cascade recursed without bound during full teardown (the 2000-node
    benchmark hung on exit, or RecursionError after the slot-corruption
    fix). ``SceneUnit.unload`` must complete teardown for any tree size
    without exceeding the recursion limit.
    """
    import sys

    scene = SceneUnit(name="Scene")
    scene.load()

    # Breadth-first tree: first 6 branches + random children → a structure
    # that triggers the reassign cascade when slots are reordered.
    nodes: list[NodeUnit] = []
    for i in range(400):
        n = NodeUnit(name=f"u{i}")
        parent = scene.root if i < 6 else nodes[(i * 7) % i]
        parent.attach(n)
        nodes.append(n)

    assert scene.transform_store.count == 401

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(old_limit // 2)  # stricter than the default
    try:
        scene.unload()
    finally:
        sys.setrecursionlimit(old_limit)

    assert scene.is_loaded is False
    assert scene.transform_store.count == 0  # fresh, empty store
