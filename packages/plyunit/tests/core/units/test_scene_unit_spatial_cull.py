from __future__ import annotations

from plyunit.core.units.node_unit import NodeUnit
from plyunit.core.units.scene_unit import SceneUnit
from plyunit.core.units.unit import Unit
from plyunit.services.spatial.spatial_index import SpatialIndex


class SubmitCounter(NodeUnit):
    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.submits = 0

    def render_submit(self, renderer, context=None) -> None:
        self.submits += 1
        _ = renderer, context

    def get_render_bounds(self):
        # World-space (x, y, w, h) — same convention as Sprite / geometry utils.
        x, y = self.transform.world.position
        return (float(x), float(y), 10.0, 10.0)


class FakeRenderer:
    def context_for_node(self, **kwargs):
        return kwargs


class CamUnit(Unit):
    """Minimal camera stub for %Camera2D unique lookup."""

    def __init__(self, rect=(0.0, 0.0, 100.0, 100.0)) -> None:
        super().__init__(name="Camera2D", is_unique=True, unit_kind="service")
        self.rect = rect

    def get_view_rect(self):
        return self.rect


def test_spatial_cull_skips_submit_but_recurses():
    scene = SceneUnit(name="CullScene")
    scene.load()
    spatial = SpatialIndex(cell_size=64.0)
    existing = spatial.global_units.one_or_none("@SpatialIndex")
    if existing is not None and existing is not spatial:
        spatial.global_units.unregister(existing)

    parent = SubmitCounter("Parent")
    child = SubmitCounter("Child")
    scene.root.attach(parent)
    parent.attach(child)
    parent.transform.set_position(1000.0, 1000.0)
    child.transform.set_position(0.0, 0.0)
    scene.sync_hierarchy_and_world_transforms()
    spatial.refresh_scene(scene)

    cam = CamUnit((0.0, 0.0, 100.0, 100.0))
    scene.global_units.register(cam)
    # pyrefly: ignore [bad-argument-type]
    scene.dispatch_render(FakeRenderer())
    assert parent.submits == 0
    # Child world is near parent (off-screen); still recursed but also culled.
    assert child.submits == 0

    parent.transform.set_position(10.0, 10.0)
    scene.sync_hierarchy_and_world_transforms()
    spatial.refresh_scene(scene)
    parent.submits = 0
    child.submits = 0
    # pyrefly: ignore [bad-argument-type]
    scene.dispatch_render(FakeRenderer())
    assert parent.submits == 1
    assert child.submits == 1


def test_aabb_fallback_without_spatial():
    scene = SceneUnit(name="CullFallback")
    scene.load()
    spatial = scene.global_units.one_or_none("@SpatialIndex")
    if spatial is not None:
        scene.global_units.unregister(spatial)

    node = SubmitCounter("N")
    scene.root.attach(node)
    node.transform.set_position(0.0, 0.0)
    scene.sync_hierarchy_and_world_transforms()
    cam = CamUnit((0.0, 0.0, 50.0, 50.0))
    scene.global_units.register(cam)

    # pyrefly: ignore [bad-argument-type]
    scene.dispatch_render(FakeRenderer())
    assert node.submits == 1

    node.transform.set_position(500.0, 500.0)
    scene.sync_hierarchy_and_world_transforms()
    node.submits = 0
    # pyrefly: ignore [bad-argument-type]
    scene.dispatch_render(FakeRenderer())
    assert node.submits == 0
