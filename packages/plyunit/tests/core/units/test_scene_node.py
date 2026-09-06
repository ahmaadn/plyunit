from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest

import plyunit as pu

unit_module = importlib.import_module("plyunit.core.units.unit")


class ProbeComponent(pu.Component):
    updates = True
    renders = True

    def __init__(self) -> None:
        super().__init__()
        self.start_count = 0
        self.update_count = 0
        self.render_submit_count = 0
        self.destroy_count = 0

    def on_start(self) -> None:
        self.start_count += 1

    def update(self, dt: float) -> None:
        _ = dt
        self.update_count += 1

    def render_submit(self, renderer: object, context: object | None = None) -> None:
        _ = renderer
        _ = context
        self.render_submit_count += 1

    def on_destroy(self) -> None:
        self.destroy_count += 1


class ProbeNode(pu.NodeUnit):
    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.enter_calls = 0
        self.exit_calls = 0
        self.update_calls = 0
        self.render_submit_calls = 0
        self.traversing_flags: list[bool] = []

    def on_enter_tree(self) -> None:
        self.enter_calls += 1

    def on_exit_tree(self) -> None:
        self.exit_calls += 1

    def update(self, dt: float) -> None:
        _ = dt
        self.update_calls += 1
        if self._scene_tree is not None:
            self.traversing_flags.append(self._scene_tree.is_traversing)

    def render_submit(self, renderer: object, context: object | None = None) -> None:
        _ = renderer
        _ = context
        self.render_submit_calls += 1
        if self._scene_tree is not None:
            self.traversing_flags.append(self._scene_tree.is_traversing)


class LifecycleScene(pu.SceneUnit):
    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.load_calls = 0
        self.unload_calls = 0

    def on_load(self) -> None:
        self.load_calls += 1

    def on_unload(self) -> None:
        self.unload_calls += 1


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_nodeunit_child_management_traversal_and_scene_callbacks() -> None:
    class StubScene:
        def __init__(self) -> None:
            self.is_traversing = True
            # Immediate detach path for this double (not a real SceneUnit).
            self._defer_tree_ops = False
            self.attached: list[pu.NodeUnit] = []
            self.detached: list[pu.NodeUnit] = []

        def _attach_subtree(self, unit: pu.NodeUnit) -> None:
            self.attached.append(unit)

        def _detach_subtree(self, unit: pu.NodeUnit) -> None:
            self.detached.append(unit)

    parent = pu.NodeUnit(name="Parent")
    child = pu.NodeUnit(name="Child")
    grandchild = pu.NodeUnit(name="Grand")

    with pytest.raises(TypeError, match="Child must be an instance of NodeUnit"):
        parent.attach(object())  # type: ignore[arg-type]

    parent.attach(child)
    child.attach(grandchild)
    assert [unit.name for unit in parent.traverse_preorder()] == [
        "Parent",
        "Child",
        "Grand",
    ]

    parent.attach(child)
    assert parent.children == [child]

    other = pu.NodeUnit(name="Other")
    other.attach(child)
    assert child.parent is other
    assert child not in parent.children

    parent.detach(child)
    assert child.parent is other

    stub_scene = StubScene()
    other._scene_tree = stub_scene  # type: ignore[assignment]

    in_scene = pu.NodeUnit(name="InScene")
    other.attach(in_scene)
    other.detach(in_scene)

    assert stub_scene.attached == [in_scene]
    assert stub_scene.detached == [in_scene]
    assert in_scene.parent is None
    assert parent.is_root() is True


def test_nodeunit_interpolated_transform_flags_and_noop_methods() -> None:
    node = pu.NodeUnit(name="Actor")

    node.set_active(False)
    node.set_visible(False)
    assert node.active is False
    assert node.visible is False

    node.transform.set_position(10.0, 20.0)
    node.transform.recalc_world(parent_world=None)

    half = node.world_transform_lerp(0.5)
    assert math.isclose(half.position[0], 5.0)
    assert math.isclose(half.position[1], 10.0)

    quarter = node.world_transform_lerp(0.25)
    assert math.isclose(quarter.position[0], 2.5)
    assert math.isclose(quarter.position[1], 5.0)

    full = node.world_transform_lerp(1)
    assert math.isclose(full.position[0], 10.0)
    assert math.isclose(full.position[1], 20.0)

    node.on_enter_tree()
    node.on_exit_tree()
    node.update(0.016)
    # node.render_submit({"frame": 1})


def test_default_node_render_submit_skips_custom_item() -> None:
    node = pu.NodeUnit(name="Plain")
    calls: list[dict[str, object]] = []

    class Renderer:
        def render_custom(self, **kwargs):
            calls.append(kwargs)

    node.render_submit(Renderer())

    assert calls == []


def test_draw_override_and_custom_draw_opt_in_submit_custom_item() -> None:
    class DrawNode(pu.NodeUnit):
        def draw(self, canvas: object) -> None:
            _ = canvas

    calls: list[dict[str, object]] = []

    class Renderer:
        def context_for_node(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                pass_name="world",
                layer=0,
                z=0.0,
                state_id=0,
                y_sort=False,
                y_sort_origin=0.0,
                screen_space=False,
            )

        def render_custom(self, **kwargs):
            calls.append(kwargs)

    DrawNode(name="Override").render_submit(Renderer())

    opt_in = pu.NodeUnit(name="OptIn")
    opt_in.enable_custom_draw()
    opt_in.render_submit(Renderer())

    assert len(calls) == 2
    # pyrefly: ignore [missing-attribute]
    assert calls[0]["draw_func"].__self__.name == "Override"
    # pyrefly: ignore [missing-attribute]
    assert calls[1]["draw_func"].__self__ is opt_in


def test_scene_dispatch_supports_legacy_render_submit_signature() -> None:
    class LegacyNode(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Legacy")
            self.calls = 0

        def render_submit(self, renderer: object) -> None:
            _ = renderer
            self.calls += 1

    scene = pu.SceneUnit(name="LegacyScene")
    scene._attach_subtree(scene.root)
    legacy = LegacyNode()
    scene.root.attach(legacy)

    class Renderer:
        def context_for_node(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                pass_name="world",
                layer=0,
                z=0.0,
                state_id=0,
                y_sort=False,
                y_sort_origin=0.0,
                screen_space=False,
                render_transform=None,
            )

    scene.dispatch_render(Renderer())

    assert legacy.calls == 1


def test_no_camera_render_submit_does_not_query_bounds() -> None:
    scene = pu.SceneUnit(name="Culling")
    scene._attach_subtree(scene.root)
    child = pu.NodeUnit(name="Child")
    scene.root.attach(child)
    calls = 0

    def get_render_bounds():
        nonlocal calls
        calls += 1
        return (0.0, 0.0, 1.0, 1.0)

    child.get_render_bounds = get_render_bounds  # type: ignore[method-assign]

    class Renderer:
        def context_for_node(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                pass_name="world",
                layer=0,
                z=0.0,
                state_id=0,
                y_sort=False,
                y_sort_origin=0.0,
                screen_space=False,
                render_transform=None,
            )

    scene.dispatch_render(Renderer())

    assert calls == 0


def test_scene_traversal_sync_and_lifecycle_hooks(
    isolated_registry: pu.UnitRegistry,
) -> None:
    scene = LifecycleScene(name="Gameplay")
    scene._attach_subtree(scene.root)

    class Renderer:
        def context_for_node(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(
                pass_name="world",
                layer=0,
                z=0.0,
                state_id=0,
                y_sort=False,
                y_sort_origin=0.0,
                screen_space=False,
            )

        def render_custom(self, **kwargs):
            _ = kwargs

    active = ProbeNode(name="Active")
    inactive = ProbeNode(name="Inactive")
    hidden = ProbeNode(name="Hidden")

    active_component = active.add_component(ProbeComponent())
    inactive_component = inactive.add_component(ProbeComponent())
    hidden_component = hidden.add_component(ProbeComponent())

    inactive.set_active(False)
    hidden.set_visible(False)

    scene.root.attach(active)
    scene.root.attach(inactive)
    scene.root.attach(hidden)

    assert scene.scene_units is not None
    assert scene.scene_units.one("Active") is active
    assert scene.scene_units.one("Inactive") is inactive
    assert scene.scene_units.one("Hidden") is hidden

    assert isolated_registry.one_or_none("Active") is None
    assert isolated_registry.one_or_none("Inactive") is None
    assert isolated_registry.one_or_none("Hidden") is None

    scene.sync_hierarchy_and_world_transforms()
    assert active.active_tree is True
    assert inactive.active_tree is False
    assert hidden.visible_tree is False

    scene.sync_hierarchy_and_world_transforms()
    assert active.transform.previous_world is not active.transform.world

    scene._dispatch_update(0.1)
    scene.dispatch_render(Renderer())

    assert active.update_calls == 1
    assert inactive.update_calls == 0
    assert hidden.update_calls == 1

    assert active.render_submit_calls == 1
    assert inactive.render_submit_calls == 1
    assert hidden.render_submit_calls == 0

    assert active_component.start_count == 1
    assert active_component.update_count == 1
    assert active_component.render_submit_count == 1

    assert inactive_component.start_count == 0
    assert inactive_component.update_count == 0
    assert inactive_component.render_submit_count == 1

    assert hidden_component.start_count == 1
    assert hidden_component.update_count == 1
    assert hidden_component.render_submit_count == 0

    assert active.traversing_flags
    assert set(active.traversing_flags) == {True}
    assert scene.is_traversing is False

    scene.load()
    scene.load()
    assert scene.load_calls == 1
    assert scene.is_loaded is True

    old_root = scene.root
    scene.unload()

    assert scene.unload_calls == 1
    assert scene.is_loaded is False
    assert scene.units is None
    assert scene.root is not old_root

    scene.unload()
    assert scene.unload_calls == 1


def test_scene_attach_detach_destroy_and_registry_setter(
    isolated_registry: pu.UnitRegistry,
) -> None:
    scene = pu.SceneUnit(name="Runtime")
    scene._attach_subtree(scene.root)

    parent = ProbeNode(name="Parent")
    child = ProbeNode(name="Child")
    parent.attach(child)

    scene.root.attach(parent)
    assert parent.enter_calls == 1
    assert child.enter_calls == 1
    assert scene.scene_units is not None
    assert scene.scene_units.one("Parent") is parent
    assert isolated_registry.one_or_none("Parent") is None

    scene.set_registry(scene.units)
    old_registry = scene.units
    new_registry = pu.UnitRegistry()
    scene.set_registry(new_registry)

    assert old_registry is not None
    assert old_registry.one_or_none("Parent") is None
    assert new_registry.one("Parent") is parent

    scene._detach_subtree(parent)
    assert parent._scene_tree is None
    assert child._scene_tree is None
    assert parent.exit_calls == 1
    assert child.exit_calls == 1

    scene._attach_subtree(parent)
    assert parent.enter_calls == 2
    assert child.enter_calls == 2

    parent_component = parent.add_component(ProbeComponent())
    child_component = child.add_component(ProbeComponent())
    parent.destroy()

    assert parent_component.destroy_count == 1
    assert child_component.destroy_count == 1
    assert parent.parent is None
    assert child.parent is None
    assert parent not in scene.root.children
    assert new_registry.one_or_none("Parent") is None


def test_scene_rejects_singleton_scoped_attach_and_base_hooks() -> None:
    scene = pu.SceneUnit(name="BaseScene")

    scene.on_load()
    scene.on_unload()

    singleton_scoped = pu.NodeUnit(name="SingletonLike")
    singleton_scoped.singleton_kind = "service"  # type: ignore[assignment]

    with pytest.raises(ValueError, match="NodeUnit cannot be singleton in SceneTree"):
        scene._attach_subtree(singleton_scoped)
