from __future__ import annotations

import pytest

import plyunit as pu
import plyunit.services.scene_manager as scene_manager_module


class CountingScene(pu.SceneUnit):
    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.load_count = 0
        self.unload_count = 0

    def on_load(self) -> None:
        self.load_count += 1

    def on_unload(self) -> None:
        self.unload_count += 1


def test_scene_manager_emits_queue_and_applied_signals() -> None:
    manager = scene_manager_module.SceneManager()

    queued: list[tuple[scene_manager_module.TransitionType, pu.SceneUnit | None]] = []
    applied: list[scene_manager_module.SceneTransitionEvent] = []

    manager.on_transition_queued.connect(lambda kind, unit: queued.append((kind, unit)))
    manager.on_transition_applied.connect(lambda event: applied.append(event))

    first = CountingScene("First")
    second = CountingScene("Second")

    manager.push(first)

    assert manager.current is None
    assert queued == [(scene_manager_module.TransitionType.PUSH, first)]

    manager.apply_pending()

    assert manager.current is first
    assert first.load_count == 1

    first_event = applied[-1]
    assert first_event.kind is scene_manager_module.TransitionType.PUSH
    assert first_event.previous is None
    assert first_event.current is first
    assert first_event.depth == 1

    manager.change(second)
    manager.apply_pending()

    assert manager.current is second
    assert first.unload_count == 1
    assert second.load_count == 1

    second_event = applied[-1]
    assert second_event.kind is scene_manager_module.TransitionType.CHANGE
    assert second_event.previous is first
    assert second_event.current is second
    assert second_event.depth == 1

    manager.pop()
    manager.apply_pending()

    assert manager.current is None
    assert second.unload_count == 1

    third_event = applied[-1]
    assert third_event.kind is scene_manager_module.TransitionType.POP
    assert third_event.previous is second
    assert third_event.current is None
    assert third_event.depth == 0


def test_scene_controller_fade_change_and_signals() -> None:
    manager = scene_manager_module.SceneManager()

    current_scene = CountingScene("Current")
    manager.push(current_scene)
    manager.apply_pending()

    controller = scene_manager_module.SceneController(duration=0.1)
    manager.set_transition_behavior(controller)

    started: list[scene_manager_module.TransitionType] = []
    midpoint: list[tuple[scene_manager_module.TransitionType, pu.SceneUnit | None]] = []
    finished: list[pu.SceneUnit | None] = []

    manager.on_transition_started.connect(lambda kind: started.append(kind))
    manager.on_transition_midpoint.connect(
        lambda kind, scene: midpoint.append((kind, scene))
    )
    manager.on_transition_finished.connect(lambda scene: finished.append(scene))

    next_scene = CountingScene("Next")

    assert manager.request_change(lambda: next_scene) is True
    assert manager.request_pop() is False
    assert controller.busy is True

    manager.update(0.1)

    assert controller.state == "fading_in"
    assert controller.alpha == 255.0
    assert manager.current is current_scene

    manager.apply_pending()

    assert manager.current is next_scene
    assert current_scene.unload_count == 1
    assert next_scene.load_count == 1

    assert started == [scene_manager_module.TransitionType.CHANGE]
    assert midpoint == [(scene_manager_module.TransitionType.CHANGE, next_scene)]

    manager.update(0.1)

    assert controller.state == "idle"
    assert controller.alpha == 0.0
    assert finished == [next_scene]


def test_scene_controller_requires_scene_factory_for_non_pop() -> None:
    manager = scene_manager_module.SceneManager()
    controller = scene_manager_module.SceneController()
    manager.set_transition_behavior(controller)

    with pytest.raises(ValueError, match="scene_factory wajib"):
        manager.request_transition(scene_manager_module.TransitionType.PUSH)

    with pytest.raises(ValueError, match="scene_factory wajib"):
        manager.request_transition(scene_manager_module.TransitionType.CHANGE)

    with pytest.raises(ValueError, match="scene_factory wajib"):
        manager.request_transition(scene_manager_module.TransitionType.REPLACE_ALL)

    assert manager.request_transition(scene_manager_module.TransitionType.POP) is True


def test_replace_all_unloads_stack_from_top_to_bottom() -> None:
    events: list[str] = []

    class OrderedScene(CountingScene):
        def on_unload(self) -> None:
            super().on_unload()
            events.append(self.name)

    manager = scene_manager_module.SceneManager()
    first = OrderedScene("First")
    second = OrderedScene("Second")
    replacement = OrderedScene("Replacement")
    for scene in (first, second):
        manager.push(scene)
        manager.apply_pending()

    manager.replace_all(replacement)
    manager.apply_pending()

    assert events == ["Second", "First"]
    assert manager.current is replacement
    assert manager.depth == 1
    assert replacement.load_count == 1


def test_scene_manager_rejects_transition_without_behavior() -> None:
    manager = scene_manager_module.SceneManager()
    manager.set_transition_behavior(None)

    with pytest.raises(RuntimeError, match="belum dipasang"):
        manager.request_pop()


def test_scene_manager_stack_limit_cleanup_and_repr() -> None:
    manager = scene_manager_module.SceneManager()
    scenes = [CountingScene(str(index)) for index in range(manager.MAX_STACK_DEPTH)]
    for scene in scenes:
        manager.push(scene)
        manager.apply_pending()

    manager.push(CountingScene("overflow"))
    with pytest.raises(RuntimeError, match="stack overflow"):
        manager.apply_pending()

    assert repr(manager) == f"SceneManager(stack={[scene.name for scene in scenes]})"
    manager.shutdown()
    assert manager.depth == 0
    assert all(scene.unload_count == 1 for scene in scenes)

    manager.shutdown()
    assert all(scene.unload_count == 1 for scene in scenes)
