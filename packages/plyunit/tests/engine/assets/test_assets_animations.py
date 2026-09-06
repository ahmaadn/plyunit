from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import plyunit as pu
from plyunit.assets.animations import AnimationClip, AnimationFrame, Animations

unit_module = importlib.import_module("plyunit.core.units.unit")


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


def test_animation_frame_and_clip_validation() -> None:
    with pytest.raises(ValueError, match="requires either asset_id or texture"):
        AnimationFrame()

    with pytest.raises(ValueError, match="duration must be > 0"):
        AnimationFrame(asset_id="hero", duration=0.0)

    frame = AnimationFrame(asset_id="hero", duration=0.2)
    assert frame.asset_id == "hero"

    with pytest.raises(ValueError, match="requires at least 1 frame"):
        AnimationClip(name="walk", frames=[])

    with pytest.raises(ValueError, match="speed must be > 0"):
        AnimationClip(name="walk", frames=[frame], speed=0.0)


def test_animations_add_clip_groups_and_base_path(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry

    animations = Animations()
    frame = AnimationFrame(asset_id="idle")
    clip = AnimationClip(name="idle", frames=[frame], loop=False, speed=1.5)

    animations.add_clip(clip, group="player")

    assert animations.get_clip("idle") is clip
    assert animations.is_clip_in_group("idle", "player") is True
    assert "idle" in animations.get_clips_by_group("player")

    animations.set_base_path(Path("assets"))
    assert animations.base_path == Path("assets")


def test_animations_load_animation_defaults_and_group(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry

    animations = Animations()
    data = {
        "group": "enemy",
        "animations": {
            "idle": {
                "default": {"duration": 0.2, "source_rect": [0, 0, 16, 16]},
                "frames": [
                    {"asset_id": "idle_1"},
                    {
                        "asset_id": "idle_2",
                        "duration": 0.3,
                        "source_rect": [16, 0, 16, 16],
                    },
                ],
                "loop": False,
                "speed": 2.0,
            }
        },
    }

    animations.load_animation(data)

    clip = animations.get_clip("idle")
    assert clip.loop is False
    assert clip.speed == 2.0
    assert clip.frames[0].duration == 0.2
    assert clip.frames[0].source_rect == [0, 0, 16, 16]
    assert clip.frames[1].duration == 0.3
    assert clip.frames[1].source_rect == [16, 0, 16, 16]

    assert animations.is_clip_in_group("idle", "enemy") is True
