"""Backend-neutral texture configuration and atlas packing data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

from .schemas import ImageConfig, SpriteSheetConfig, TextureConfig, TextureProperty

if TYPE_CHECKING:
    from plyunit.backends.integrations import Assets, Image, ImageProcessor
    from plyunit.backends.ports import IAssets, IImageProcessor, ImageHandle

__all__ = (
    "Assets",
    "IAssets",
    "IImageProcessor",
    "Image",
    "ImageConfig",
    "ImageHandle",
    "ImageProcessor",
    "SpriteSheetConfig",
    "TextureConfig",
    "TextureProperty",
)

__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Assets": "plyunit.backends.integrations",
        "Image": "plyunit.backends.integrations",
        "ImageProcessor": "plyunit.backends.integrations",
        "IAssets": "plyunit.backends.ports",
        "IImageProcessor": "plyunit.backends.ports",
        "ImageHandle": "plyunit.backends.ports",
    },
    global_dict=globals(),
    all_exports=__all__,
)
