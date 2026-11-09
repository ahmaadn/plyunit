"""Backend-neutral texture configuration and atlas packing data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .schemas import ImageConfig, SpriteSheetConfig, TextureConfig, TextureProperty

if TYPE_CHECKING:
    from plyunit.backends.integrations import Assets, Image, ImageProcessor

__all__ = (
    "Assets",
    "Image",
    "ImageConfig",
    "ImageProcessor",
    "SpriteSheetConfig",
    "TextureConfig",
    "TextureProperty",
)


def __getattr__(name: str):
    if name not in {"Assets", "Image", "ImageProcessor"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends import integrations

    value = getattr(integrations, name)
    globals()[name] = value
    return value
