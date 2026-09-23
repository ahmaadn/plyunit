"""Backend-agnostic asset data shapes for the engine.

Contains configuration/runtime dataclasses and TypedDicts for the
image/spritesheet animation JSON schema. ``TextureProperty``,
``ImageData``, and ``TextureData`` are runtime dataclasses; JSON input
still arrives as a ``dict`` (e.g. ``Assets.load_from_dict``) and is
then parsed into dataclasses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Required, TypedDict

from plyunit.core.types import ColorType, RectType, Texture

if TYPE_CHECKING:
    import numpy as np


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


@dataclass(slots=True)
class TextureProperty:
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

    @classmethod
    def from_dict(
        cls, data: TextureConfig | None, defaults: TextureProperty | None = None
    ) -> TextureProperty:
        base = defaults or TextureProperty()
        if data is None:
            return cls(
                filter=base.filter,
                wrap=base.wrap,
                mipmap=base.mipmap,
                srgb=base.srgb,
                premultiply_alpha=base.premultiply_alpha,
                color_key=base.color_key,
            )

        color_key = data.get("color_key", base.color_key)
        if isinstance(color_key, list):
            color_key = tuple(color_key)

        return cls(
            filter=data.get("filter", base.filter),
            wrap=data.get("wrap", base.wrap),
            mipmap=bool(data.get("mipmap", base.mipmap)),
            srgb=bool(data.get("srgb", base.srgb)),
            premultiply_alpha=bool(
                data.get("premultiply_alpha", base.premultiply_alpha)
            ),
            color_key=color_key if color_key is not None else base.color_key,
        )


@dataclass(slots=True)
class ImageData:
    """Image/asset configuration (runtime, parsed from JSON).

    Attributes:
        id: Unique ID for the asset.
        name: Optional display name.
        image_path: Path to the image file (relative to the asset base
            when loaded from JSON).
        texture: Texture property configuration.
        type: The asset kind ("image" or "spritesheet").
        config_path: Path of the JSON configuration file (when loaded
            from disk).
    """

    id: str
    image_path: Path
    name: str | None = None
    texture: TextureProperty = field(default_factory=TextureProperty)
    type: Literal["image", "spritesheet"] = "image"
    config_path: Path | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        config_path: Path | str | None = None,
        texture_default: TextureProperty | None = None,
    ) -> ImageData:
        """Parse a JSON configuration dictionary into an ``ImageData``.

        Args:
            data: Asset configuration dictionary (from ``read_json`` /
                ``Assets.load_from_dict``).
            config_path: Overrides the config file path; when ``None``,
                uses the value in ``data``.
            texture_default: Default texture properties.

        Returns:
            A new ``ImageData`` instance.
        """
        asset_type = data.get("type") or "image"
        if asset_type not in ("image", "spritesheet"):
            asset_type = "image"

        resolved_path = config_path
        if resolved_path is None:
            resolved_path = data.get("config_path")
        if resolved_path is not None:
            resolved_path = Path(resolved_path)

        image_path = data.get("image_path")
        if isinstance(image_path, str):
            image_path = Path(image_path)

        return cls(
            id=str(data.get("id") or ""),
            name=data.get("name"),
            image_path=image_path,
            texture=TextureProperty.from_dict(
                data.get("texture", {}), defaults=texture_default
            ),
            type=asset_type,  # type: ignore[arg-type]
            config_path=resolved_path,
        )


@dataclass(slots=True)
class TextureData:
    """In-memory texture data (the Assets cache).

    Attributes:
        parent_id: ID of the main/parent asset (itself when standalone).
        texture: GPU texture object (backend-specific, satisfies the Texture Protocol).
        source_rect: The specific texture area (x, y, w, h).
        name: Optional display name for the texture.
    """

    parent_id: str
    texture: Texture
    source_rect: tuple[float, float, float, float]
    name: str | None = None


class TextureConfig(TypedDict, total=False):
    """Texture properties for a JSON-loaded image asset.

    All keys are optional; the runtime defaults live on
    :class:`TextureProperty`.

    Attributes:
        filter: Texture filter mode ("nearest" or "linear").
        wrap: Texture wrap mode ("repeat", "clamp", or "mirror").
        mipmap: Whether to generate mipmaps.
        srgb: Whether to use the sRGB color space.
        premultiply_alpha: Whether to pre-multiply the alpha channel.
        color_key: Color replaced with transparency on load.
    """

    filter: Literal["nearest", "linear"]
    wrap: Literal["repeat", "clamp", "mirror"]
    mipmap: bool
    srgb: bool
    premultiply_alpha: bool
    color_key: ColorType


class ImageConfig(TypedDict, total=False):
    """JSON configuration for a single image asset.

    Attributes:
        id: Unique ID for the asset.
        name: Optional display name.
        image_path: Path to the image file (relative to the asset base).
        texture: Texture property configuration.
        config_path: Path of the JSON configuration file (injected by
            ``Assets`` when loading from disk).
        type: The asset kind (always "image").
    """

    id: Required[str]
    name: str | None
    image_path: Required[str]
    texture: TextureConfig
    config_path: Path | str
    type: Literal["image"]


class _RegionType(TypedDict, total=True):
    """A named spritesheet region.

    Attributes:
        name: Unique name of the region within the spritesheet.
        rect: Region rectangle (x, y, w, h).
    """

    name: Required[str]
    rect: Required[RectType]


class SpriteSheetConfig(ImageConfig):
    """JSON configuration for a spritesheet asset.

    Attributes:
        regions: Named sub-rectangles, either a mapping of names to
            rectangles or a list of ``{"name": ..., "rect": ...}``
            entries.
        type: The asset kind (always "spritesheet").

    See Also:
        :class:`ImageConfig`: Inherited keys (``id``, ``name``,
        ``image_path``, ``texture``).
    """

    regions: Required[dict[str, RectType] | list[_RegionType]]
    type: Literal["spritesheet"]  # pyrefly: ignore [bad-typed-dict-key]


__all__ = [
    "ImageConfig",
    "ImageData",
    "ShapeKey",
    "ShapedText",
    "SpriteSheetConfig",
    "TemplateText",
    "TextureConfig",
    "TextureData",
    "TextureProperty",
]
