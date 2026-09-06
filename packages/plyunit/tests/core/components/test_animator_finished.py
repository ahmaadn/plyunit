from __future__ import annotations

from types import SimpleNamespace

from plyunit.assets.animations import AnimationClip, AnimationFrame, Animations
from plyunit.core.components.builtin.animator import AnimationController
from plyunit.core.components.builtin.sprite import SpriteRenderer
from plyunit.events.event_bus import EventBus


class SpriteStub:
    def set_texture(self, *, asset_key=None, texture=None) -> None:
        pass

    def set_source_rect(self, rect=None) -> None:
        pass


class UnitStub:
    def __init__(self, animations: Animations, sprite: SpriteStub, bus: EventBus | None) -> None:
        self._animations = animations
        self._bus = bus
        self.components = {SpriteRenderer: sprite}

    def one(self, ref, scope: str = "mixed"):
        _ = scope
        if ref is Animations:
            return self._animations
        raise KeyError(ref)

    def one_or_none(self, ref, scope: str = "mixed"):
        _ = scope
        if ref == "@EventBus":
            return self._bus
        return None

    def has_component(self, component_type) -> bool:
        return component_type in self.components

    def __getitem__(self, component_type):
        return self.components[component_type]


def _controller(loop: bool, with_bus: bool = True) -> tuple[AnimationController, EventBus | None]:
    animations = Animations()
    clip = AnimationClip(
        name="once",
        frames=[
            AnimationFrame(asset_id="a", duration=0.1),
            AnimationFrame(asset_id="b", duration=0.1),
        ],
        loop=loop,
        speed=1.0,
    )
    animations.add_clip(clip)
    bus = EventBus() if with_bus else None
    unit = UnitStub(animations, SpriteStub(), bus)
    controller = AnimationController("once")
    controller.unit = unit  # type: ignore[assignment]
    controller.on_attach()
    controller.playing = True
    controller.frame_index = 0
    controller.frame_time = 0.0
    return controller, bus


def test_finished_signal_once_non_loop() -> None:
    controller, bus = _controller(loop=False)
    assert bus is not None
    events: list[str] = []
    bus_events: list[str] = []

    def on_sig(name: str, ctrl: AnimationController) -> None:
        events.append(name)
        assert ctrl is controller

    def on_bus(**kwargs) -> None:
        bus_events.append(kwargs["name"])

    controller.finished.connect(on_sig)
    bus.subscribe("animation.finished", on_bus)

    controller.update(0.15)
    controller.update(0.15)
    assert controller.playing is False
    assert events == ["once"]
    assert bus_events == ["once"]

    controller.update(1.0)
    assert events == ["once"]
    assert bus_events == ["once"]


def test_loop_does_not_emit_finished() -> None:
    controller, _bus = _controller(loop=True, with_bus=False)
    events: list[str] = []
    controller.finished.connect(lambda name, c: events.append(name))
    controller.update(0.5)
    assert controller.playing is True
    assert events == []


def test_finished_without_event_bus() -> None:
    controller, _ = _controller(loop=False, with_bus=False)
    events: list[str] = []
    controller.finished.connect(lambda name, c: events.append(name))
    controller.update(0.25)
    assert events == ["once"]
