from __future__ import annotations

from types import SimpleNamespace

import plyunit as pu
from plyunit.core.units.node_unit import NodeUnit
from plyunit.services.spatial.spatial_index import SpatialIndex


class _FakeRenderer:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def context_for_node(self, **kwargs):
        return SimpleNamespace(**kwargs)


def test_scene_unit_frustum_and_screen_rect():
    class Cam:
        def get_view_rect(self):
            return (0.0, 0.0, 100.0, 100.0)

        def world_to_screen(self, x, y):
            return (x * 2, y * 2)

    class Scene(pu.SceneUnit):
        def __init__(self):
            super().__init__(name="scene")
            self._cam = Cam()

        def one_or_none(self, q, scope="mixed"):
            if "Camera" in str(q):
                return self._cam
            return None

    s = Scene()
    if hasattr(s, "_get_frustum_cull_rect"):
        rect = s._get_frustum_cull_rect()
        assert rect is None or len(rect) == 4
    if hasattr(s, "world_rect_to_screen"):
        out = s.world_rect_to_screen((10, 20, 30, 40))
        assert len(out) == 4
    # pyrefly: ignore [bad-assignment]
    s._cam = None
    if hasattr(s, "_get_frustum_cull_rect"):
        assert s._get_frustum_cull_rect() is None


def test_aabb_fallback_skips_submit_but_recurses():
    class Bounded(NodeUnit):
        def __init__(self, name: str, bounds):
            super().__init__(name=name)
            self._bounds = bounds
            self.submit_count = 0

        def get_render_bounds(self):
            return self._bounds

        def render_submit(self, renderer, context=None):
            self.submit_count += 1

    class Scene(pu.SceneUnit):
        def one_or_none(self, q, scope="mixed"):
            return None

    scene = Scene(name="CullScene")
    scene.load()
    # Bounds are world (x, y, w, h).
    parent = Bounded("Off", (1000.0, 1000.0, 10.0, 10.0))
    child = Bounded("On", (10.0, 10.0, 10.0, 10.0))
    scene.root.attach(parent)
    parent.attach(child)
    scene.sync_hierarchy_and_world_transforms()

    renderer = _FakeRenderer()
    view = (0.0, 0.0, 100.0, 100.0)
    scene._traverse_render(
        scene.root,
        renderer,  # type: ignore[arg-type]
        view_rect=view,
        candidates=None,
    )
    assert parent.submit_count == 0
    assert child.submit_count == 1


def test_spatial_candidates_cull():
    class Named(NodeUnit):
        def __init__(self, name: str):
            super().__init__(name=name)
            self.submit_count = 0

        def render_submit(self, renderer, context=None):
            self.submit_count += 1

    scene = pu.SceneUnit(name="SpatialCull")
    scene.load()
    a = Named("A")
    b = Named("B")
    scene.root.attach(a)
    scene.root.attach(b)
    scene.sync_hierarchy_and_world_transforms()

    candidates = {a}
    renderer = _FakeRenderer()
    scene._traverse_render(
        scene.root,
        renderer,  # type: ignore[arg-type]
        view_rect=(0.0, 0.0, 100.0, 100.0),
        candidates=candidates,
    )
    assert a.submit_count == 1
    assert b.submit_count == 0
    _ = SpatialIndex  # import used by related tests
