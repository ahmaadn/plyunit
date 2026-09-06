"""Core animation management for the plyunit game engine.

This module provides the animation data structures (``AnimationFrame`` and
``AnimationClip``) plus the ``Animations`` service, which stores clips,
groups them per group, and loads animation configuration from JSON files.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from plyunit.core.types import Texture
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils.io import read_json


@dataclass(slots=True)
class AnimationFrame:
    """Representation of a single frame in an animation clip.

    Attributes:
        asset_id: Texture asset ID.
        texture: GPU texture object when not using an ID.
        source_rect: Texture area (x, y, w, h).
        duration: How long the frame is shown (in seconds).
    """

    asset_id: str | None = None
    texture: Texture | None = None
    source_rect: tuple[float, float, float, float] | None = None
    duration: float = 0.1

    def __post_init__(self) -> None:
        """Validate frame consistency after initialization.

        Raises:
            ValueError: If neither ``asset_id`` nor ``texture`` is given,
                or if ``duration`` is not greater than 0.
        """
        if self.asset_id is None and self.texture is None:
            raise ValueError("animation frame requires either asset_id or texture")

        if self.duration <= 0:
            raise ValueError("animation frame duration must be > 0")


@dataclass(slots=True)
class AnimationClip:
    """An animation clip holding a set of frames and their metadata.

    Attributes:
        name: The animation clip name.
        frames: The list of frames making up this animation.
        loop: Whether this animation loops continuously.
        speed: Playback speed multiplier (default: 1.0).
        paused: Whether the animation starts paused.
    """

    name: str
    frames: list[AnimationFrame]
    loop: bool = True
    speed: float = 1.0
    paused: bool = False

    def __post_init__(self) -> None:
        """Validate clip consistency after initialization.

        Raises:
            ValueError: If ``frames`` is empty, or if ``speed`` is not
                greater than 0.
        """
        if not self.frames:
            raise ValueError("animation clip requires at least 1 frame")
        if self.speed <= 0:
            raise ValueError("animation clip speed must be > 0")


class Animations(ServiceUnit):
    """Service that provides and manages animations in the plyunit game engine.

    This service holds the list of animation clips and groups them by
    group name (e.g. "player_animations").

    Attributes:
        clips: Mapping of clip names to ``AnimationClip`` objects.
        groups: Mapping of group names to the sets of member clip names.
        base_path: Base path used to resolve frame ``asset_id`` values
            when loading textures.
    """

    def __init__(self) -> None:
        """Initialize the animation manager with empty storage.

        Creates empty clip and group registries, plus the internal
        clip-to-group mapping.
        """
        super().__init__("Animations", tags={"service", "animations"})
        self.clips: dict[str, AnimationClip] = {}
        self.groups: dict[str, set[str]] = defaultdict(set)
        self._clip_to_group: dict[str, str] = {}

        self.base_path = Path("")

    def add_clip(self, clip: AnimationClip, *, group: str | None = None) -> None:
        """Add a new animation clip to the storage.

        Args:
            clip: The animation clip object to add.
            group: The animation clip group name (optional).
        """
        self.clips[clip.name] = clip
        if group:
            self.groups[group].add(clip.name)
            self._clip_to_group[clip.name] = group

    def get_clip(self, name: str) -> AnimationClip:
        """Get an animation clip by name.

        Args:
            name: The animation clip name.

        Returns:
            The requested animation clip.

        Raises:
            KeyError: If the clip is not found.
        """
        return self.clips[name]

    def get_clips_by_group(self, group: str) -> dict[str, AnimationClip]:
        """Get all animation clips in a group.

        Args:
            group: The group name.

        Returns:
            A dictionary mapping clip names to animation clip objects.
        """
        clip_names = self.groups.get(group, set())
        return {name: self.clips[name] for name in clip_names}

    def is_clip_in_group(self, clip_name: str, group: str) -> bool:
        """Check whether an animation clip belongs to a given group.

        Args:
            clip_name: The animation clip name.
            group: The group name.

        Returns:
            True if the clip is in the group, False otherwise.
        """
        return clip_name in self.groups.get(group, set())

    def load_animation(self, animation_data: dict) -> None:
        """Load a set of animations from a configuration dictionary.

        Args:
            animation_data: Parsed-JSON configuration dictionary.
        """
        for clip_name, clip_data in animation_data.get("animations", {}).items():
            frames = []

            default_duration = clip_data.get("default", {}).get("duration", 0.1)

            default_source_rect = clip_data.get("default", {}).get("source_rect", None)

            for frame_data in clip_data.get("frames", []):
                frame = AnimationFrame(
                    asset_id=frame_data.get("asset_id"),
                    source_rect=frame_data.get("source_rect", default_source_rect),
                    duration=frame_data.get("duration", default_duration),
                )
                frames.append(frame)

            if frames:
                clip = AnimationClip(
                    name=clip_name,
                    frames=frames,
                    loop=clip_data.get("loop", True),
                    speed=clip_data.get("speed", 1.0),
                    paused=clip_data.get("paused", False),
                )

                group_id = animation_data.get("group")
                self.add_clip(clip, group=group_id)

    def load(self, file_path: str) -> None:
        """Load animations from a JSON file on disk.

        Args:
            file_path: Path (relative to `base_path`) of the JSON file.
        """
        self.load_animation(read_json(str(self.base_path / file_path)))

    def set_base_path(self, base_path: Path) -> None:
        """Set the base path for resolving frame asset_id values.

        For example, with base_path = "characters/hero" and a frame
        asset_id = "walk1", loading looks up the asset with key
        "characters/hero/walk1" in the AssetManager.
        """
        self.base_path = base_path

    def clear(self) -> None:
        """Remove all animation clips and groups from the runtime."""
        self.clips.clear()
        self.groups.clear()
        self._clip_to_group.clear()
