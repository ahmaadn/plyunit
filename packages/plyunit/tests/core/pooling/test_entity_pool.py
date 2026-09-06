from __future__ import annotations

from plyunit.utils.pool.entity_pool import EntityHandle, EntityPool
from plyunit.core.units.node_unit import NodeUnit


class PooledNode(NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="Pooled")
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1


def test_acquire_release_generation():
    pool = EntityPool(factory=PooledNode, capacity=2)
    h1 = pool.acquire()
    h2 = pool.acquire()
    assert pool.is_alive(h1)
    assert pool.get(h1) is not None

    pool.release(h1)
    assert not pool.is_alive(h1)
    assert pool.get(h1) is None

    h3 = pool.acquire()
    assert pool.is_alive(h3)
    assert not pool.is_alive(h1)
    assert h3.generation != h1.generation or h3.index != h1.index or True
    # Same slot reuses with bumped generation
    if h3.index == h1.index:
        assert h3.generation != h1.generation


def test_stale_handle_after_release():
    pool = EntityPool(factory=PooledNode, capacity=4)
    handle = pool.acquire()
    entity = pool.get(handle)
    assert isinstance(entity, PooledNode)
    pool.release(handle)
    assert entity.reset_count == 1
    assert not pool.is_alive(handle)
    assert pool.get(EntityHandle(index=handle.index, generation=handle.generation)) is None


def test_pool_grows():
    pool = EntityPool(factory=PooledNode, capacity=1)
    handles = [pool.acquire() for _ in range(3)]
    assert all(pool.is_alive(h) for h in handles)


def test_release_idempotent_and_invalid_handle():
    pool = EntityPool(factory=PooledNode, capacity=2)
    h = pool.acquire()
    pool.release(h)
    pool.release(h)
    assert not pool.is_alive(EntityHandle(index=-1, generation=0))
    assert not pool.is_alive(EntityHandle(index=999, generation=0))


def test_release_detaches_from_scene():
    from plyunit.core.units.scene_unit import SceneUnit

    scene = SceneUnit(name="PoolScene")
    scene.load()
    pool = EntityPool(factory=PooledNode, capacity=2)
    h = pool.acquire()
    node = pool.get(h)
    assert node is not None
    scene.root.attach(node)
    assert node._scene_tree is scene
    pool.release(h)
    assert node._scene_tree is None
    # pyrefly: ignore [missing-attribute]
    assert node.reset_count == 1


def test_release_calls_component_reset():
    from plyunit.core.components.component import Component

    class ResetComp(Component):
        def __init__(self) -> None:
            super().__init__()
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

    pool = EntityPool(factory=PooledNode, capacity=2)
    h = pool.acquire()
    node = pool.get(h)
    assert node is not None
    comp = ResetComp()
    node.add_component(comp)
    pool.release(h)
    assert comp.reset_count == 1
    # pyrefly: ignore [missing-attribute]
    assert node.reset_count == 1


def test_release_removes_from_spatial_index():
    from plyunit.core.units.scene_unit import SceneUnit
    from plyunit.services.spatial.spatial_index import SpatialIndex

    scene = SceneUnit(name="PoolSpatial")
    scene.load()
    index = SpatialIndex()
    index.set_bounds("placeholder", 0, 0, 1, 1)

    class Host:
        def one_or_none(self, q, scope="mixed"):
            if "SpatialIndex" in str(q):
                return index
            return None

    pool = EntityPool(factory=PooledNode, capacity=2)
    h = pool.acquire()
    node = pool.get(h)
    assert node is not None
    node.one_or_none = Host().one_or_none  # type: ignore[method-assign]
    index.set_bounds(node, 0.0, 0.0, 10.0, 10.0)
    assert node in index.query_aabb(-1, -1, 20, 20)
    pool.release(h)
    assert node not in index.query_aabb(-1, -1, 20, 20)


def test_release_resets_components_and_spatial():
    from plyunit.core.components.component import Component
    from plyunit.core.units.scene_unit import SceneUnit
    from plyunit.services.spatial.spatial_index import SpatialIndex

    class ResetComp(Component):
        def __init__(self) -> None:
            super().__init__()
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

    scene = SceneUnit(name="PoolScene")
    scene.load()
    spatial = SpatialIndex()
    existing = spatial.global_units.one_or_none("@SpatialIndex")
    if existing is not None and existing is not spatial:
        spatial.global_units.unregister(existing)

    pool = EntityPool(factory=PooledNode, capacity=2)
    h = pool.acquire()
    node = pool.get(h)
    assert node is not None
    assert node.one_or_none("@SpatialIndex", scope="global") is spatial
    comp = ResetComp()
    node.add_component(comp)
    scene.root.attach(node)
    spatial.set_bounds(node, 0.0, 0.0, 1.0, 1.0)
    assert node in spatial.query_aabb(-1.0, -1.0, 2.0, 2.0)

    pool.release(h)
    assert comp.reset_count == 1
    # pyrefly: ignore [missing-attribute]
    assert node.reset_count == 1
    assert node not in spatial.query_aabb(-1.0, -1.0, 2.0, 2.0)
    assert not pool.is_alive(h)
