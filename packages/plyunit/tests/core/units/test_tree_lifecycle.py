"""M1 tree lifecycle: enter-tree order, spawn gate, detach/destroy deferral."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit as pu


class CountingNode(pu.NodeUnit):
    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.enter_calls = 0
        self.exit_calls = 0
        self.ready_calls = 0
        self.update_calls = 0
        self.render_submit_calls = 0
        self.enter_sibling: pu.NodeUnit | None = None
        self.ready_sibling: pu.NodeUnit | None = None

    def on_enter_tree(self) -> None:
        self.enter_calls += 1
        sibling_name = self.name.replace("A", "B") if "A" in self.name else None
        if sibling_name:
            self.enter_sibling = self.one_or_none(sibling_name, scope="scene")

    def on_ready(self) -> None:
        self.ready_calls += 1
        sibling_name = self.name.replace("A", "B") if "A" in self.name else None
        if sibling_name:
            self.ready_sibling = self.one_or_none(sibling_name, scope="scene")

    def on_exit_tree(self) -> None:
        self.exit_calls += 1

    def update(self, dt: float) -> None:
        _ = dt
        self.update_calls += 1

    def render_submit(self, renderer: object, context: object | None = None) -> None:
        _ = renderer
        _ = context
        self.render_submit_calls += 1


class ProbeComponent(pu.Component):
    updates = True
    renders = True

    def __init__(self) -> None:
        super().__init__()
        self.start_count = 0
        self.update_count = 0
        self.destroy_count = 0

    def on_start(self) -> None:
        self.start_count += 1

    def update(self, dt: float) -> None:
        _ = dt
        self.update_count += 1

    def on_destroy(self) -> None:
        self.destroy_count += 1


def _step(scene: pu.SceneUnit, dt: float = 0.016) -> None:
    scene._dispatch_update(dt)


def _renderer() -> object:
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

        def render_custom(self, **kwargs):
            _ = kwargs

    return Renderer()


@pytest.fixture()
def loaded_scene() -> pu.SceneUnit:
    scene = pu.SceneUnit(name="Lifecycle")
    scene.load()
    return scene


def test_sibling_resolve_in_on_enter_tree_and_on_ready(
    loaded_scene: pu.SceneUnit,
) -> None:
    """Opsi A: full subtree registered before any on_enter_tree."""
    parent = pu.NodeUnit(name="Parent")
    a = CountingNode(name="SiblingA")
    b = CountingNode(name="SiblingB")
    parent.attach(a)
    parent.attach(b)

    loaded_scene.root.attach(parent)

    assert a.enter_calls == 1
    assert b.enter_calls == 1
    assert a.enter_sibling is b
    assert a.ready_sibling is b
    assert loaded_scene.scene_units is not None
    assert loaded_scene.scene_units.one("SiblingA") is a
    assert loaded_scene.scene_units.one("SiblingB") is b


def test_attach_during_update_immediate_structure_no_update_same_step(
    loaded_scene: pu.SceneUnit,
) -> None:
    scene = loaded_scene
    spawned: list[CountingNode] = []

    class Spawner(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            child = CountingNode(name="Spawned")
            comp = child.add_component(ProbeComponent())
            self.attach(child)
            spawned.append(child)
            assert child in self.children
            assert scene.scene_units is not None
            assert scene.scene_units.one("Spawned") is child
            assert child.enter_calls == 1
            assert child.ready_calls == 1
            _ = comp

    spawner = Spawner(name="Spawner")
    scene.root.attach(spawner)

    _step(scene)

    child = spawned[0]
    assert child in spawner.children
    assert child.update_calls == 0
    assert child[ProbeComponent].start_count == 0
    assert child[ProbeComponent].update_count == 0


def test_attached_child_updates_next_step(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    spawned: list[CountingNode] = []

    class Spawner(pu.NodeUnit):
        def __init__(self) -> None:
            super().__init__(name="Spawner")
            self._did = False

        def update(self, dt: float) -> None:
            _ = dt
            if self._did:
                return
            self._did = True
            child = CountingNode(name="NextTick")
            child.add_component(ProbeComponent())
            self.attach(child)
            spawned.append(child)

    scene.root.attach(Spawner())
    _step(scene)
    child = spawned[0]
    assert child.update_calls == 0

    _step(scene)
    assert child.update_calls == 1
    assert child[ProbeComponent].start_count == 1
    assert child[ProbeComponent].update_count == 1


def test_attach_from_scene_update_gated() -> None:
    """Strict gate: attach from scene.update also skips same fixed step."""
    spawned: list[CountingNode] = []

    class SpawnScene(pu.SceneUnit):
        def __init__(self) -> None:
            super().__init__(name="SpawnScene")
            self._did = False

        def update(self, dt: float) -> None:
            _ = dt
            if self._did:
                return
            self._did = True
            child = CountingNode(name="FromScene")
            self.root.attach(child)
            spawned.append(child)

    scene = SpawnScene()
    scene.load()
    _step(scene)
    child = spawned[0]
    assert child in scene.root.children
    assert child.update_calls == 0

    _step(scene)
    assert child.update_calls == 1


def test_attach_mid_traversal_siblings_complete(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    order: list[str] = []

    class Ordered(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            order.append(self.name)
            if self.name == "First":
                self.parent.attach(CountingNode(name="MidSpawn"))  # type: ignore[union-attr]

    first = Ordered(name="First")
    second = Ordered(name="Second")
    scene.root.attach(first)
    scene.root.attach(second)

    _step(scene)

    assert order == ["First", "Second"]
    mid = scene.scene_units.one("MidSpawn")  # type: ignore[union-attr]
    assert mid in scene.root.children
    assert mid.update_calls == 0  # type: ignore[attr-defined]


def test_detach_during_update_hides_immediately_then_flushes(
    loaded_scene: pu.SceneUnit,
) -> None:
    scene = loaded_scene
    observed: dict[str, object] = {}

    class Victim(CountingNode):
        pass

    class Detacher(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            parent = self.parent
            assert parent is not None
            parent.detach(victim)
            # Structure still present until flush; registry already hidden.
            observed["in_children"] = victim in parent.children
            observed["parent"] = victim.parent
            assert scene.scene_units is not None
            observed["registry"] = scene.scene_units.one_or_none("Victim")
            observed["pending"] = victim._pending_removal

    class Observer(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            observed["observer_ran"] = True
            observed["victim_update_calls"] = victim.update_calls

    detacher = Detacher(name="Detacher")
    victim = Victim(name="Victim")
    observer = Observer(name="Observer")
    scene.root.attach(detacher)
    scene.root.attach(victim)
    scene.root.attach(observer)

    scene._dispatch_update(0.016)

    assert observed["in_children"] is True
    assert observed["parent"] is scene.root
    assert observed["registry"] is None
    assert observed["pending"] is True
    assert observed["observer_ran"] is True
    assert observed["victim_update_calls"] == 0
    # Flush at end of update phase removes structure.
    assert victim.parent is None
    assert victim not in scene.root.children
    assert victim.exit_calls == 1
    assert victim._pending_removal is False


def test_scene_update_mutation_is_deferred_until_dispatch_flush() -> None:
    victim = CountingNode(name="SceneVictim")
    observed: dict[str, object] = {}

    class MutatingScene(pu.SceneUnit):
        def update(self, dt: float) -> None:
            _ = dt
            observed["traversing"] = self.is_traversing
            self.root.detach(victim)
            observed["in_children"] = victim in self.root.children
            observed["pending"] = victim._pending_removal

    scene = MutatingScene(name="MutatingScene")
    scene.load()
    scene.root.attach(victim)

    scene._dispatch_update(0.016)

    assert observed == {
        "traversing": True,
        "in_children": True,
        "pending": True,
    }
    assert victim.parent is None
    assert victim not in scene.root.children
    assert victim.exit_calls == 1


def test_detach_does_not_skip_unrelated_siblings(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    updated: list[str] = []

    class Tracker(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            updated.append(self.name)
            if self.name == "A":
                self.parent.detach(b)  # type: ignore[union-attr]

    a = Tracker(name="A")
    b = Tracker(name="B")
    c = Tracker(name="C")
    scene.root.attach(a)
    scene.root.attach(b)
    scene.root.attach(c)

    _step(scene)

    assert updated == ["A", "C"]
    assert b.parent is None
    assert b not in scene.root.children


def test_destroy_during_update_cleans_registry_and_transform(
    loaded_scene: pu.SceneUnit,
) -> None:
    scene = loaded_scene
    victim = CountingNode(name="ToDestroy")
    comp = victim.add_component(ProbeComponent())

    class Killer(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            victim.destroy()
            assert scene.scene_units is not None
            assert scene.scene_units.one_or_none("ToDestroy") is None
            assert victim._pending_removal

    # Preorder: Killer runs before Victim so mark happens mid-walk.
    scene.root.attach(Killer(name="Killer"))
    scene.root.attach(victim)
    scene.sync_hierarchy_and_world_transforms()
    assert victim._transform_index >= 0

    _step(scene)

    assert victim.parent is None
    assert victim not in scene.root.children
    assert victim.exit_calls == 1
    assert comp.destroy_count == 1
    assert victim._transform_index == -1
    assert scene.scene_units is not None
    assert scene.scene_units.one_or_none("ToDestroy") is None


def test_destroy_wins_over_detach_same_step(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    victim = CountingNode(name="Dual")
    comp = victim.add_component(ProbeComponent())

    class Both(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            self.parent.detach(victim)  # type: ignore[union-attr]
            victim.destroy()

    scene.root.attach(Both(name="Both"))
    scene.root.attach(victim)

    _step(scene)

    assert comp.destroy_count == 1
    assert victim.exit_calls == 1
    assert victim.parent is None


def test_attach_then_detach_same_step(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    child_ref: list[CountingNode] = []

    class Spawner(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            child = CountingNode(name="Brief")
            self.attach(child)
            child_ref.append(child)
            self.detach(child)

    scene.root.attach(Spawner(name="Spawner"))
    _step(scene)

    child = child_ref[0]
    assert child.enter_calls == 1
    assert child.exit_calls == 1
    assert child.parent is None
    assert child not in scene.root.children
    assert child.update_calls == 0


def test_reparent_in_scene_keeps_transform_slot(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    a = pu.NodeUnit(name="A")
    b = pu.NodeUnit(name="B")
    child = pu.NodeUnit(name="Child")
    scene.root.attach(a)
    scene.root.attach(b)
    a.attach(child)

    class Reparenter(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            b.attach(child)

    scene.root.attach(Reparenter(name="Reparenter"))
    scene.sync_hierarchy_and_world_transforms()

    idx = child._transform_index
    store = child._transform_store
    assert idx >= 0
    assert store is scene.transform_store
    count = scene.transform_store.count

    _step(scene)

    assert child.parent is b
    assert child._transform_store is store
    assert child._transform_index >= 0
    assert scene.transform_store.count == count


def test_pending_removal_not_rendered(loaded_scene: pu.SceneUnit) -> None:
    scene = loaded_scene
    victim = CountingNode(name="HideMe")

    class Killer(pu.NodeUnit):
        def update(self, dt: float) -> None:
            _ = dt
            victim.destroy()

    scene.root.attach(Killer(name="Killer"))
    scene.root.attach(victim)

    scene._dispatch_update(0.016)
    # Destroy flush already ran at end of update; render should still skip.
    scene.dispatch_render(_renderer())

    assert victim.render_submit_calls == 0
    assert victim.exit_calls == 1


def test_load_nodes_update_first_step() -> None:
    """Nodes attached during load must not be spawn-gated into skipping first step."""
    child = CountingNode(name="LoadedChild")

    class Level(pu.SceneUnit):
        def on_load(self) -> None:
            self.root.attach(child)

    scene = Level(name="Level")
    scene.load()
    _step(scene)
    assert child.update_calls == 1


def test_app_fixed_step_brackets_scene_manager() -> None:
    """App begin/end_step covers App.update attaches (strict gate)."""
    app = pu.App()
    sm = pu.SceneManager()
    app.scene_manager = sm
    app.config = pu.AppConfig(fixed_update_hz=60, max_substeps_per_frame=1)
    app.window = type(
        "Window",
        (),
        {
            "fixed_delta_time": 1.0 / 60.0,
            "accumulator": 1.0 / 60.0,
            "consume_fixed_steps": lambda self, max_steps: 1,
        },
    )()

    scene = pu.SceneUnit(name="AppScene")
    sm.push(scene)
    sm.apply_pending()

    spawned: list[CountingNode] = []

    def app_fixed_update(dt: float, step: int) -> None:
        _ = dt, step
        child = CountingNode(name="FromApp")
        scene.root.attach(child)
        spawned.append(child)

    app.fixed_update = app_fixed_update  # type: ignore[method-assign]
    app.step_fixed()

    child = spawned[0]
    assert child in scene.root.children
    assert child.update_calls == 0

    app.window.accumulator = app.window.fixed_delta_time
    app.fixed_update = (  # type: ignore[method-assign]
        lambda dt, step: sm.update(dt)
    )
    app.step_fixed()
    assert child.update_calls == 1


def test_on_after_update_attach_is_eligible_next_step() -> None:
    app = pu.App()
    manager = pu.SceneManager()
    app.scene_manager = manager
    app.config = pu.AppConfig(fixed_update_hz=60, max_substeps_per_frame=1)
    app.window = type(
        "Window",
        (),
        {
            "fixed_delta_time": 1.0 / 60.0,
            "accumulator": 1.0 / 60.0,
            "consume_fixed_steps": lambda self, max_steps: 1,
        },
    )()

    scene = pu.SceneUnit(name="AfterUpdateScene")
    manager.push(scene)
    manager.apply_pending()
    child = CountingNode(name="AfterUpdateChild")

    def fixed_update(dt: float, step: int) -> None:
        _ = step
        manager.update(dt)

    app.fixed_update = fixed_update  # type: ignore[method-assign]

    def attach_after_update(dt: float) -> None:
        _ = dt
        scene.root.attach(child)
        app.on_after_update.disconnect(attach_after_update)

    app.on_after_update.connect(attach_after_update)
    app.step_fixed()

    assert child.update_calls == 0
    assert child._skip_update is False

    app.window.accumulator = app.window.fixed_delta_time
    app.step_fixed()

    assert child.update_calls == 1
