"""Backend-agnostic asset data shapes for the engine.

Contains configuration/runtime dataclasses and TypedDicts for the
spritesheet animation JSON schema. ``ConfigTexture``, ``ConfigImage``,
and ``TextureData`` are runtime dataclasses; JSON input still arrives
as a ``dict`` (e.g. ``Assets.load_from_dict``) and is then parsed into
dataclasses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from plyunit.core.types import ColorType, PosType, RectType, SourceRectType, Texture

if TYPE_CHECKING:
    import numpy as np


class _TextureParams(TypedDict, total=False):
    """Optional texture rendering parameters.

    Attributes:
        pos: Position coordinates (x, y).
        tint: Tint/overlay color.
        rotation: Texture rotation (degrees).
        scale: Render scale.
        source: Source area of the texture (x, y, w, h).
        dest: Destination area of the render on screen.
        origin: Pivot point for rotation/position.
    """

    pos: PosType
    tint: ColorType
    rotation: float
    scale: float
    source: SourceRectType
    dest: RectType
    origin: PosType


@dataclass(slots=True)
class ConfigTexture:
    """Texture property configuration (runtime).

    Attributes:
        filter: Texture filter mode ("nearest" or "linear").
        wrap: Texture wrap mode ("repeat", "clamp", or "mirror").
        mipmap: Whether to generate mipmaps.
        srgb: Whether to use the sRGB color space.
        premultiply_alpha: Whether to pre-multiply the alpha channel.
        color_key: Color replaced with transparency on load.
    """

    filter: Literal["nearest", "linear"] = "nearest"
    wrap: Literal["repeat", "clamp", "mirror"] = "clamp"
    mipmap: bool = False
    srgb: bool = True
    premultiply_alpha: bool = False
    color_key: ColorType = (0, 0, 0, 255)


@dataclass(slots=True)
class ConfigImage:
    """Image/asset configuration (runtime, parsed from JSON).

    Attributes:
        id: Unique ID for the asset.
        image_path: Path to the image file (relative to the asset base).
        texture: Texture property configuration.
        type: The asset kind ("image" or "spritesheet").
        config_path: Path of the JSON configuration file (when loaded from disk).
    """

    id: str
    image_path: str
    texture: ConfigTexture = field(default_factory=ConfigTexture)
    type: Literal["image", "spritesheet"] = "image"
    config_path: Path | str | None = None


@dataclass(slots=True)
class TextureData:
    """In-memory texture data (the Assets cache).

    Attributes:
        parent_id: ID of the main/parent asset (itself when standalone).
        texture: GPU texture object (backend-specific, satisfies the Texture Protocol).
        source_rect: The specific texture area (x, y, w, h).
    """

    parent_id: str
    texture: Texture
    source_rect: tuple[float, float, float, float]


def config_texture_from_dict(
    data: Mapping[str, Any] | ConfigTexture | None = None,
    *,
    defaults: ConfigTexture | None = None,
) -> ConfigTexture:
    """Parse a mapping/dict (or copy a ConfigTexture) into a ConfigTexture.

    Args:
        data: A texture-field mapping, a ConfigTexture instance, or None.
        defaults: Fallback values; defaults to ``ConfigTexture()``.

    Returns:
        A new ``ConfigTexture`` instance.
    """
    base = defaults or ConfigTexture()
    if data is None:
        return ConfigTexture(
            filter=base.filter,
            wrap=base.wrap,
            mipmap=base.mipmap,
            srgb=base.srgb,
            premultiply_alpha=base.premultiply_alpha,
            color_key=base.color_key,
        )
    if isinstance(data, ConfigTexture):
        return ConfigTexture(
            filter=data.filter,
            wrap=data.wrap,
            mipmap=data.mipmap,
            srgb=data.srgb,
            premultiply_alpha=data.premultiply_alpha,
            color_key=data.color_key,
        )

    color_key = data.get("color_key", base.color_key)
    if isinstance(color_key, list):
        color_key = tuple(color_key)

    return ConfigTexture(
        filter=data.get("filter", base.filter),
        wrap=data.get("wrap", base.wrap),
        mipmap=bool(data.get("mipmap", base.mipmap)),
        srgb=bool(data.get("srgb", base.srgb)),
        premultiply_alpha=bool(data.get("premultiply_alpha", base.premultiply_alpha)),
        color_key=color_key if color_key is not None else base.color_key,
    )


def config_image_from_dict(
    data: Mapping[str, Any],
    *,
    config_path: Path | str | None = None,
    defaults: ConfigTexture | None = None,
) -> ConfigImage:
    """Parse a JSON configuration dictionary into a ``ConfigImage``.

    Args:
        data: Asset configuration dictionary (from ``read_json`` / load_from_dict).
        config_path: Overrides the config file path; when None, uses the
            value in ``data``.
        defaults: Default texture fields.

    Returns:
        A ``ConfigImage`` instance.
    """
    resolved_path = config_path if config_path is not None else data.get("config_path")
    asset_type = data.get("type") or "image"
    if asset_type not in ("image", "spritesheet"):
        asset_type = "image"

    return ConfigImage(
        id=str(data.get("id") or ""),
        image_path=str(data.get("image_path") or ""),
        texture=config_texture_from_dict(data.get("texture"), defaults=defaults),
        type=asset_type,  # type: ignore[arg-type]
        config_path=resolved_path,
    )


class SpriteSheetFrameConfig(TypedDict):
    """Configuration of an individual frame in a spritesheet animation.

    Attributes:
        asset_id: The asset/region ID for this frame.
        duration: How long the frame is shown, in seconds.
    """

    asset_id: str
    duration: float


class SpriteSheetAnimationConfig(TypedDict, total=False):
    """Animation configuration inside a spritesheet group.

    Attributes:
        frames: The list of frame configurations making up the animation.
        loop: The animation loop state.
        speed: The animation speed multiplier.
        paused: The animation's initial paused state.
    """

    frames: list[SpriteSheetFrameConfig]
    loop: bool
    speed: float
    paused: bool


class SpriteSheetGroupConfig(TypedDict):
    """A spritesheet animation group.

    Attributes:
        group: The animation group name.
        animations: Dictionary mapping animation names to their configuration.
    """

    group: str
    animations: dict[str, SpriteSheetAnimationConfig]


class SpriteSheetConfig(TypedDict, total=False):
    """Configuration of an entire spritesheet JSON file.

    Attributes:
        id: The spritesheet ID.
        image_path: Relative path to the image.
        texture: Texture property configuration (raw dict).
        regions: Mapping of region_id -> rect list or a dict with a rect.
        animation_groups: The list of animation groups.
    """

    id: str
    image_path: str
    texture: dict
    regions: dict[str, list[float] | dict]
    animation_groups: list[SpriteSheetGroupConfig]


@dataclass(frozen=True)
class ShapedText:
    """The shaping result for one string: per-glyph positions/sizes/UVs
    relative to the pen origin (0, 0). Reusable at any position/rotation
    without recomputing glyphs."""

    offsets_xy: np.ndarray  # (n, 2) float32
    sizes_wh: np.ndarray  # (n, 2) float32
    uv_rects: np.ndarray  # (n, 4) float32 — u0,v0,u1,v1
    tex_id: int
    total_width: float
    total_height: float


@dataclass(frozen=True)
class TemplateText:
    """Spec template text."""

    font_name: str
    spacing: float | None
    font_size: int


type ShapeKey = tuple[str, str, int, float]  # font_name, text, font_size, spacing


__all__ = [
    "ConfigImage",
    "ConfigTexture",
    "ShapeKey",
    "ShapedText",
    "SpriteSheetAnimationConfig",
    "SpriteSheetConfig",
    "SpriteSheetFrameConfig",
    "SpriteSheetGroupConfig",
    "TemplateText",
    "TextureData",
    "config_image_from_dict",
    "config_texture_from_dict"
]
