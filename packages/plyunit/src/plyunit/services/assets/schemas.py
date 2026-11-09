"""Backend-neutral image and spritesheet configuration schemas."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Required, TypedDict, cast

from plyunit._enums import TextureFilter, TextureWrap
from plyunit.core.types import ColorType, RectType


class TextureConfig(TypedDict, total=False):
    """Texture properties for a JSON-loaded image asset.

    All keys are optional; the runtime defaults live on
    :class:`TextureProperty`.

    Attributes:
        filter: Texture filter mode ("nearest", "linear", or "trilinear").
        wrap: Texture wrap mode ("repeat", "clamp", "mirror", or "mirror_repeat").
        mipmap: Whether to generate mipmaps.
        srgb: Whether to use the sRGB color space.
        premultiply_alpha: Whether to pre-multiply the alpha channel.
        color_key: Color replaced with transparency on load.
    """

    filter: Literal["nearest", "linear", "trilinear"]
    wrap: Literal["repeat", "clamp", "mirror", "mirror_repeat"]
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


@dataclass(slots=True)
class TextureProperty:
    """Texture property configuration (runtime).

    Attributes:
        filter: Texture filter mode ("nearest", "linear", or "trilinear").
        wrap: Texture wrap mode ("repeat", "clamp", "mirror", or "mirror_repeat").
        mipmap: Whether to generate mipmaps.
        srgb: Whether to use the sRGB color space.
        premultiply_alpha: Whether to pre-multiply the alpha channel.
        color_key: Color replaced with transparency on load.
    """

    filter: TextureFilter = TextureFilter.NEAREST
    wrap: TextureWrap = TextureWrap.CLAMP
    mipmap: bool = False
    srgb: bool = True
    premultiply_alpha: bool = False
    color_key: ColorType = field(default_factory=lambda: (0, 0, 0, 255))

    @classmethod
    def from_dict(
        cls, data: TextureConfig, *, default: TextureProperty | None = None
    ) -> TextureProperty:
        """Build settings, overriding defaults only for supplied keys.

        Args:
            data: JSON texture settings.
            default: Settings to inherit for omitted keys.

        Returns:
            An independent settings object; neither input is modified.

        Raises:
            ValueError: If a filter, wrap mode, or color key is invalid.
        """
        base = replace(default) if default is not None else cls()
        if "filter" in data:
            mode = TextureFilter.get(data["filter"])
            if mode is None:
                raise ValueError(f"Unknown texture filter: {data['filter']!r}")
            base.filter = mode
        if "wrap" in data:
            mode = TextureWrap.get(data["wrap"])
            if mode is None:
                raise ValueError(f"Unknown texture wrap: {data['wrap']!r}")
            base.wrap = mode
        if "mipmap" in data:
            base.mipmap = bool(data["mipmap"])
        if "srgb" in data:
            base.srgb = bool(data["srgb"])
        if "premultiply_alpha" in data:
            base.premultiply_alpha = bool(data["premultiply_alpha"])
        if "color_key" in data:
            color_key = data["color_key"]
            if (
                not isinstance(color_key, (list, tuple))
                or len(color_key) != 4
                or any(
                    not isinstance(channel, int) or not 0 <= channel <= 255
                    for channel in color_key
                )
            ):
                raise ValueError("Texture color_key must contain four RGBA bytes")
            base.color_key = tuple(color_key)
        return base

    def to_dict(self) -> TextureConfig:
        """Serialize the settings into backend-neutral JSON-compatible values."""
        return TextureConfig(
            filter=cast(
                Literal["nearest", "linear", "trilinear"], self.filter.name.lower()
            ),
            wrap=cast(
                Literal["repeat", "clamp", "mirror", "mirror_repeat"],
                self.wrap.name.lower(),
            ),
            mipmap=self.mipmap,
            srgb=self.srgb,
            premultiply_alpha=self.premultiply_alpha,
            color_key=self.color_key,
        )
