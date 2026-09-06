from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import plyunit as pu
from plyunit.assets.animations import AnimationClip, AnimationFrame, Animations
from plyunit.core.components.builtin.animator import AnimationController
from plyunit.core.components.builtin.sprite import SpriteRenderer

unit_module = importlib.import_module("plyunit.core.units.unit")


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


class SpriteStub:
    def __init__(self) -> None:
        self.texture_calls: list[tuple[object | None, object | None]] = []
        self.rect_calls: list[tuple[float, float, float, float] | None] = []

    def set_texture(self, *, asset_key=None, texture=None) -> None:
        if asset_key == "hero":
            texture = "hero-texture"
        self.texture_calls.append((asset_key, texture))

    def set_source_rect(self, rect=None) -> None:
        self.rect_calls.append(rect)


class AssetManagerStub:
    def __init__(self) -> None:
        self.assets = {"hero": "hero-texture"}

    def get_asset(self, key: str) -> object:
        return self.assets[key]


class UnitStub:
    def __init__(
        self,
        animations: Animations,
        asset_manager: AssetManagerStub,
        sprite: SpriteStub | None,
    ) -> None:
        self._animations = animations
        self._asset_manager = asset_manager
        self.components = {}
        if sprite is not None:
            self.components[SpriteRenderer] = sprite

    def one(self, ref, scope: str = "mixed"):
        _ = scope
        if ref is Animations:
            return self._animations
        if ref == "AssetManager":
            return self._asset_manager
        raise KeyError(ref)

    def one_or_none(self, ref, scope: str = "mixed"):
        _ = scope
        return None

    def has_component(self, component_type) -> bool:
        return component_type in self.components

    def __getitem__(self, component_type):
        return self.components[component_type]


def test_sprite_renderer_render_submit_and_flips(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry

    texture = SimpleNamespace(width=10, height=20)
    sprite = SpriteRenderer(
        "",
        # pyrefly: ignore [bad-argument-type]
        texture=texture,
        flip_x=True,
        flip_y=False,
        use_interpolation=False,
    )

    node = pu.NodeUnit("Hero")
    node.transform.world.position = (1.0, 2.0)
    node.transform.world.rotation = 15.0
    sprite.unit = node

    calls: list[dict[str, object]] = []

    class Renderer:
        def render_sprite(self, **kwargs):
            calls.append(kwargs)

    # pyrefly: ignore [bad-argument-type]
    sprite.render_submit(Renderer())

    assert calls
    draw = calls[0]
    assert draw["pos"] == (1.0, 2.0)
    assert draw["source"] == (10.0, 0.0, -10.0, 20.0)

    empty_texture = SimpleNamespace(width=0, height=0)
    # pyrefly: ignore [bad-argument-type]
    sprite_empty = SpriteRenderer("", texture=empty_texture)
    assert sprite_empty._compute_flipped_source_rect() is None


def test_sprite_renderer_uses_asset_region_without_flip() -> None:
    texture = SimpleNamespace(width=128, height=128)
    sprite = SpriteRenderer("well", use_interpolation=False)
    calls: list[dict[str, object]] = []

    class Assets:
        def __getitem__(self, key):
            assert key == "well"
            return texture

        def get_source_rect(self, key):
            assert key == "well"
            return (1.0, 1.0, 60.0, 60.0)

    class Renderer:
        def render_sprite(self, **kwargs):
            calls.append(kwargs)

    node = pu.NodeUnit("Well")
    node.transform.world.position = (10.0, 20.0)
    node.one = lambda ref, scope="mixed": Assets() if ref == "Assets" else None
    sprite.unit = node

    sprite.render_submit(Renderer())

    assert calls[0]["source"] == (1.0, 1.0, 60.0, 60.0)


def test_sprite_renderer_uses_render_context_transform() -> None:
    texture = SimpleNamespace(width=10, height=20)
    # pyrefly: ignore [bad-argument-type]
    sprite = SpriteRenderer("", texture=texture, use_interpolation=True)
    node = pu.NodeUnit("Hero")
    node.transform.world.position = (1.0, 2.0)
    sprite.unit = node

    calls: list[dict[str, object]] = []

    class Renderer:
        def render_sprite(self, **kwargs):
            calls.append(kwargs)

    context = SimpleNamespace(
        pass_name="world",
        state_id=0,
        y_sort=False,
        y_sort_origin=0.0,
        screen_space=False,
        render_transform=SimpleNamespace(position=(9.0, 8.0), rotation=30.0),
    )
    # pyrefly: ignore [bad-argument-type]
    sprite.render_submit(Renderer(), context)

    assert calls[0]["pos"] == (9.0, 8.0)
    assert calls[0]["rotation"] == 30.0


def test_sprite_renderer_setters_and_errors() -> None:
    texture = SimpleNamespace(width=5, height=6)
    # pyrefly: ignore [bad-argument-type]
    sprite = SpriteRenderer("", texture=texture)

    # pyrefly: ignore [bad-argument-type]
    sprite.set_texture(texture=SimpleNamespace(width=7, height=8))
    # pyrefly: ignore [missing-attribute]
    assert sprite._texture.width == 7

    sprite.set_texture(asset_key="hero")
    assert sprite._asset_key == "hero"

    with pytest.raises(
        ValueError, match="Either asset_key or texture must be provided"
    ):
        sprite.set_texture()

    sprite.set_source_rect((1, 2, 3, 4))
    assert sprite.source_rect == (1.0, 2.0, 3.0, 4.0)

    sprite.set_source_rect(None)
    assert sprite.source_rect is None

    sprite.set_layer(99)
    assert sprite.layer == 99


def test_animation_controller_on_attach_and_sync(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry

    animations = Animations()
    texture = SimpleNamespace(name="tex")
    clip = AnimationClip(
        name="idle",
        frames=[
            # pyrefly: ignore [bad-argument-type]
            AnimationFrame(texture=texture, source_rect=(0, 0, 8, 8), duration=0.1),
            AnimationFrame(asset_id="hero", source_rect=(8, 0, 8, 8), duration=0.1),
        ],
        loop=False,
        speed=1.0,
    )
    animations.add_clip(clip)

    sprite = SpriteStub()
    unit = UnitStub(animations, AssetManagerStub(), sprite)

    controller = AnimationController("idle")
    # pyrefly: ignore [bad-assignment]
    controller.unit = unit
    controller.on_attach()

    controller.playing = True
    controller.frame_index = 0
    controller.frame_time = 0.0

    controller._sync_sprite_renderer()
    assert sprite.texture_calls[-1][1] is texture
    assert sprite.rect_calls[-1] == (0, 0, 8, 8)

    controller.update(0.2)
    assert sprite.texture_calls[-1][1] == "hero-texture"
    assert sprite.rect_calls[-1] == (8, 0, 8, 8)
    assert controller.playing is False

    controller.on_destroy()
    assert controller.sprite is None


def test_animation_controller_play_validation_and_attach_error(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry

    animations = Animations()
    clip = AnimationClip(
        name="idle",
        frames=[AnimationFrame(asset_id="hero")],
        loop=True,
        speed=1.0,
    )
    animations.add_clip(clip, group="ally")

    unit = UnitStub(animations, AssetManagerStub(), SpriteStub())

    controller = AnimationController("idle", group="enemy")
    # pyrefly: ignore [bad-assignment]
    controller.unit = unit

    with pytest.raises(KeyError, match="animation clip"):
        controller.play("idle")

    unit_missing_sprite = UnitStub(animations, AssetManagerStub(), None)
    controller_missing = AnimationController("idle")
    # pyrefly: ignore [bad-assignment]
    controller_missing.unit = unit_missing_sprite

    with pytest.raises(ValueError, match="SpriteComponent"):
        controller_missing.on_attach()
