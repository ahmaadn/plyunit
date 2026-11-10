"""Raylib implementation of texture assets and CPU image processing."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pyray as pr
import raylib as rl

from plyunit._constants import DEFAULT_IMAGE_EXTENSIONS
from plyunit._enums import TextureFilter, TextureWrap
from plyunit.backends.ports.assets import IImageProcessor, ResizeMode
from plyunit.core.types import ColorType, PosType, RectType, Vec2Type
from plyunit.core.units import ServiceUnit
from plyunit.rendering.enum import Layer
from plyunit.services.assets.atlas import pack_shelf
from plyunit.services.assets.schemas import TextureProperty
from plyunit.utils.io import read_json
from plyunit.utils.paths import resolve_config_resource, resolve_inside
from plyunit.utils.rects import full_rect, iter_region_rects, shift_rect

from .handler import Image, Texture2D
from .utils import create_rect, tuple2color

if TYPE_CHECKING:
    from plyunit.services.assets.atlas import AtlasPage, AtlasPlacement
    from plyunit.services.assets.schemas import (
        ImageConfig,
        SpriteSheetConfig,
    )

__all__ = ("Assets", "ImageProcessor")

logger = logging.getLogger(__name__)

FILTER_MODE_MAP: Mapping[TextureFilter, int] = {
    TextureFilter.NEAREST: rl.TEXTURE_FILTER_POINT,
    TextureFilter.LINEAR: rl.TEXTURE_FILTER_BILINEAR,
    TextureFilter.TRILINEAR: rl.TEXTURE_FILTER_TRILINEAR,
}

WRAP_MODE_MAP: Mapping[TextureWrap, int] = {
    TextureWrap.CLAMP: rl.TEXTURE_WRAP_CLAMP,
    TextureWrap.MIRROR: rl.TEXTURE_WRAP_MIRROR_CLAMP,
    TextureWrap.REPEAT: rl.TEXTURE_WRAP_REPEAT,
    TextureWrap.MIRROR_REPEAT: rl.TEXTURE_WRAP_MIRROR_REPEAT,
}


TRANSPARENT: ColorType = (0, 0, 0, 0)
ROTATE_CW_DEG = 90
ROTATE_CCW_DEGS = (-90, 270)


class ImageProcessor(IImageProcessor):
    """Stateless raylib implementation of ``IImageProcessor``."""

    def load_image(self, path: str | Path) -> Image:
        """Decode an image file."""
        return Image(pr.load_image(str(path)))

    def load_image_from_memory(self, data: bytes, file_type: str) -> Image:
        """Decode an encoded image held in memory (``file_type`` like ``".png"``)."""
        # pyrefly: ignore[bad-argument-type]
        return Image(pr.load_image_from_memory(file_type, data, len(data)))

    def load_image_from_texture(self, texture: Texture2D) -> Image:
        """Read the whole GPU texture back into a CPU image (needs a window)."""
        return Image(pr.load_image_from_texture(texture.raw_texture))

    def gen_image_color(
        self, width: int, height: int, color: ColorType = TRANSPARENT
    ) -> Image:
        """Create a ``width x height`` image filled with a solid color."""
        if width <= 0 or height <= 0:
            raise ValueError(f"Image dimensions must be positive: {width}x{height}")
        return Image(pr.gen_image_color(int(width), int(height), tuple2color(color)))

    def copy_image(self, image: Image) -> Image:
        """Return an independent copy of ``image``."""
        return Image(pr.image_copy(image.raw_image))

    def unload_image(self, image: Image | None) -> None:
        """Release an image (no-op for ``None``)."""
        if image is not None:
            pr.unload_image(image.raw_image)

    def is_image_valid(self, image: Image) -> bool:
        """Return ``True`` if the image holds usable pixels."""
        return bool(pr.is_image_valid(image.raw_image))

    def get_color(self, image: Image, x: int, y: int) -> ColorType:
        """Return the RGBA color at pixel ``(x, y)``."""
        c = pr.get_image_color(image.raw_image, int(x), int(y))
        return c.r, c.g, c.b, c.a

    def get_alpha_border(self, image: Image, threshold: float) -> RectType:
        """Return the bounding box of pixels with alpha >= ``threshold``."""
        r = pr.get_image_alpha_border(image.raw_image, float(threshold))
        return float(r.x), float(r.y), float(r.width), float(r.height)

    def blit(self, dst: Image, src: Image, pos: tuple[int, int]) -> None:
        """Blit ``src`` onto ``dst`` at ``pos`` without scaling."""
        source = src.raw_image
        pr.image_draw_image_rec(
            dst.raw_image,
            source,
            pr.Rectangle(0, 0, source.width, source.height),
            pos,
            pr.WHITE,
        )

    def transform(
        self,
        image: Image,
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
        """Apply geometric transforms in the documented order."""
        raw = image.raw_image
        if crop_rect is not None:
            pr.image_crop(raw, create_rect(crop_rect))
        if resize is not None:
            self._resize(raw, resize, resize_mode, canvas_offset, canvas_fill)
        if flip_h:
            pr.image_flip_horizontal(raw)
        if flip_v:
            pr.image_flip_vertical(raw)
        if rotate_deg != 0:
            self._rotate(raw, rotate_deg)
        if to_pot:
            pr.image_to_pot(raw, tuple2color(canvas_fill))

    def apply_filters(
        self,
        image: Image,
        *,
        replace_color: tuple[ColorType, ColorType] | None = None,
        tint: ColorType | None = None,
        brightness: int = 0,
        contrast: int = 0,
        invert: bool = False,
        grayscale: bool = False,
        blur: int = 0,
    ) -> None:
        """Apply color adjustments in the documented order."""
        raw = image.raw_image
        if replace_color is not None:
            old, new = replace_color
            pr.image_color_replace(raw, tuple2color(old), tuple2color(new))
        if tint is not None:
            pr.image_color_tint(raw, tuple2color(tint))
        if invert:
            pr.image_color_invert(raw)
        if brightness != 0:
            pr.image_color_brightness(raw, brightness)
        if contrast != 0:
            pr.image_color_contrast(raw, contrast)
        if grayscale:
            pr.image_color_grayscale(raw)
        if blur > 0:
            pr.image_blur_gaussian(raw, blur)

    def apply_alpha(
        self,
        image: Image,
        *,
        premultiply: bool = False,
        clear_threshold: float | None = None,
        clear_color: ColorType | None = None,
        crop_threshold: float | None = None,
        mask_image: Image | None = None,
    ) -> None:
        """Apply alpha-channel operations in the documented order."""
        raw = image.raw_image
        if premultiply:
            pr.image_alpha_premultiply(raw)
        if clear_threshold is not None:
            pr.image_alpha_clear(raw, tuple2color(clear_color), float(clear_threshold))
        if crop_threshold is not None:
            pr.image_alpha_crop(raw, float(crop_threshold))
        if mask_image is not None:
            pr.image_alpha_mask(raw, mask_image.raw_image)

    @staticmethod
    def _resize(
        raw: pr.Image,
        size: tuple[int, int],
        mode: ResizeMode,
        canvas_offset: tuple[int, int],
        canvas_fill: ColorType | None,
    ) -> None:
        """Resize ``raw`` according to ``mode``."""
        width, height = size
        if width <= 0 or height <= 0:
            raise ValueError(f"Image dimensions must be positive: {width}x{height}")
        if mode not in {"bilinear", "nn", "canvas"}:
            raise ValueError(f"Unknown image resize mode: {mode!r}")
        if mode == "nn":
            pr.image_resize_nn(raw, width, height)
        elif mode == "canvas":
            offset_x, offset_y = canvas_offset
            pr.image_resize_canvas(
                raw, width, height, offset_x, offset_y, tuple2color(canvas_fill)
            )
        else:
            pr.image_resize(raw, width, height)

    @staticmethod
    def _rotate(raw: pr.Image, degrees: int) -> None:
        """Rotate; quarter turns use the lossless raylib routines."""
        degrees %= 360
        if degrees == ROTATE_CW_DEG:
            pr.image_rotate_cw(raw)
        elif degrees in ROTATE_CCW_DEGS:
            pr.image_rotate_ccw(raw)
        elif degrees != 0:
            pr.image_rotate(raw, degrees)


class Assets(ServiceUnit):
    """Raylib-backed texture asset manager (implements ``IAssets``).

    Attributes:
        _textures: Primary cache of id -> :class:`Texture2D` (roots and
            regions alike).
        _regions: Mapping of ``parent_id`` -> the set of ``region_id``
            values owned by the spritesheet (or atlas page).
        _config_paths: ``asset_id`` -> the JSON file it was loaded from.
        _atlases: Atlas page IDs produced by :meth:`build_texture_atlas`
            (so they are not re-packed).
        _base: Absolute, symlink-free base directory for all asset paths.
        _texture_default: Default parameters for assets that give none.
        _images: The :class:`ImageProcessor` used for all CPU-side images.
    """

    def __init__(
        self,
        asset_base_path: Path = Path("./"),
        *,
        image_processor: ImageProcessor | None = None,
        texture_default: TextureProperty | None = None,
    ) -> None:
        """Initialize the asset manager.

        Args:
            asset_base_path: Base path (relative or absolute) of the asset
                folder; resolved to an absolute path immediately.
            image_processor: CPU image port; ``None`` uses the raylib adapter.
            texture_default: Default texture parameters; ``None`` uses
                ``TextureProperty()``.
        """
        super().__init__(name="Assets", tags={"service", "asset_manager", "assets"})

        self._textures: dict[str, Texture2D] = {}
        self._texture_owners: dict[int, str] = {}
        self._regions: dict[str, set[str]] = {}
        self._sheet_regions: dict[str, set[str]] = {}
        self._region_sheets: dict[str, str] = {}
        self._config_paths: dict[str, Path] = {}
        self._atlases: set[str] = set()
        self._base: Path = Path(asset_base_path).resolve()

        self._texture_default = replace(texture_default or TextureProperty())
        self._images: ImageProcessor = (
            image_processor if image_processor is not None else ImageProcessor()
        )

    @property
    def asset_base_path(self) -> Path:
        """Absolute base directory for all asset paths."""
        return self._base

    @property
    def all_assets(self) -> MappingProxyType[str, Texture2D]:
        """Read-only view of all assets currently in the cache."""
        return MappingProxyType(self._textures)

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base path for the asset folder (resolved immediately)."""
        self._base = Path(path).resolve()
        logger.info(f"Path dasar aset diubah menjadi: {self._base}")

    def set_default_texture(self, config: TextureProperty) -> None:
        """Set the default texture parameters used when an asset gives none."""
        self._check_texture_params(config)
        self._texture_default = replace(config)
        logger.info(f"Default texture parameters updated: {config}")

    def get_asset(self, key: str) -> Texture2D:
        """Get the handle of an asset by ID.

        Raises:
            KeyError: If the asset is not found.
        """
        try:
            return self._textures[key]
        except KeyError:
            logger.error(f"Aset dengan ID '{key}' tidak ditemukan dalam cache")
            raise KeyError(f"Aset dengan ID '{key}' tidak ditemukan") from None

    def get_config_path_for(self, asset_id: str) -> Path | None:
        """Return the JSON config path an asset was loaded from, or ``None``."""
        return self._config_paths.get(asset_id)

    def get_source_rect(self, asset_id: str) -> RectType | None:
        """Get the source rect of an asset, or ``None`` if unknown."""
        handle = self._textures.get(asset_id)
        return handle.source_rect if handle is not None else None

    def get_region_parent(self, asset_id: str) -> str:
        """Get the parent spritesheet ID, or ``asset_id`` if not a region."""
        handle = self._textures.get(asset_id)
        return (handle.parent_id or asset_id) if handle is not None else asset_id

    def __getitem__(self, key: str) -> Texture2D:
        """Shorthand for :meth:`get_asset`."""
        return self.get_asset(key)

    def is_valid(self, asset_id: str) -> bool:
        """Return ``True`` if the asset exists and its GPU texture is valid."""
        handle = self._textures.get(asset_id)
        return handle is not None and bool(pr.is_texture_valid(handle.raw_texture))

    def clear_all(self) -> None:
        """Unload all assets and clear configuration data."""
        for asset_id in list(self._textures):
            self.unload_asset(asset_id)
        self._texture_owners.clear()
        self._regions.clear()
        self._sheet_regions.clear()
        self._region_sheets.clear()
        self._config_paths.clear()
        self._atlases.clear()
        logger.info("Semua aset di-unload dan cache dibersihkan.")

    def destroy(self) -> None:
        """Unload all textures still stored in the cache."""
        self.clear_all()
        super().destroy()

    def unload_asset(self, asset_id: str) -> None:
        """Remove an asset and its logical regions, releasing only owned VRAM.

        Spritesheet frames remain logically owned by their sheet after atlas
        packing. Removing a packed sheet therefore removes its frames without
        releasing the atlas page shared by other assets.
        """
        handle = self._textures.get(asset_id)
        if handle is None:
            return
        children = set(self._sheet_regions.get(asset_id, ()))
        if handle._is_root:
            children.update(self._regions.get(asset_id, ()))
        for region_id in children:
            self.unload_asset(region_id)

        self._textures.pop(asset_id, None)
        self._config_paths.pop(asset_id, None)
        self._sheet_regions.pop(asset_id, None)
        sheet_id = self._region_sheets.pop(asset_id, None)
        if sheet_id is not None:
            self._sheet_regions.get(sheet_id, set()).discard(asset_id)
        if handle._is_root:
            self._texture_owners.pop(self._texture_key(handle.raw_texture), None)
            self._regions.pop(asset_id, None)
            self._atlases.discard(asset_id)
            try:
                self._unload_texture(handle.raw_texture)
            except Exception:
                logger.warning("Failed to unload texture '%s'", asset_id, exc_info=True)
        else:
            self._regions.get(handle.parent_id, set()).discard(asset_id)

    @staticmethod
    def _check_asset_id(asset_id: str) -> None:
        """Reject asset IDs that cannot identify a cache entry."""
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("Asset IDs must be non-empty strings")

    @staticmethod
    def _texture_key(raw_texture: pr.Texture) -> int:
        """Identify GPU ownership even when raylib returns another struct wrapper."""
        return int(raw_texture.id)

    def _put(self, handle: Texture2D) -> None:
        """Cache a handle without creating duplicate GPU owners."""
        asset_id = handle.texture_id
        self._check_asset_id(asset_id)
        existing = self._textures.get(asset_id)
        texture_key = self._texture_key(handle.raw_texture)
        if handle._is_root:
            if not handle._owns_texture:
                raise ValueError("A borrowed texture cannot own a cache entry")
            owner_id = self._texture_owners.get(texture_key)
            if owner_id is not None and owner_id != asset_id:
                raise ValueError(f"Texture is already owned by asset '{owner_id}'")
            if (
                existing is not None
                and existing._is_root
                and self._texture_key(existing.raw_texture) == texture_key
            ):
                self._textures[asset_id] = handle
                return
        else:
            parent = self._textures.get(handle.parent_id)
            if (
                parent is None
                or not parent._is_root
                or self._texture_key(parent.raw_texture) != texture_key
            ):
                raise ValueError(f"Region '{asset_id}' requires a live root owner")
        if existing is not None:
            self.unload_asset(asset_id)
        self._textures[asset_id] = handle
        if handle._is_root:
            self._texture_owners[texture_key] = asset_id
            self._regions.setdefault(asset_id, set())
        else:
            self._regions.setdefault(handle.parent_id, set()).add(asset_id)

    def store_texture(self, asset_id: str, texture: Texture2D) -> None:
        """Store an already-created GPU texture in the cache.

        The handle is re-identified as a root asset named ``asset_id`` that
        covers the whole texture. Used for staged loading and for textures
        baked from primitives (wrap a raw one with
        ``Texture2D.from_raw``). Raylib texture calls are NOT
        thread-safe — always call from the main thread.

        Raises:
            ValueError: If the texture is invalid, borrowed, or already owned
                by another asset ID.
            TypeError: If the texture is not a raylib ``Texture2D`` handle.
        """
        self._check_asset_id(asset_id)
        if texture is None:
            raise ValueError(f"Texture for asset '{asset_id}' must not be None")
        if not isinstance(texture, Texture2D):
            raise TypeError("Raylib assets require a Texture2D handle")
        if not texture._is_root or not texture._owns_texture:
            raise ValueError(
                "A borrowed texture cannot transfer ownership of its parent"
            )
        if not pr.is_texture_valid(texture.raw_texture):
            raise ValueError(f"Texture for asset '{asset_id}' is invalid")
        self._put(
            texture.derive(
                texture_id=asset_id,
                parent_id=asset_id,
                source_rect=full_rect(texture.width, texture.height),
            )
        )
        logger.debug(f"Texture untuk aset '{asset_id}' disimpan dari luar")

    def store_textures(self, textures: Mapping[str, Texture2D]) -> None:
        """Store many GPU textures at once; existing IDs are overwritten.

        Raises:
            ValueError: If any texture is ``None``.
        """
        for asset_id, texture in textures.items():
            if texture is None:
                raise ValueError(f"Texture for asset '{asset_id}' must not be None")
        for asset_id, texture in textures.items():
            self.store_texture(asset_id, texture)

    @staticmethod
    def _unload_texture(raw_texture: Any) -> None:
        """Unload a raw GPU texture from VRAM (no-op if ``None``)."""
        if raw_texture is not None:
            pr.unload_texture(raw_texture)

    @staticmethod
    def _check_texture_params(prop: TextureProperty) -> None:
        """Raise ``ValueError`` if the filter or wrap mode of ``prop`` is unknown."""
        if prop.filter not in FILTER_MODE_MAP:
            raise ValueError(f"Unknown texture filter: {prop.filter!r}")
        if prop.wrap not in WRAP_MODE_MAP:
            raise ValueError(f"Unknown texture wrap: {prop.wrap!r}")

    @classmethod
    def _apply_texture_params(cls, raw_texture: Any, prop: TextureProperty) -> None:
        """Apply filter and wrap mode of ``prop`` to a raw texture."""
        cls._check_texture_params(prop)
        pr.set_texture_filter(raw_texture, FILTER_MODE_MAP[prop.filter])
        pr.set_texture_wrap(raw_texture, WRAP_MODE_MAP[prop.wrap])

    def _upload(self, image: Image, asset_id: str, prop: TextureProperty) -> Texture2D:
        """Upload ``image`` to the GPU as a root handle named ``asset_id``."""
        self._check_asset_id(asset_id)
        self._check_texture_params(prop)
        prop = replace(prop)
        raw = pr.load_texture_from_image(image.raw_image)
        try:
            if not pr.is_texture_valid(raw):
                raise ValueError(f"Failed to upload texture for asset '{asset_id}'")
            if prop.mipmap:
                pr.gen_texture_mipmaps(raw)
            self._apply_texture_params(raw, prop)
            return Texture2D(
                raw_texture=raw,
                texture_id=asset_id,
                parent_id=asset_id,
                source_rect=full_rect(raw.width, raw.height),
                metadata=prop,
            )
        except BaseException:
            self._unload_texture(raw)
            raise

    def _prepare_image(self, image: Image, prop: TextureProperty) -> None:
        """Replace the color key with transparency, then optionally premultiply."""
        self._images.apply_filters(image, replace_color=(prop.color_key, TRANSPARENT))
        if prop.premultiply_alpha:
            self._images.apply_alpha(image, premultiply=True)

    def _texture_from_owned_image(
        self,
        image: Image,
        asset_id: str,
        prop: TextureProperty,
        *,
        source: str,
        regions: Sequence[tuple[str, RectType]] = (),
    ) -> Texture2D:
        """Validate, prepare and upload ``image``, then unload it.

        Raises:
            ValueError: If ``image`` could not be decoded.
        """
        try:
            if not self._images.is_image_valid(image):
                raise ValueError(f"Gagal decode gambar '{source}'")
            self._validate_region_bounds(regions, image.width, image.height)
            self._prepare_image(image, prop)
            return self._upload(image, asset_id, prop)
        finally:
            self._images.unload_image(image)

    def _texture_from_file(
        self,
        path: Path,
        asset_id: str,
        prop: TextureProperty,
        *,
        regions: Sequence[tuple[str, RectType]] = (),
    ) -> Texture2D:
        """Decode an image file into a root texture handle using ``prop``."""
        image = self._images.load_image(path)
        return self._texture_from_owned_image(
            image, asset_id, prop, source=path.name, regions=regions
        )

    def load_asset(self, path: str, *, asset_id: str | None = None) -> None:
        """Load an image or JSON config relative to the base path.

        Raises:
            FileNotFoundError: If the file is not found.
            ValueError: If the asset ID cannot be determined or the path
                escapes the base path.
        """
        asset_path = resolve_inside(self._base, path)
        logger.debug(f"Memproses pemuatan aset: {asset_path}")

        if asset_path.suffix.lower() == ".json":
            self.load_from_dict(self._read_config(asset_path), asset_id=asset_id)
        else:
            self._load_image_asset(asset_path, asset_id=asset_id)

    def load_spritesheet(
        self, config_path: str, *, asset_id: str | None = None
    ) -> None:
        """Load a spritesheet from its JSON configuration file.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can be
                determined, or a region is malformed.
        """
        logger.debug(f"Memuat spritesheet dari {config_path}")
        config = self._read_config(resolve_inside(self._base, config_path))
        config.setdefault("type", "spritesheet")
        self.load_from_dict(config, asset_id=asset_id)

    def load_from_dict(
        self,
        data: ImageConfig | SpriteSheetConfig | Mapping[str, Any],
        *,
        asset_id: str | None = None,
    ) -> None:
        """Load an image or spritesheet from a config mapping.

        For type ``"spritesheet"`` the regions are registered as handles
        sharing the sheet's texture. Texture settings come from the optional
        ``"texture"`` entry, falling back to the manager's defaults.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can be
                determined, or a region is malformed.
        """
        self._load_config(dict(data), asset_id=asset_id)

    def _read_config(self, config_file: Path) -> dict[str, Any]:
        """Read a JSON config and attach its own path as ``config_path``."""
        config_file = resolve_inside(self._base, config_file)
        config = read_json(str(config_file))
        if not isinstance(config, dict):
            raise ValueError(f"Asset config '{config_file.name}' must be an object")
        config["config_path"] = config_file
        return config

    def _load_config(self, raw: dict[str, Any], *, asset_id: str | None) -> Path:
        """Load an image/spritesheet from a config dict.

        Returns:
            The absolute path of the image file that was loaded.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can be
                determined, or a region is malformed.
        """
        config_path = raw.get("config_path")
        if config_path is not None:
            config_path = resolve_inside(self._base, config_path)
        if not raw.get("image_path"):
            name = Path(config_path).name if config_path else raw.get("id", "<dict>")
            raise ValueError(f"image_path is required in config '{name}'")

        resolved_id = asset_id or str(raw.get("id") or "")
        if not resolved_id.strip() and config_path is not None:
            resolved_id = Path(config_path).stem
        if not resolved_id.strip():
            raise ValueError(
                "Asset ID wajib ada (asset_id, data['id'], atau config_path)"
            )

        self._check_asset_id(resolved_id)
        kind = raw.get("type", "image")
        if kind not in {"image", "spritesheet"}:
            raise ValueError(f"Unknown asset config type: {kind!r}")
        regions = (
            list(iter_region_rects(raw.get("regions", {})))
            if kind == "spritesheet"
            else []
        )
        for region_id, _ in regions:
            if region_id == resolved_id:
                raise ValueError("A spritesheet region cannot use its sheet ID")
            if region_id in self._textures and region_id not in self._sheet_regions.get(
                resolved_id, set()
            ):
                raise ValueError(f"Region ID '{region_id}' is already in use")

        image_ref = str(raw["image_path"])
        if config_path is not None:
            image_path = resolve_config_resource(
                self._base, image_ref, Path(config_path)
            )
        else:
            image_path = resolve_inside(self._base, image_ref)

        if not image_path.is_file():
            message = (
                f"File gambar '{image_path.name}' tidak ada untuk aset '{resolved_id}'"
            )
            logger.error(message)
            raise FileNotFoundError(message)

        prop = TextureProperty.from_dict(
            raw.get("texture") or {}, default=self._texture_default
        )
        root = self._texture_from_file(image_path, resolved_id, prop, regions=regions)
        self._put(root)
        if config_path is not None:
            self._config_paths[resolved_id] = config_path

        if kind == "spritesheet":
            self._sheet_regions[resolved_id] = set()
            for region_id, rect in regions:
                self._put(
                    root.derive(
                        texture_id=region_id, parent_id=resolved_id, source_rect=rect
                    )
                )
                self._sheet_regions[resolved_id].add(region_id)
                self._region_sheets[region_id] = resolved_id
                if config_path is not None:
                    self._config_paths[region_id] = config_path
            logger.info(
                "Loaded spritesheet '%s' with %d regions", resolved_id, len(regions)
            )
        else:
            logger.info("Loaded asset '%s'", resolved_id)
        return image_path

    @staticmethod
    def _validate_region_bounds(
        regions: Sequence[tuple[str, RectType]], width: int, height: int
    ) -> None:
        """Reject regions that cannot describe pixels within the source image."""
        for region_id, (x, y, w, h) in regions:
            if (
                x < 0
                or y < 0
                or w <= 0
                or h <= 0
                or x + w > width
                or y + h > height
                or any(not float(value).is_integer() for value in (x, y, w, h))
            ):
                raise ValueError(
                    f"Region '{region_id}' is outside the image pixel bounds"
                )

    def _load_image_asset(
        self, asset_path: Path, *, asset_id: str | None = None
    ) -> None:
        """Load an image directly (no JSON) using the default parameters."""
        logger.debug(f"Memproses aset gambar langsung: {asset_path.name}")

        if not asset_path.is_file():
            raise FileNotFoundError(f"Image file not found: {asset_path}")
        resolved_id = asset_id or asset_path.stem
        self._check_asset_id(resolved_id)
        self._put(
            self._texture_from_file(asset_path, resolved_id, self._texture_default)
        )
        logger.info(f"Aset '{resolved_id}' berhasil dimuat")

    def load_folder(
        self,
        path: str,
        *,
        allow_extensions: list[str] | None = None,
    ) -> None:
        """Load all assets from a folder.

        JSON configs are loaded first; every remaining image that no config
        referenced is then loaded as a standalone asset.

        Raises:
            FileNotFoundError: If the folder does not exist.
        """
        extensions = {
            ext.lower()
            for ext in (
                DEFAULT_IMAGE_EXTENSIONS
                if allow_extensions is None
                else allow_extensions
            )
        }
        folder_path = resolve_inside(self._base, path)

        if not folder_path.is_dir():
            logger.error(f"Folder tidak ada: {folder_path}")
            raise FileNotFoundError(f"Folder tidak ada: {folder_path}")

        logger.info(f"Mulai memproses folder di path '{path}'")

        config_images = self._load_folder_configs(folder_path)
        self._load_folder_images(folder_path, extensions, config_images)

        logger.info(
            f"Folder berhasil diproses ({len(config_images)} aset dengan config dimuat)"
        )

    def _load_folder_configs(self, folder_path: Path) -> set[Path]:
        """Load folder JSON configs, skipping those without ``image_path``.

        Returns:
            The set of image file paths loaded through a config.

        Raises:
            FileNotFoundError: If the image file for a config is not found.
        """
        config_files = sorted(folder_path.glob("*.json"))
        logger.debug(f"Menemukan {len(config_files)} file konfigurasi")

        loaded_images: set[Path] = set()
        for config_file in config_files:
            try:
                config = self._read_config(config_file)
                if not config.get("image_path"):
                    logger.debug(
                        f"image_path is required in config '{config_file.name}'"
                    )
                    continue

                image_path = self._load_config(config, asset_id=None)
            except Exception as error:
                logger.error(f"Gagal memproses config '{config_file.name}': {error}")
                raise

            loaded_images.add(image_path)
            if image_path.parent != config_file.parent:
                logger.warning(
                    f"Disarankan file config '{config_file.name}' dan gambar "
                    f"{image_path.name!r} berada di folder yang sama."
                )
            logger.debug(
                f"Config diproses: {config_file.stem} (gambar: {image_path.name})"
            )

        return loaded_images

    def _load_folder_images(
        self,
        folder_path: Path,
        extensions: set[str],
        loaded_images: set[Path],
    ) -> None:
        """Load standalone images that no configuration file referenced."""
        count = 0
        for image_file in sorted(folder_path.iterdir()):
            if not image_file.is_file() or image_file.suffix.lower() not in extensions:
                continue

            image_path = resolve_inside(self._base, image_file)
            if image_path in loaded_images:
                continue

            try:
                logger.debug(f"Memproses gambar standalone: {image_path.stem}")
                self._load_image_asset(image_path)
                count += 1
            except Exception as error:
                logger.error(f"Gagal memproses gambar '{image_file.name}': {error}")
                raise

        if count > 0:
            logger.info(f"{count} gambar standalone dimuat dari '{folder_path}'")

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
            ValueError: If the bytes are empty or cannot be decoded.
        """
        self._check_asset_id(asset_id)
        if not data:
            raise ValueError(f"Image data for asset '{asset_id}' is empty")

        suffix = file_type if file_type.startswith(".") else f".{file_type}"
        image = self._images.load_image_from_memory(data, suffix.lower())
        handle = self._texture_from_owned_image(
            image,
            asset_id,
            texture or self._texture_default,
            source=f"memory:{asset_id}",
        )
        self._put(handle)
        logger.info(f"Aset '{asset_id}' berhasil dimuat dari memori")

    def load_from_image(
        self,
        asset_id: str,
        image: Image,
        *,
        texture: TextureProperty | None = None,
        take_ownership: bool = False,
    ) -> None:
        """Upload a CPU image as a GPU texture asset.

        The pixels are uploaded as-is: ``color_key`` and ``premultiply_alpha``
        are NOT applied (edit the image with the image processor first).
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
        try:
            if not self._images.is_image_valid(image):
                raise ValueError(f"Gambar untuk aset '{asset_id}' tidak valid")
            handle = self._upload(image, asset_id, texture or self._texture_default)
        finally:
            if take_ownership:
                self._images.unload_image(image)

        self._put(handle)
        logger.info(f"Aset '{asset_id}' berhasil dimuat dari image")

    def create_solid_color(
        self, asset_id: str, width: int, height: int, color: ColorType
    ) -> None:
        """Create a ``width x height`` single-color texture asset.

        Raises:
            ValueError: If ``width`` or ``height`` is not positive.
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"Ukuran harus > 0, dapat: {width}x{height}")
        image = self._images.gen_image_color(width, height, color)
        self.load_from_image(asset_id, image, take_ownership=True)

    def copy_image(self, asset_id: str) -> Image:
        """Read an asset (its region only) back into a new CPU image.

        The caller owns the result and must release it with the image
        processor's ``unload_image``.

        Raises:
            KeyError: If the asset is unknown.
        """
        handle = self.get_asset(asset_id)
        image = self._images.load_image_from_texture(handle)
        try:
            if not self._images.is_image_valid(image):
                raise ValueError(f"Failed to read image for asset '{asset_id}'")
            if handle.source_rect != full_rect(handle.width, handle.height):
                self._images.transform(image, crop_rect=handle.source_rect)
        except BaseException:
            self._images.unload_image(image)
            raise
        return image

    def update_from_image(self, asset_id: str, image: Image) -> None:
        """Re-upload the pixels of an asset (its region only) from ``image``.

        Works on atlas and spritesheet regions too. Mipmaps are not rebuilt.

        Raises:
            KeyError: If the asset is unknown.
            ValueError: If the image size or pixel format does not match.
        """
        handle = self.get_asset(asset_id)
        if not self._images.is_image_valid(image):
            raise ValueError(f"Image for asset '{asset_id}' is invalid")
        x, y, w, h = handle.source_rect
        if (image.width, image.height) != (int(w), int(h)):
            raise ValueError(
                f"Ukuran image {image.width}x{image.height} tidak sama dengan "
                f"aset '{asset_id}' ({int(w)}x{int(h)})"
            )
        if image.format_id != handle.format_id:
            raise ValueError(f"Format pixel image tidak sama dengan aset '{asset_id}'")

        # Assets is the raylib adapter, so ``Image.data`` (the pixels) is safe here.
        pr.update_texture_rec(
            handle.raw_texture, pr.Rectangle(x, y, w, h), image.raw_image.data
        )

    def build_texture_atlas(
        self,
        asset_ids: Sequence[str] | None = None,
        *,
        atlas_id: str = "atlas",
        max_size: int = 2048,
        padding: int = 2,
    ) -> list[str]:
        """Merge already-loaded assets into an in-memory texture atlas.

        Assets are shelf-packed into pages and each old asset ID is
        repointed to an atlas region (IDs do not change). Spritesheet
        regions and animation frames with a ``source_rect`` are remapped,
        and old textures are unloaded from the GPU. Purely optional, for
        render performance; nothing is written to disk.

        Args:
            asset_ids: Asset IDs to pack; ``None`` means all root assets
                not already in an atlas.
            atlas_id: Base ID of the atlas pages (``_2``, ``_3``, ... after
                the first page).
            max_size: Maximum side of one page; larger assets stay standalone.
            padding: Pixel spacing between assets (anti-bleeding).

        Returns:
            The created atlas page IDs (empty if nothing was eligible).

        Raises:
            KeyError: If any ID in ``asset_ids`` is not in the cache.
            ValueError: If ``max_size`` or ``padding`` is invalid.
        """
        self._check_asset_id(atlas_id)
        if max_size <= 0:
            raise ValueError(f"max_size must be positive: {max_size}")
        if padding < 0:
            raise ValueError(f"padding tidak boleh negatif, dapat: {padding}")

        entries = self._atlas_entries(self._collect_atlas_roots(asset_ids), max_size)
        if not entries:
            logger.warning("build_texture_atlas: tidak ada aset yang layak di-pack.")
            return []

        pages, placements = pack_shelf(entries, max_size=max_size, padding=padding)

        placements_by_page: defaultdict[int, list[tuple[str, AtlasPlacement]]] = (
            defaultdict(list)
        )
        for root_id, placement in placements.items():
            placements_by_page[placement.page].append((root_id, placement))

        page_ids: list[str] = []
        page_handles: list[Texture2D] = []
        try:
            for index, page in enumerate(pages):
                page_id = self._unique_atlas_id(atlas_id, index, page_ids)
                handle = self._compose_atlas_page(
                    page_id, page, placements_by_page[index]
                )
                page_ids.append(page_id)
                page_handles.append(handle)
        except BaseException:
            for handle in page_handles:
                self._unload_texture(handle.raw_texture)
            raise
        for handle in page_handles:
            self._put(handle)
            self._atlases.add(handle.texture_id)

        old_textures, delta_map, texture_map = self._repoint_to_atlas(
            placements, page_ids, page_handles
        )
        try:
            self._remap_animation_references(delta_map, texture_map)
        finally:
            for raw_texture in old_textures.values():
                self._unload_texture(raw_texture)

        logger.info(
            f"Texture atlas dibuat: {len(entries)} aset -> {len(pages)} halaman "
            f"({', '.join(f'{p.width}x{p.height}' for p in pages)}), "
            f"{len(old_textures)} texture lama di-unload."
        )
        return page_ids

    def _collect_atlas_roots(self, asset_ids: Sequence[str] | None) -> list[str]:
        """Collect the unique root asset IDs to pack into the atlas.

        Raises:
            KeyError: If any explicit ID is not in the cache.
        """
        if asset_ids is None:
            return [
                asset_id
                for asset_id, handle in self._textures.items()
                if handle._is_root and asset_id not in self._atlases
            ]

        roots: dict[str, None] = {}  # ordered, unique
        for asset_id in asset_ids:
            handle = self._textures.get(asset_id)
            if handle is None:
                raise KeyError(f"Aset dengan ID '{asset_id}' tidak ditemukan")
            root_id = handle.parent_id or asset_id
            if root_id in self._atlases:
                logger.debug(f"Aset '{asset_id}' sudah berada di atlas; dilewati.")
                continue
            roots[root_id] = None
        return list(roots)

    def _atlas_entries(
        self, roots: Sequence[str], max_size: int
    ) -> list[tuple[str, int, int]]:
        """Build ``(root_id, width, height)`` entries eligible for packing.

        Assets with invalid dimensions or larger than ``max_size`` are skipped.
        """
        entries: list[tuple[str, int, int]] = []
        for root_id in roots:
            handle = self._textures[root_id]
            width, height = handle.width, handle.height
            if width <= 0 or height <= 0:
                logger.warning(
                    f"build_texture_atlas: aset '{root_id}' berdimensi tidak "
                    f"valid ({width}x{height}); dilewati."
                )
            elif width > max_size or height > max_size:
                logger.info(
                    f"build_texture_atlas: aset '{root_id}' ({width}x{height}) "
                    f"melebihi max_size={max_size}; tetap sebagai texture mandiri."
                )
            else:
                entries.append((root_id, width, height))
        return entries

    def _compose_atlas_page(
        self,
        page_id: str,
        page: AtlasPage,
        entries: Sequence[tuple[str, AtlasPlacement]],
    ) -> Texture2D:
        """Compose one atlas page from already-loaded textures.

        Mipmaps are never generated for a page (they would bleed neighbours).
        """
        prop = replace(self._texture_default, mipmap=False)
        self._check_texture_params(prop)
        image = self._images.gen_image_color(page.width, page.height, TRANSPARENT)
        try:
            if not self._images.is_image_valid(image):
                raise ValueError(f"Failed to create atlas page '{page_id}'")
            for root_id, placement in entries:
                self._blit_texture(image, self._textures[root_id], placement)
            return self._upload(image, page_id, prop)
        finally:
            self._images.unload_image(image)

    def _blit_texture(
        self, dst_image: Image, handle: Texture2D, placement: AtlasPlacement
    ) -> None:
        """Copy a GPU texture's pixels onto ``dst_image`` at ``placement``."""
        source = self._images.load_image_from_texture(handle)
        try:
            if not self._images.is_image_valid(source):
                raise ValueError(f"Failed to read texture '{handle.texture_id}'")
            self._images.blit(dst_image, source, (placement.x, placement.y))
        finally:
            self._images.unload_image(source)

    def _repoint_to_atlas(
        self,
        placements: Mapping[str, AtlasPlacement],
        page_ids: Sequence[str],
        page_handles: Sequence[Texture2D],
    ) -> tuple[
        dict[str, Any],
        dict[str, tuple[float, float]],
        dict[int, tuple[Texture2D, float, float]],
    ]:
        """Repoint cache entries (root + region) to the texture atlas.

        Every entry becomes a handle derived from its atlas page, so all of
        them share the page's GPU texture.

        Returns:
            Tuple ``(old_textures, delta_map, texture_map)``: old raw textures
            ready to unload, the ``(dx, dy)`` shift per ID (root + region),
            and the GPU texture ID -> ``(atlas_page_handle, dx, dy)``.
        """
        old_textures: dict[str, Any] = {}
        delta_map: dict[str, tuple[float, float]] = {}
        texture_map: dict[int, tuple[Texture2D, float, float]] = {}
        for root_id, placement in placements.items():
            old = self._textures[root_id]
            old_textures[root_id] = old.raw_texture

            page_id = page_ids[placement.page]
            page = page_handles[placement.page]
            dx = float(placement.x) - old.source_rect[0]
            dy = float(placement.y) - old.source_rect[1]

            self._textures[root_id] = page.derive(
                texture_id=root_id,
                parent_id=page_id,
                source_rect=(
                    float(placement.x),
                    float(placement.y),
                    float(placement.width),
                    float(placement.height),
                ),
            )
            self._regions[page_id].add(root_id)
            delta_map[root_id] = (dx, dy)
            texture_key = self._texture_key(old.raw_texture)
            texture_map[texture_key] = (page, dx, dy)
            self._texture_owners.pop(texture_key, None)

            for region_id in self._regions.pop(root_id, ()):
                self._textures[region_id] = page.derive(
                    texture_id=region_id,
                    parent_id=page_id,
                    source_rect=shift_rect(
                        self._textures[region_id].source_rect, dx, dy
                    ),
                )
                self._regions[page_id].add(region_id)
                delta_map[region_id] = (dx, dy)

            logger.debug(f"Aset '{root_id}' dipindah ke atlas '{page_id}'")
        return old_textures, delta_map, texture_map

    def _remap_animation_references(
        self,
        delta_map: Mapping[str, tuple[float, float]],
        texture_map: Mapping[int, tuple[Texture2D, float, float]],
    ) -> None:
        """Fix animation frames holding old texture/source_rect values.

        Frames with an ``asset_id`` but no ``source_rect`` need no change
        (resolution is lazy via :meth:`get_source_rect`). Frames holding a
        ``Texture2D`` of a packed texture get a handle derived from the
        atlas page, and frames with an explicit ``source_rect`` are shifted to
        match the asset's position in the atlas.
        """
        animations = self.one_or_none("@Animations")
        clips = getattr(animations, "clips", None)
        if not clips:
            return

        for clip in clips.values():
            for frame in clip.frames:
                delta: tuple[float, float] | None = None
                if frame.asset_id is not None:
                    delta = delta_map.get(frame.asset_id)
                if frame.texture is not None:
                    texture_delta = self._remap_frame_texture(frame, texture_map)
                    if delta is None:
                        delta = texture_delta

                if delta is not None and frame.source_rect is not None:
                    frame.source_rect = shift_rect(frame.source_rect, *delta)

    def _remap_frame_texture(
        self,
        frame: Any,
        texture_map: Mapping[int, tuple[Texture2D, float, float]],
    ) -> tuple[float, float] | None:
        """Repoint ``frame.texture`` to the atlas; return its shift or ``None``."""
        old: Texture2D = frame.texture
        entry = texture_map.get(self._texture_key(old.raw_texture))
        if entry is None:
            return None

        page, dx, dy = entry
        frame.texture = page.derive(
            texture_id=old.texture_id,
            parent_id=page.texture_id,
            source_rect=shift_rect(old.source_rect, dx, dy),
        )
        return dx, dy

    def _unique_atlas_id(
        self, base: str, page_index: int, reserved: Sequence[str] = ()
    ) -> str:
        """Find an atlas page ID not yet used by another asset."""
        suffix = "" if page_index == 0 else f"_{page_index + 1}"
        candidate = f"{base}{suffix}"
        counter = 2
        while candidate in self._textures or candidate in reserved:
            candidate = f"{base}{suffix}_{counter}"
            counter += 1
        return candidate

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

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
        """Render the asset with the given ID through the Renderer.

        The asset's own source rect (spritesheet or atlas region) is used
        unless ``source`` is given, so output is identical with or without
        :meth:`build_texture_atlas`.
        """
        handle = self.get_asset(asset_id)
        logger.debug(
            f"Rendering aset '{asset_id}' pada z={z}, layer={layer} dengan "
            f"params: pos = {pos} tint = {tint} rotation = {rotation} scale = {scale} "
            f"source = {source} dest = {dest} origin = {origin}"
        )

        self.one("Renderer").render_sprite(
            z=z,
            layer=layer,
            texture=handle,
            source=handle.source_rect if source is None else source,
            pos=pos,
            tint=tint,
            rotation=rotation,
            scale=scale,
            dest=dest,
            origin=origin,
        )
