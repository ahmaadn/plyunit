"""Port (hexagonal architecture) for the Assets service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from plyunit.backends.ports._unit import IServiceUnit
from plyunit.rendering.enum import Layer

if TYPE_CHECKING:
    from plyunit.core.types import ColorType, PosType, RectType, Vec2Type
    from plyunit.services.assets.schemas import (
        ImageConfig,
        SpriteSheetConfig,
        TextureProperty,
    )

    from .handler import ImageHandle, Texture2DHandle


__all__ = ("IAssets", "IImageProcessor", "ResizeMode")

type ResizeMode = Literal["bilinear", "nn", "canvas"]


@runtime_checkable
class IImageProcessor(Protocol):
    """Contract for creating, converting and editing CPU-side images."""

    def load_image(self, path: str | Path) -> ImageHandle:
        """Decode an image file."""
        ...

    def load_image_from_memory(self, data: bytes, file_type: str) -> ImageHandle:
        """Decode an encoded image held in memory.

        Args:
            data: Encoded bytes (PNG, JPG, ...).
            file_type: Extension that names the format, e.g. ``".png"``.
        """
        ...

    def load_image_from_texture(self, texture: Texture2DHandle) -> ImageHandle:
        """Read the WHOLE GPU texture behind ``texture`` back into an image.

        A region handle reads its parent's entire texture; crop to
        ``texture.source_rect`` afterwards if only the region is wanted.
        """
        ...

    def gen_image_color(
        self, width: int, height: int, color: ColorType = (0, 0, 0, 0)
    ) -> ImageHandle:
        """Create a ``width x height`` image filled with a solid color."""
        ...

    def copy_image(self, image: ImageHandle) -> ImageHandle:
        """Return an independent copy of ``image``."""
        ...

    def unload_image(self, image: ImageHandle | None) -> None:
        """Release an image (no-op for ``None``)."""
        ...

    def is_image_valid(self, image: ImageHandle) -> bool:
        """Return ``True`` if decoding/creation produced usable pixels."""
        ...

    def get_color(self, image: ImageHandle, x: int, y: int) -> ColorType:
        """Return the RGBA color at pixel ``(x, y)``."""
        ...

    def get_alpha_border(self, image: ImageHandle, threshold: float) -> RectType:
        """Return the bounding box of pixels with alpha >= ``threshold``."""
        ...

    def blit(self, dst: ImageHandle, src: ImageHandle, pos: tuple[int, int]) -> None:
        """Blit ``src`` onto ``dst`` at ``pos`` without scaling."""
        ...

    def transform(
        self,
        image: ImageHandle,
        *,
        crop_rect: RectType | None = None,
        resize: tuple[int, int] | None = None,
        resize_mode: ResizeMode = "bilinear",
        canvas_offset: tuple[int, int] = (0, 0),
        canvas_fill: ColorType | None = None,
        flip_h: bool = False,
        flip_v: bool = False,
        rotate_deg: int = 0,
        to_pot: bool = False,
    ) -> None:
        """Apply geometric transforms, in the order of the parameters below.

        Order: crop -> resize -> flip_h -> flip_v -> rotate -> to_pot.

        Args:
            image: Image to edit in place.
            crop_rect: ``(x, y, w, h)`` region to keep.
            resize: ``(width, height)`` target size.
            resize_mode: ``"bilinear"``, ``"nn"`` (nearest) or ``"canvas"``
                (resize the canvas without scaling pixels).
            canvas_offset: Where the old pixels land when
                ``resize_mode="canvas"``.
            canvas_fill: Fill color for new canvas area / POT padding
                (``None`` = fully transparent).
            flip_h: Mirror horizontally.
            flip_v: Mirror vertically.
            rotate_deg: Rotation in degrees (90 / -90 / 270 are lossless).
            to_pot: Pad the canvas up to power-of-two dimensions.
        """
        ...

    def apply_filters(
        self,
        image: ImageHandle,
        *,
        replace_color: tuple[ColorType, ColorType] | None = None,
        tint: ColorType | None = None,
        brightness: int = 0,
        contrast: int = 0,
        invert: bool = False,
        grayscale: bool = False,
        blur: int = 0,
    ) -> None:
        """Apply color adjustments, in the order of the parameters below.

        Order: replace_color -> tint -> invert -> brightness -> contrast ->
        grayscale -> blur.

        Args:
            image: Image to edit in place.
            replace_color: ``(old_color, new_color)`` pair.
            tint: RGBA tint multiplied into every pixel.
            brightness: Brightness delta, -255..255.
            contrast: Contrast delta, -100..100.
            invert: Invert the colors.
            grayscale: Convert to grayscale.
            blur: Gaussian blur radius (0 = off).
        """
        ...

    def apply_alpha(
        self,
        image: ImageHandle,
        *,
        premultiply: bool = False,
        clear_threshold: float | None = None,
        clear_color: ColorType | None = None,
        crop_threshold: float | None = None,
        mask_image: ImageHandle | None = None,
    ) -> None:
        """Apply alpha-channel operations, in the order of the parameters below.

        Order: premultiply -> clear -> crop -> mask.

        Args:
            image: Image to edit in place.
            premultiply: Pre-multiply color by alpha.
            clear_threshold: Pixels with alpha below this (0..1) are replaced
                by ``clear_color``.
            clear_color: Replacement color (``None`` = fully transparent).
            crop_threshold: Crop transparent borders (alpha below this 0..1).
            mask_image: Image whose luminance becomes the alpha channel.
        """
        ...


@runtime_checkable
class IAssets(IServiceUnit, Protocol):
    """Contract for loading, caching, atlas-packing and rendering textures."""

    @property
    def asset_base_path(self) -> Path:
        """Absolute base directory for all asset paths."""
        ...

    @property
    def all_assets(self) -> MappingProxyType[str, Texture2DHandle]:
        """Read-only view of all assets currently in the cache."""
        ...

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base path for the asset folder."""
        ...

    def set_default_texture(self, config: TextureProperty) -> None:
        """Set the default texture parameters used when an asset gives none."""
        ...

    def get_asset(self, key: str) -> Texture2DHandle:
        """Return the handle of an asset; raise ``KeyError`` if unknown.

        The handle carries everything about the asset: ``source_rect``,
        ``parent_id``, ``metadata`` (texture settings), size and format.
        """
        ...

    def get_config_path_for(self, asset_id: str) -> Path | None:
        """Return the JSON config path an asset was loaded from, if any."""
        ...

    def get_source_rect(self, asset_id: str) -> RectType | None:
        """Return the source rect of an asset, or ``None`` if unknown."""
        ...

    def get_region_parent(self, asset_id: str) -> str:
        """Return the parent spritesheet ID, or ``asset_id`` if not a region."""
        ...

    def __getitem__(self, key: str) -> Texture2DHandle:
        """Shorthand for :meth:`get_asset`."""
        ...

    def is_valid(self, asset_id: str) -> bool:
        """Return ``True`` if the asset exists and its GPU texture is valid."""
        ...

    def load_asset(self, path: str, *, asset_id: str | None = None) -> None:
        """Load an image or JSON config relative to the base path."""
        ...

    def load_spritesheet(
        self, config_path: str, *, asset_id: str | None = None
    ) -> None:
        """Load a spritesheet from its JSON configuration file."""
        ...

    def load_from_dict(
        self,
        data: ImageConfig | SpriteSheetConfig | Mapping[str, Any],
        *,
        asset_id: str | None = None,
    ) -> None:
        """Load an image or spritesheet from a config mapping."""
        ...

    def load_folder(
        self,
        path: str,
        *,
        allow_extensions: list[str] | None = None,
    ) -> None:
        """Load every config and standalone image inside a folder."""
        ...

    def load_from_memory(
        self,
        asset_id: str,
        data: bytes,
        file_type: str,
        *,
        texture: TextureProperty | None = None,
    ) -> None:
        """Create an asset from encoded image bytes (embedded, downloaded...).

        Args:
            asset_id: Unique ID in the cache.
            data: Encoded bytes (PNG, JPG, ...).
            file_type: Extension naming the format, e.g. ``".png"``.
            texture: Texture parameters; ``None`` uses the defaults.

        Raises:
            ValueError: If the bytes cannot be decoded.
        """
        ...

    def load_from_image(
        self,
        asset_id: str,
        image: ImageHandle,
        *,
        texture: TextureProperty | None = None,
        take_ownership: bool = False,
    ) -> None:
        """Upload a CPU image (see ``IImageProcessor``) as a GPU texture asset.

        The pixels are uploaded as-is: ``color_key`` and ``premultiply_alpha``
        are NOT applied (edit the image with ``IImageProcessor`` first).
        Filter, wrap and mipmap settings are applied. Must run on the main
        thread, which makes this the upload step of staged loading.

        Args:
            asset_id: Unique ID in the cache.
            image: Source image.
            texture: Texture parameters; ``None`` uses the defaults.
            take_ownership: If ``True`` the image is unloaded after upload;
                otherwise the caller keeps and must release it.

        Raises:
            ValueError: If the image is not valid.
        """
        ...

    def create_solid_color(
        self, asset_id: str, width: int, height: int, color: ColorType
    ) -> None:
        """Create a ``width x height`` single-color texture asset.

        Raises:
            ValueError: If ``width`` or ``height`` is not positive.
        """
        ...

    def store_texture(self, asset_id: str, texture: Texture2DHandle) -> None:
        """Store an already-created GPU texture in the cache.

        The caller transfers ownership of a standalone root texture to the
        cache. Its identity and rectangle are replaced without modifying the
        supplied handle. Regions and borrowed render-target attachments cannot
        transfer ownership. Re-storing the same resource under the same ID is
        safe; assigning a second owner ID for it raises ``ValueError``.
        """
        ...

    def store_textures(self, textures: Mapping[str, Texture2DHandle]) -> None:
        """Store many GPU textures in the cache at once."""
        ...

    def copy_image(self, asset_id: str) -> ImageHandle:
        """Read an asset (its region only) back into a new CPU image.

        The caller owns the result and must release it with
        ``IImageProcessor.unload_image``.

        Raises:
            KeyError: If the asset is unknown.
        """
        ...

    def update_from_image(self, asset_id: str, image: ImageHandle) -> None:
        """Re-upload the pixels of an asset (its region only) from ``image``.

        Works on atlas and spritesheet regions too. Mipmaps are not rebuilt.

        Raises:
            KeyError: If the asset is unknown.
            ValueError: If the image size or pixel format does not match.
        """
        ...

    def unload_asset(self, asset_id: str) -> None:
        """Remove an asset and its logical regions, releasing only owned VRAM.

        A packed spritesheet retains its frame ownership; unloading the sheet
        removes its frames without releasing the shared atlas page.
        """
        ...

    def clear_all(self) -> None:
        """Unload every asset and clear all configuration data."""
        ...

    def build_texture_atlas(
        self,
        asset_ids: Sequence[str] | None = None,
        *,
        atlas_id: str = "atlas",
        max_size: int = 2048,
        padding: int = 2,
    ) -> list[str]:
        """Pack loaded assets into atlas pages and return the page IDs.

        Existing IDs resolve to new region handles afterward. Handles obtained
        before packing are stale; resolve their IDs again. Page composition
        failure leaves the original cache and GPU resources unchanged.
        """
        ...

    def render(
        self,
        asset_id: str,
        *,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        pos: PosType = (0.0, 0.0),
        tint: ColorType = (255, 255, 255, 255),
        rotation: float = 0.0,
        scale: float = 1.0,
        source: RectType | None = None,
        dest: RectType | None = None,
        origin: Vec2Type = (0.0, 0.0),
    ) -> None:
        """Render an asset through the renderer."""
        ...
