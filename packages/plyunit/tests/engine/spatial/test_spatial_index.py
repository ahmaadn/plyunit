from __future__ import annotations

import random
import importlib

import pytest

from plyunit.core.units.node_unit import NodeUnit
from plyunit.core.units.scene_unit import SceneUnit
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.services.spatial.spatial_index import SpatialIndex


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    unit_module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_module, "units", registry)
    return registry


def test_set_bounds_query_remove():
    index = SpatialIndex(cell_size=32.0)
    index.set_bounds("a", 0.0, 0.0, 10.0, 10.0)
    index.set_bounds("b", 100.0, 100.0, 110.0, 110.0)
    hits = index.query_aabb(-1.0, -1.0, 20.0, 20.0)
    assert "a" in hits
    assert "b" not in hits
    index.remove("a")
    assert index.query_aabb(-1.0, -1.0, 20.0, 20.0) == []
    index.clear()


def test_refresh_scene_after_update():
    scene = SceneUnit(name="Scene")
    scene.load()
    spatial = SpatialIndex(cell_size=32.0)
    assert scene.one_or_none("@SpatialIndex", scope="global") is spatial

    node = NodeUnit(name="Mover")
    scene.root.attach(node)
    node.transform.set_position(5.0, 5.0)
    scene._dispatch_update(0.016)

    hits = spatial.query_aabb(0.0, 0.0, 20.0, 20.0)
    assert node in hits

    node.transform.set_position(200.0, 200.0)
    scene._dispatch_update(0.016)
    hits_near = spatial.query_aabb(0.0, 0.0, 20.0, 20.0)
    hits_far = spatial.query_aabb(180.0, 180.0, 220.0, 220.0)
    assert node not in hits_near
    assert node in hits_far

    scene.root.detach(node)
    scene._dispatch_update(0.016)
    assert node not in spatial.query_aabb(180.0, 180.0, 220.0, 220.0)


def _build_scene(n: int) -> tuple[SceneUnit, SpatialIndex, list[NodeUnit]]:
    scene = SceneUnit(name="Scene")
    scene.load()
    spatial = SpatialIndex(cell_size=64.0, stats_enabled=True)
    nodes: list[NodeUnit] = []
    for i in range(n):
        node = NodeUnit(name=f"N{i}")
        scene.root.attach(node)
        node.transform.set_position(float(i * 10.0), 0.0)
        nodes.append(node)
    scene._dispatch_update(0.016)
    return scene, spatial, nodes


def test_incremental_dirty_count_less_than_full():
    scene, spatial, nodes = _build_scene(n=200)
    assert spatial.stats is not None
    # Bootstrap dispatch already did a full rebuild.
    assert spatial.stats.last_full_count >= 200

    # Move exactly one node; incremental flush should re-insert only that one.
    mover = nodes[7]
    mover.transform.set_position(5000.0, 5000.0)
    scene._dispatch_update(0.016)
    assert spatial.stats.last_dirty_count == 1

    # Full rebuild touches strictly more nodes than the single-move flush.
    spatial.refresh_scene(scene)
    assert spatial.stats.last_full_count > spatial.stats.last_dirty_count


def test_attach_detach_incremental():
    scene = SceneUnit(name="Scene")
    scene.load()
    spatial = SpatialIndex(cell_size=32.0)

    nodes = []
    for i in range(10):
        node = NodeUnit(name=f"A{i}")
        scene.root.attach(node)
        node.transform.set_position(float(i * 100.0), 0.0)
        nodes.append(node)
    scene._dispatch_update(0.016)

    # All attached nodes are queryable (bootstrap inserted them + the root).
    assert nodes[3] in spatial.query_aabb(250.0, -10.0, 360.0, 10.0)

    # Detach one; it must disappear from queries on the next dispatch.
    scene.root.detach(nodes[3])
    scene._dispatch_update(0.016)
    assert nodes[3] not in spatial.query_aabb(250.0, -10.0, 360.0, 10.0)
    # Every other node still present.
    for n in nodes:
        if n is nodes[3]:
            continue
        assert n in spatial.query_aabb(-100.0, -100.0, 1100.0, 100.0)


def test_mark_dirty_noop_for_unattached():
    spatial = SpatialIndex(cell_size=32.0)
    node = NodeUnit(name="Orphan")
    # Not attached — mark_dirty must not raise nor enqueue.
    spatial.mark_dirty(node)
    assert spatial.flush_dirty() == 0


def test_physics_writeback_updates_spatial():
    # Simulate the Physics._post_step_sync hook directly: a dynamic
    # body moves via apply_physics_state (which bypasses transform dirty), then
    # the service marks it dirty + flushes.
    _scene, spatial, nodes = _build_scene(n=5)
    body = nodes[2]

    # apply_physics_state clears _dirty, so a normal sync would skip it.
    body.transform.apply_physics_state(
        local_pos=(8000.0, 8000.0),
        local_rot=0.0,
        world_pos=(8000.0, 8000.0),
        world_rot=0.0,
        previous_world_pos=(20.0, 0.0),
        previous_world_rot=0.0,
    )

    # The physics service hook mirrors moved bodies into the dirty set.
    spatial.mark_dirty(body)
    flushed = spatial.flush_dirty()
    assert flushed == 1
    assert body in spatial.query_aabb(7990.0, 7990.0, 8010.0, 8010.0)
    assert body not in spatial.query_aabb(0.0, -10.0, 30.0, 10.0)


def test_parity_incremental_vs_full_random_walk():
    rng = random.Random(1234)
    scene, spatial, nodes = _build_scene(n=120)
    for _ in range(60):
        mover = rng.choice(nodes)
        mover.transform.set_position(
            float(rng.uniform(-500.0, 500.0)),
            float(rng.uniform(-500.0, 500.0)),
        )
        scene._dispatch_update(0.016)

    # Snapshot incremental query results across the playfield.
    probes = [
        (-200.0, -200.0, 0.0, 0.0),
        (0.0, 0.0, 200.0, 200.0),
        (-500.0, -500.0, 500.0, 500.0),
    ]
    incremental = [set(spatial.query_aabb(*p)) for p in probes]

    # Full rebuild must produce identical candidate sets.
    spatial.refresh_scene(scene)
    full = [set(spatial.query_aabb(*p)) for p in probes]

    assert incremental == full
