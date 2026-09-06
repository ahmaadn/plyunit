from __future__ import annotations

import importlib

import pytest

import plyunit as pu

unit_module = importlib.import_module("plyunit.core.units.unit")


class DummyUnit(pu.Unit):
    pass


class DummyNodeUnit(pu.NodeUnit):
    pass


class EnemyUnit(pu.Unit):
    pass


class MarkerComponent(pu.Component):
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


class ExtraComponent(pu.Component):
    def __init__(self) -> None:
        super().__init__()
        self.destroy_count = 0

    def on_destroy(self) -> None:
        self.destroy_count += 1


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_unit_defaults_and_optional_auto_register(
    isolated_registry: pu.UnitRegistry,
) -> None:
    unit = DummyUnit()
    assert unit.name == "DummyUnit"
    assert unit.tags == set()
    assert isolated_registry.one_or_none("DummyUnit") is None

    registered = DummyUnit(name="Player", tags={"hero"}, register=True)
    assert isolated_registry.one("Player") is registered
    assert isolated_registry.one("#hero") is registered


def test_tag_mutation_updates_registry_indexes(
    isolated_registry: pu.UnitRegistry,
) -> None:
    unit = DummyUnit(name="Enemy", register=True)

    unit.add_tag("flying")
    assert isolated_registry.one("#flying") is unit

    unit.remove_tag("flying")
    assert isolated_registry.one_or_none("#flying") is None

    unit.set_tags({"boss", "elite"})
    assert isolated_registry.one("#boss") is unit
    assert isolated_registry.one("#elite") is unit


def test_component_lifecycle_through_unit_runners() -> None:
    unit = DummyNodeUnit(name="Runner")
    component = unit.add_component(MarkerComponent())

    assert component is unit[MarkerComponent]
    assert unit.has_component(MarkerComponent) is True

    unit._update_components(0.016)
    unit._update_components(0.016)
    unit._render_components({"frame": 1})

    assert component.start_count == 1
    assert component.update_count == 2
    assert component.render_submit_count == 1


def test_component_disable_and_destroy_behavior() -> None:
    unit = DummyNodeUnit(name="Runner")
    component = unit.add_component(MarkerComponent())

    component.enabled = False
    unit._update_components(0.016)
    unit._render_components({"frame": 1})

    assert component.start_count == 1
    assert component.update_count == 0
    assert component.render_submit_count == 0

    unit.destroy_component(component)

    assert component.is_destroyed is True
    assert component.destroy_count == 1
    assert component.unit is None
    assert unit.has_component(MarkerComponent) is False


def test_registry_queries_by_name_tag_and_type(
    isolated_registry: pu.UnitRegistry,
) -> None:
    EnemyUnit(name="Enemy", tags={"enemy"}, register=True)
    second = EnemyUnit(name="Enemy", tags={"enemy"}, register=True)

    by_name = isolated_registry.group("Enemy")
    by_tag = isolated_registry.group("#enemy")
    by_type = isolated_registry.group(EnemyUnit)

    assert len(by_name) == 2
    assert len(by_tag) == 2
    assert len(by_type) == 2
    with pytest.raises(pu.MultipleResultsFound):
        isolated_registry.one("Enemy")

    assert isolated_registry.one_or_none("Missing") is None
    assert isolated_registry.one_or_none("#missing") is None

    with pytest.raises(pu.NoResultFound):
        isolated_registry.one("Missing")

    # duplicate-name one() should raise (already asserted above)

    assert isolated_registry.one_or_none("Missing") is None
    assert second in by_name


def test_registry_explicit_query_helpers(isolated_registry: pu.UnitRegistry) -> None:
    one = EnemyUnit(name="Enemy", tags={"enemy"}, register=True)
    EnemyUnit(name="Enemy", tags={"enemy"}, register=True)

    # registry helpers vs group
    assert isolated_registry.find_by_name("Enemy") == isolated_registry.group("Enemy")
    assert isolated_registry.find_by_tag("enemy") == isolated_registry.group("#enemy")

    # unique name helper
    assert isolated_registry.find_unique_name("Enemy") == []
    unique = EnemyUnit(name="Boss", tags={"enemy"}, is_unique=True, register=True)
    assert isolated_registry.find_unique_name("Boss") == [unique]

    # Unit-level wrappers (mixed scope default)
    assert one.find_by_name("Enemy") == one.group("Enemy")
    assert one.find_by_tag("enemy") == one.group("#enemy")
    assert one.find_unique_name("Boss") == [unique]


def test_unit_noop_methods_and_tag_guard(
    isolated_registry: pu.UnitRegistry,
) -> None:
    unit = DummyUnit(name="Noop", register=True)

    # unit.update(0.016)
    # unit.render_submit({"frame": 1})

    unit.add_tag("dup")
    unit.add_tag("dup")
    assert unit.tags == {"dup"}

    unit.remove_tag("missing")
    assert isolated_registry.one("#dup") is unit


def test_add_component_duplicate_guard_branch() -> None:
    unit = DummyNodeUnit(name="Guarded")
    unit.components[MarkerComponent] = MarkerComponent()

    with pytest.raises(ValueError):
        unit.add_component(MarkerComponent())


def test_destroy_component_handles_already_destroyed_state() -> None:
    unit = DummyNodeUnit(name="Destroyed")
    component = MarkerComponent()

    unit.components[type(component)] = component
    component.unit = unit

    unit.destroy_component(component)

    assert component.destroy_count == 1
    assert component.unit is None
    assert type(component) not in unit.components


def test_destroy_all_components_and_started_component_branch() -> None:
    unit = DummyNodeUnit(name="AllComponents")
    one = unit.add_component(MarkerComponent())
    second = unit.add_component(ExtraComponent())

    one._started = True
    unit._update_components(0.016)
    assert one.start_count == 0
    assert one.update_count == 1

    unit.destroy_all_components()

    assert one.destroy_count == 1
    assert second.destroy_count == 1
    assert list(unit.iter_components()) == []


def test_registry_magic_getitem_and_type_paths(
    isolated_registry: pu.UnitRegistry,
) -> None:
    enemy = EnemyUnit(name="EnemyOne", register=True)

    assert isolated_registry["EnemyOne"] is enemy
    assert isolated_registry.one_or_none(EnemyUnit) is enemy
    assert isolated_registry.one(EnemyUnit) is enemy
    assert isolated_registry.one_or_none(EnemyUnit) is enemy

    EnemyUnit(name="EnemyTwo", register=True)
    with pytest.raises(pu.MultipleResultsFound):
        isolated_registry.one_or_none(EnemyUnit)


def test_registry_unregister_tolerates_missing_bucket_members() -> None:
    registry = pu.UnitRegistry()
    unit = DummyUnit(name="Ghost", tags={"alpha"})
    other = DummyUnit(name="Other")

    registry.register(unit)
    registry._by_name[unit.name] = [other]
    registry._by_tag["alpha"] = [other]
    registry._by_type[type(unit)] = [other]

    registry.unregister(unit)

    assert registry._by_name[unit.name] == [other]
    assert registry._by_tag["alpha"] == [other]
    assert registry._by_type[type(unit)] == [other]


def test_service_unit_singleton_registry_behavior(
    isolated_registry: pu.UnitRegistry,
) -> None:
    service = pu.ServiceUnit(name="Audio", tags={"service"})

    assert isolated_registry.one("Audio") is service
    assert isolated_registry.one("#service") is service

    isolated_registry.unregister(service)
    assert isolated_registry.one_or_none("Audio") is None
    assert isolated_registry.one_or_none("#service") is None


def test_scene_unit_singleton_registry_can_be_removed(
    isolated_registry: pu.UnitRegistry,
) -> None:
    scene = pu.SceneUnit(name="GameplayScene")

    assert isolated_registry.one("GameplayScene") is scene

    isolated_registry.unregister(scene)
    assert isolated_registry.one_or_none("GameplayScene") is None


def test_unit_scoped_query_scene_global_and_mixed(
    isolated_registry: pu.UnitRegistry,
) -> None:
    global_enemy = EnemyUnit(name="Enemy", tags={"enemy"}, register=True)

    scene = pu.SceneUnit(name="BattleScene")
    scene._attach_subtree(scene.root)

    scene_enemy = pu.NodeUnit(name="Enemy", tags={"enemy"})
    observer = pu.NodeUnit(name="Observer")

    scene.root.attach(scene_enemy)
    scene.root.attach(observer)

    assert observer.one("Enemy", scope="scene") is scene_enemy
    assert observer.one("Enemy", scope="global") is global_enemy
    assert observer.one("Enemy", scope="mixed") is scene_enemy

    assert observer.one("#enemy", scope="scene") is scene_enemy
    assert observer.one("#enemy", scope="global") is global_enemy

    scene.root.detach(scene_enemy)
    assert observer.one("Enemy", scope="mixed") is global_enemy
    assert observer.one_or_none("Missing", scope="scene") is None


def test_service_unit_query_always_uses_global_scope(
    isolated_registry: pu.UnitRegistry,
) -> None:
    global_enemy = EnemyUnit(name="Enemy", register=True)
    service = pu.ServiceUnit(name="Audio", tags={"service"})

    scene = pu.SceneUnit(name="BattleScene")
    scene._attach_subtree(scene.root)

    scene_enemy = pu.NodeUnit(name="Enemy")
    observer = pu.NodeUnit(name="Observer")
    scene.root.attach(scene_enemy)
    scene.root.attach(observer)

    assert observer.one_or_none("Audio", scope="scene") is None
    assert observer.one("Audio", scope="global") is service

    # ServiceUnit query scope "scene"/"mixed" dipaksa ke global.
    assert service.one("Enemy", scope="scene") is global_enemy
    assert service.one("Enemy", scope="mixed") is global_enemy
    assert service.one("Enemy", scope="global") is global_enemy
