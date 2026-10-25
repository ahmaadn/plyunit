"""Texture, spritesheet, and animation asset manager (Assets service).

This module provides :class:`Assets`, a
:class:`~plyunit.core.units.service_unit.ServiceUnit` responsible for
loading, caching, and providing textures for the game. Supports loading
from direct images, from JSON configuration (image, spritesheet,
animation), and in batches from a folder.

The runtime cache stores :class:`TextureData` and :class:`ImageData`
as dataclasses. JSON input is still accepted as a ``dict`` via
:meth:`load_from_dict`. All path handling relative to the asset base
directory is delegated to :class:`~plyunit.assets.paths.AssetPaths`.
"""

import logging
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from plyunit.assets.atlas import AtlasPage, AtlasPlacement, pack_shelf
from plyunit.assets.types import (
    ImageConfig,
    ImageData,
    SpriteSheetConfig,
    TextureData,
)
from plyunit.backends.interfaces.i_assets_loader import IAssetsLoader
from plyunit.core.types import (
    ColorType,
    PosType,
    RectType,
    SourceRectType,
    Texture,
    Vec2Type,
)
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.rendering.enum import Layer
from plyunit.utils.io import read_json

logger = logging.getLogger(__name__)

# Default supported extensions for batch loading.
DEFAULT_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tga"]


class AssetPaths:
    """Resolve asset paths safely against a single base directory.

    The base is resolved to an absolute, symlink-free path once (on
    construction or when it is reassigned), so every check in this class
    compares absolute paths. Any path that ends up outside the base is
    rejected with :class:`ValueError`.

    Attributes:
        base: Absolute base directory for all asset paths.
    """

    def __init__(self, base: str | Path = "./") -> None:
        """Initialize with a base directory.

        Args:
            base: Base path (relative or absolute) of the asset folder.
        """
        self._base = Path(base).resolve()

    @property
    def base(self) -> Path:
        """The absolute base directory."""
        return self._base

    @base.setter
    def base(self, value: str | Path) -> None:
        self._base = Path(value).resolve()

    def resolve(self, path: str | Path) -> Path:
        """Resolve a path relative to the base directory.

        Args:
            path: Path relative to the base (an absolute path is accepted
                as long as it stays inside the base).

        Returns:
            The resolved absolute path (it may not exist).

        Raises:
            ValueError: If the path escapes the base directory.
        """
        candidate = (self._base / path).resolve()
        self._ensure_inside(candidate, path)
        return candidate

    def resolve_config_image(self, image_path: str | Path, config_path: Path) -> Path:
        """Resolve the image referenced by a JSON config.

        Legacy configs store the path relative to the asset root, while
        editor-produced sidecars store only the image file name next to
        the JSON. The root-relative candidate has priority; the sidecar
        candidate is only used when the root-relative one does not exist.

        Args:
            image_path: The ``image_path`` value from the config.
            config_path: Path of the JSON config file.

        Returns:
            The resolved image path (it may not exist).

        Raises:
            ValueError: If the chosen candidate escapes the base directory.
        """
        root_candidate = self.resolve(image_path)
        if root_candidate.is_file():
            return root_candidate

        sidecar = (Path(config_path).parent / Path(image_path).name).resolve()
        if sidecar.is_file():
            self._ensure_inside(sidecar, image_path)
            return sidecar
        return root_candidate

    def _ensure_inside(self, candidate: Path, original: str | Path) -> None:
        if not candidate.is_relative_to(self._base):
            raise ValueError(f"Asset path escapes base path: {original}")


def _parse_rect(region_id: str, region_data: Any) -> RectType:
    """Parse one spritesheet region into an ``(x, y, w, h)`` float tuple.

    Args:
        region_id: Region ID (used for error messages).
        region_data: Either a ``[x, y, w, h]`` sequence or a legacy
            mapping with a ``rect`` key.

    Returns:
        The parsed rectangle.

    Raises:
        ValueError: If the region data is not a valid rectangle.
    """
    if isinstance(region_data, Mapping):
        region_data = region_data.get("rect", [0, 0, 0, 0])
    if not isinstance(region_data, (list, tuple)):
        raise ValueError(
            f"Region '{region_id}' must be a list [x,y,w,h] or dict with rect"
        )
    if len(region_data) != 4:
        raise ValueError(f"Region '{region_id}' must have 4 values for rect")
    x, y, w, h = region_data
    return float(x), float(y), float(w), float(h)


def _iter_region_rects(regions: Any) -> Iterator[tuple[str, RectType]]:
    """Yield ``(region_id, rect)`` pairs from either regions form.

    Args:
        regions: A mapping of ``region_id`` -> rect data, or a list of
            ``{"name": ..., "rect": ...}`` entries.

    Yields:
        Pairs of region ID and parsed rectangle.

    Raises:
        ValueError: If a region is not a valid rectangle.
    """
    if isinstance(regions, Mapping):
        items = regions.items()
    else:
        items = ((item["name"], item.get("rect")) for item in regions)
    for region_id, region_data in items:
        yield region_id, _parse_rect(region_id, region_data)


def _shift_rect(rect: RectType, dx: float, dy: float) -> RectType:
    """Return ``rect`` moved by ``(dx, dy)`` (size unchanged)."""
    return rect[0] + dx, rect[1] + dy, rect[2], rect[3]


class Assets(ServiceUnit):
    """Service for managing and caching game texture assets.

    Provides functionality to load assets (textures) from disk with
    support for JSON configuration and batch loading from folders.

    Attributes:
        _textures: Primary cache of id -> :class:`TextureData` (including
            spritesheet regions).
        _regions: Mapping of ``parent_id`` -> the set of ``region_id``
            values owned by the spritesheet (or atlas page).
        _configs: Cache of ``asset_id`` -> :class:`ImageData` (JSON context).
        _atlases: Set of atlas page IDs produced by
            :meth:`build_texture_atlas` (so they are not re-packed).
        _paths: :class:`AssetPaths` resolving every path under the base.
        _loader: The :class:`IAssetsLoader` implementation in use.
    """

    def __init__(
        self, asset_base_path: Path = Path("./"), *, loader: IAssetsLoader | None = None
    ) -> None:
        """Initialize the asset manager.

        Args:
            asset_base_path: Base path (relative or absolute) to the folder
                where all assets live. It is resolved to an absolute path
                at this point.
            loader: Custom loader implementation. If ``None``, the default
                (backend-dependent) loader is used.
        """
        super().__init__(name="Assets", tags={"service", "asset_manager", "assets"})

        self._textures: dict[str, TextureData] = {}
        self._regions: dict[str, set[str]] = {}
        self._configs: dict[str, ImageData] = {}
        self._atlases: set[str] = set()
        self._paths = AssetPaths(asset_base_path)
        if loader is None:
            from plyunit.backends.integrations import AssetsLoader

            loader = AssetsLoader()
        self._loader = loader

    @property
    def asset_base_path(self) -> Path:
        """Absolute base directory for all asset paths."""
        return self._paths.base

    @property
    def all_assets(self) -> MappingProxyType[str, TextureData]:
        """Read-only view of all assets currently in the cache.

        Returns:
            A :class:`~types.MappingProxyType` mapping ``asset_id``
            to :class:`TextureData` without copying data.
        """
        return MappingProxyType(self._textures)

    def get_config_for(self, asset_id: str) -> ImageData | None:
        """Return the :class:`ImageData` configuration for a given asset.

        Only available for assets loaded through a JSON file.
        Assets loaded directly from an image have no stored config.

        Args:
            asset_id: ID of the asset whose configuration is requested.

        Returns:
            The :class:`ImageData` if found, ``None`` otherwise.
        """
        return self._configs.get(asset_id)

    def get_config_path_for(self, asset_id: str) -> Path | None:
        """Return the absolute path to the configuration file for a given asset.

        Args:
            asset_id: ID of an asset loaded from JSON.

        Returns:
            The absolute path of the JSON file if it exists, or None.
        """
        cfg = self.get_config_for(asset_id)
        if cfg is not None and cfg.config_path is not None:
            return Path(cfg.config_path)
        return None

    def get_texture_data(self, asset_id: str) -> TextureData:
        """Fetch full texture data including its region/source rect.

        Very useful for objects that need rect properties in O(1).

        Args:
            asset_id: A region ID, or a standalone asset ID.

        Returns:
            Full TextureData with source_rect.

        Raises:
            KeyError: If the asset is not in the cache.
        """
        try:
            return self._textures[asset_id]
        except KeyError:
            logger.error(f"Aset dengan ID '{asset_id}' tidak ditemukan dalam cache")
            raise KeyError(f"Aset dengan ID '{asset_id}' tidak ditemukan") from None

    def get_asset(self, key: str) -> Texture:
        """Get a texture asset by its ID.

        Args:
            key: The asset ID.

        Returns:
            The requested texture.

        Raises:
            KeyError: If the asset is not found in memory.
        """
        return self.get_texture_data(key).texture

    def get_source_rect(self, asset_id: str) -> RectType | None:
        """Get the source rect of an asset (spritesheet/atlas region or full).

        Returns:
            The source rect, or None if the asset is unknown.
        """
        t_data = self._textures.get(asset_id)
        return t_data.source_rect if t_data is not None else None

    def get_region_parent(self, asset_id: str) -> str:
        """Get the parent spritesheet ID of a region alias.

        Returns:
            The parent ID, or the asset_id itself if it is not a region.
        """
        t_data = self._textures.get(asset_id)
        return (t_data.parent_id or asset_id) if t_data is not None else asset_id

    def __getitem__(self, key: str) -> Texture:
        """Fetch an asset using subscript notation (shorthand for get_asset)."""
        return self.get_asset(key)

    def set_assets_path(self, path: str | Path) -> None:
        """Set the base path for the asset folder.

        Args:
            path: The new base path (resolved to absolute immediately).
        """
        self._paths.base = Path(path)
        logger.info(f"Path dasar aset diubah menjadi: {self._paths.base}")

    def clear_all(self) -> None:
        """Unload all assets from the cache and clear configuration data.

        Useful before loading a new folder so no old assets remain.
        """
        for asset_id in list(self._textures):
            self.unload_asset(asset_id)
        self._configs.clear()
        self._atlases.clear()
        logger.info("Semua aset di-unload dan cache dibersihkan.")

    def destroy(self) -> None:
        """Unload all textures still stored in the cache."""
        self.clear_all()
        super().destroy()

    def unload_asset(self, asset_id: str) -> None:
        """Unload a single asset from the cache (and from GPU if a root asset).

        Unloading a root asset also removes all of its regions. Useful for
        cancelling staged loading midway.

        Args:
            asset_id: ID of the asset to unload.
        """
        try:
            t_data = self._textures.pop(asset_id, None)
            if t_data is None:
                return

            self._configs.pop(asset_id, None)

            if t_data.parent_id == asset_id:
                self._loader.unload_texture(t_data.texture)
                self._atlases.discard(asset_id)
                for region_id in self._regions.pop(asset_id, ()):
                    self._textures.pop(region_id, None)
                    self._configs.pop(region_id, None)
                logger.debug(f"Aset root '{asset_id}' berhasil diunload dari GPU")
            else:
                self._regions.get(t_data.parent_id, set()).discard(asset_id)
                logger.debug(f"Region '{asset_id}' berhasil dihapus dari cache memori")

        except Exception as error:
            logger.warning(f"Gagal unload aset '{asset_id}': {error}")

    def _put(self, t_data: TextureData) -> None:
        """Insert texture data into the cache, replacing any existing entry.

        A root entry (``parent_id == id``) gets its own region set; a
        region entry is added to its parent's region set.

        Args:
            t_data: The texture data to cache.
        """
        if t_data.id in self._textures:
            logger.warning(f"Aset '{t_data.id}' sudah ada dalam cache. Akan ditimpa.")
            self.unload_asset(t_data.id)

        self._textures[t_data.id] = t_data
        if t_data.parent_id == t_data.id:
            self._regions.setdefault(t_data.id, set())
        else:
            self._regions.setdefault(t_data.parent_id, set()).add(t_data.id)

    def _store_root(self, asset_id: str, texture: Texture) -> None:
        """Cache a whole texture as a root asset covering its full size."""
        self._put(
            TextureData(
                id=asset_id,
                parent_id=asset_id,
                texture=texture,
                source_rect=(0.0, 0.0, float(texture.width), float(texture.height)),
            )
        )

    def store_texture(self, asset_id: str, texture: Texture) -> None:
        """Store an already-created GPU texture in the asset cache.

        Used for the *staged loading* pattern: a worker thread decodes
        the CPU image (``loader.load_image``), then the main thread
        creates the GPU texture (``loader.load_texture_from_image``) and
        stores it via this method. Also used to store the results of
        ``canvas.create_rect``/``create_rects`` (baking primitives into
        ``Texture2D``) so they can be reused and packed by
        :meth:`build_texture_atlas`. Backend texture functions are NOT
        thread-safe — always call from the main thread.

        Args:
            asset_id: Unique ID of the asset in the cache.
            texture: GPU texture object (e.g. raylib ``Texture``).

        Raises:
            ValueError: If ``texture`` is not valid.
        """
        if texture is None:
            raise ValueError(f"Texture untuk aset '{asset_id}' tidak boleh None")
        self._store_root(asset_id, texture)
        logger.debug(f"Texture untuk aset '{asset_id}' disimpan dari luar")

    def store_textures(self, textures: Mapping[str, Texture]) -> None:
        """Store many GPU textures into the asset cache at once (bulk).

        Bulk version of :meth:`store_texture` — well suited to the results
        of ``canvas.create_rects``/``create_circles``/etc. Existing IDs are
        overwritten (old one unloaded).

        Args:
            textures: Mapping of ``asset_id`` -> GPU texture.

        Raises:
            ValueError: If any texture is ``None``.
        """
        for asset_id, texture in textures.items():
            self.store_texture(asset_id, texture)

    def load_asset(self, path: str, *, asset_id: str | None = None) -> None:
        """Load an asset from disk and store it in the cache.

        Args:
            path: Path to the asset relative to the base path.
            asset_id: Unique ID for the asset in the cache (optional).

        Raises:
            FileNotFoundError: If the file is not found.
            ValueError: If asset_id cannot be determined or the path
                escapes the base path.
        """
        asset_path = self._paths.resolve(path)
        logger.debug(f"Memproses pemuatan aset: {asset_path}")

        if asset_path.suffix.lower() == ".json":
            self.load_from_dict(self._read_config(asset_path), asset_id=asset_id)
        else:
            self._load_image_asset(asset_path, asset_id=asset_id)

    def load_spritesheet(
        self, config_path: str, *, asset_id: str | None = None
    ) -> None:
        """Load a spritesheet from its JSON configuration file.

        Args:
            config_path: Path to the configuration file, relative to
                the asset base path.
            asset_id: The spritesheet ID override.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can
                be determined, or a spritesheet region is malformed.
        """
        logger.debug(f"Memuat spritesheet dari {config_path}")
        config = self._read_config(self._paths.resolve(config_path))
        config.setdefault("type", "spritesheet")
        self.load_from_dict(config, asset_id=asset_id)

    def load_from_dict(
        self,
        data: ImageConfig | SpriteSheetConfig | Mapping[str, Any],
        *,
        asset_id: str | None = None,
    ) -> None:
        """Load an asset (image or spritesheet) from a JSON config dict.

        The input remains a ``dict`` (not a dataclass). The parsed
        result is stored as an :class:`ImageData` in the cache. When
        the config type is ``"spritesheet"``, its regions are
        registered as texture aliases of the sheet.

        Args:
            data: Configuration dictionary. Must contain
                ``image_path`` and an ID (from ``asset_id``,
                ``data["id"]``, or the ``config_path`` file stem).
            asset_id: Explicit asset ID override.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can
                be determined, or a spritesheet region is malformed.
        """
        self._load_config(dict(data), asset_id=asset_id)

    def _read_config(self, config_file: Path) -> dict[str, Any]:
        """Read a JSON config and attach its own path as ``config_path``."""
        config = read_json(str(config_file))
        config["config_path"] = config_file
        return config

    def _load_config(self, raw: dict[str, Any], *, asset_id: str | None) -> Path:
        """Load an image/spritesheet from a config dict.

        Args:
            raw: Config dict (a private copy; may contain ``config_path``).
            asset_id: Explicit asset ID override.

        Returns:
            The absolute path of the image file that was loaded.

        Raises:
            FileNotFoundError: If the image file is not found.
            ValueError: If ``image_path`` is missing, no asset ID can
                be determined, or a spritesheet region is malformed.
        """
        config_path = raw.get("config_path")
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

        image_ref = str(raw["image_path"])
        if config_path is not None:
            image_path = self._paths.resolve_config_image(image_ref, Path(config_path))
        else:
            image_path = self._paths.resolve(image_ref)

        if not image_path.is_file():
            message = (
                f"File gambar '{image_path.name}' tidak ada untuk aset '{resolved_id}'"
            )
            logger.error(message)
            raise FileNotFoundError(message)

        cfg = ImageData.from_dict(
            {**raw, "id": resolved_id, "image_path": image_path},
            texture_default=self._loader.default,
        )
        texture = self._loader.load_texture_from_dict(data=cfg, image_path=image_path)
        self._store_root(resolved_id, texture)
        self._configs[resolved_id] = cfg

        if cfg.type == "spritesheet":
            count = self._register_regions(
                resolved_id, texture, raw.get("regions") or {}
            )
            logger.info(
                f"Spritesheet '{resolved_id}' berhasil dimuat dengan {count} region"
            )
        else:
            logger.info(f"Aset '{resolved_id}' berhasil dimuat")
        return image_path

    def _register_regions(self, sheet_id: str, texture: Texture, regions: Any) -> int:
        """Register spritesheet regions as aliases of the sheet texture.

        Returns:
            The number of regions registered.
        """
        count = 0
        for region_id, rect in _iter_region_rects(regions):
            self._put(
                TextureData(
                    id=region_id,
                    parent_id=sheet_id,
                    texture=texture,
                    source_rect=rect,
                )
            )
            count += 1
        return count

    def _load_image_asset(
        self, asset_path: Path, *, asset_id: str | None = None
    ) -> None:
        """Load an image asset directly without a JSON configuration.

        Args:
            asset_path: Absolute path of the image file.
            asset_id: Asset ID (optional, defaults to the file stem).
        """
        logger.debug(f"Memproses aset gambar langsung: {asset_path.name}")

        resolved_id = asset_id or asset_path.stem
        defaults = self._loader.default
        texture = self._loader.load_texture(
            asset_path,
            alpha_premultiply=defaults.premultiply_alpha,
            filter_mode=defaults.filter,
            wrap_mode=defaults.wrap,
            color_key=defaults.color_key,
        )
        self._store_root(resolved_id, texture)
        logger.info(f"Aset '{resolved_id}' berhasil dimuat")

    def load_folder(
        self,
        path: str,
        *,
        allow_extensions: list[str] | None = None,
    ) -> None:
        """Load all assets from a folder.

        JSON configs are loaded first; every remaining image that no
        config referenced is then loaded as a standalone asset.

        Args:
            path: Folder path relative to the base path.
            allow_extensions: Allowed image file extensions.

        Raises:
            FileNotFoundError: If the folder does not exist.
        """
        extensions = {
            ext.lower() for ext in (allow_extensions or DEFAULT_IMAGE_EXTENSIONS)
        }
        folder_path = self._paths.resolve(path)

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
        """Load every JSON config in a folder.

        Configs without ``image_path`` are skipped.

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
        """Load standalone images that no configuration file referenced.

        Args:
            folder_path: Absolute path to the folder.
            extensions: Allowed lowercase extensions (with leading dot).
            loaded_images: Image paths already loaded via config.
        """
        count = 0
        for image_file in sorted(folder_path.iterdir()):
            if not image_file.is_file() or image_file.suffix.lower() not in extensions:
                continue

            image_path = self._paths.resolve(image_file)
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

    def build_texture_atlas(
        self,
        asset_ids: Sequence[str] | None = None,
        *,
        atlas_id: str = "atlas",
        max_size: int = 2048,
        padding: int = 2,
    ) -> list[str]:
        """Merge already-loaded assets into an in-memory texture atlas.

        Assets are packed into atlas pages (shelf packing), then each old
        asset ID is repointed to an atlas region — IDs do not change, so
        the game runs the same with or without the atlas. Spritesheet
        regions are remapped as well, animation frames holding a
        ``source_rect`` are fixed up, and old textures are unloaded
        from the GPU.

        This feature is purely optional and only for render performance:
        sprites sharing one texture can be batched into a single draw call
        by the renderer. No files are written to disk.

        Call after loading assets and before other scenes/entities take
        direct texture references (``SpriteRenderer`` with ``asset_key``
        is safe because its resolution is lazy per frame).

        Args:
            asset_ids: List of asset IDs to pack; ``None`` means all root
                assets not already in an atlas. Region IDs are
                automatically represented by their parent spritesheet.
            atlas_id: Base ID of the atlas pages (the second page onward
                gets suffixes ``_2``, ``_3``, ...).
            max_size: Maximum side of a single atlas page; larger assets
                are left as standalone textures.
            padding: Pixel spacing between assets in the atlas (anti-bleeding).

        Returns:
            The list of created atlas page IDs (empty if no assets are
            eligible for packing).

        Raises:
            KeyError: If any ID in ``asset_ids`` is not in the cache.
            ValueError: If ``max_size`` or ``padding`` is invalid.
        """
        if max_size <= 0:
            raise ValueError(f"max_size harus > 0, dapat: {max_size}")
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
        page_textures: list[Texture] = []
        for index, page in enumerate(pages):
            page_id = self._unique_atlas_id(atlas_id, index)
            texture = self._compose_atlas_page(page, placements_by_page[index])
            self._store_root(page_id, texture)
            self._atlases.add(page_id)
            page_ids.append(page_id)
            page_textures.append(texture)

        old_textures, delta_map, texture_map = self._repoint_to_atlas(
            placements, page_ids, page_textures
        )
        for texture in old_textures.values():
            self._loader.unload_texture(texture)

        self._remap_animation_references(delta_map, texture_map)

        logger.info(
            f"Texture atlas dibuat: {len(entries)} aset -> {len(pages)} halaman "
            f"({', '.join(f'{p.width}x{p.height}' for p in pages)}), "
            f"{len(old_textures)} texture lama di-unload."
        )
        return page_ids

    def _collect_atlas_roots(self, asset_ids: Sequence[str] | None) -> list[str]:
        """Collect the root asset IDs to pack into the atlas.

        Args:
            asset_ids: Explicit ID list, or ``None`` for all roots.

        Returns:
            List of unique root IDs (regions map to their parent spritesheet).

        Raises:
            KeyError: If any explicit ID is not in the cache.
        """
        if asset_ids is None:
            return [
                asset_id
                for asset_id, t_data in self._textures.items()
                if t_data.parent_id == asset_id and asset_id not in self._atlases
            ]

        roots: dict[str, None] = {}  # ordered, unique
        for asset_id in asset_ids:
            t_data = self._textures.get(asset_id)
            if t_data is None:
                raise KeyError(f"Aset dengan ID '{asset_id}' tidak ditemukan")
            root_id = t_data.parent_id or asset_id
            if root_id in self._atlases:
                logger.debug(f"Aset '{asset_id}' sudah berada di atlas; dilewati.")
                continue
            roots[root_id] = None
        return list(roots)

    def _atlas_entries(
        self, roots: Sequence[str], max_size: int
    ) -> list[tuple[str, int, int]]:
        """Build ``(root_id, width, height)`` entries eligible for packing.

        Assets with invalid dimensions or larger than ``max_size`` are
        skipped (the latter stay standalone).
        """
        entries: list[tuple[str, int, int]] = []
        for root_id in roots:
            texture = self._textures[root_id].texture
            width = int(getattr(texture, "width", 0) or 0)
            height = int(getattr(texture, "height", 0) or 0)
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
        self, page: AtlasPage, entries: Sequence[tuple[str, AtlasPlacement]]
    ) -> Texture:
        """Compose a single atlas page from already-loaded textures.

        Args:
            page: Page dimensions (:class:`~plyunit.assets.atlas.AtlasPage`).
            entries: Sequence of ``(root_id, placement)`` for this page.

        Returns:
            The atlas page GPU texture.
        """
        image = self._loader.gen_image_color(page.width, page.height)
        for root_id, placement in entries:
            source_image = self._loader.load_image_from_texture(
                self._textures[root_id].texture
            )
            self._loader.image_draw(image, source_image, (placement.x, placement.y))
            self._loader.unload_image(source_image)

        texture = self._loader.load_texture_from_image(image)
        self._loader.unload_image(image)
        self._loader.set_texture_filter(texture, self._loader.default.filter)
        self._loader.set_texture_wrap(texture, self._loader.default.wrap)
        return texture

    def _repoint_to_atlas(
        self,
        placements: Mapping[str, AtlasPlacement],
        page_ids: Sequence[str],
        page_textures: Sequence[Texture],
    ) -> tuple[
        dict[str, Texture],
        dict[str, tuple[float, float]],
        dict[int, tuple[Texture, float, float]],
    ]:
        """Repoint cache entries (root + region) to the texture atlas.

        Args:
            placements: Mapping of ``root_id`` -> :class:`AtlasPlacement`.
            page_ids: Atlas page IDs per index.
            page_textures: Atlas page textures per index.

        Returns:
            Tuple ``(old_textures, delta_map, texture_map)``: old textures
            ready to unload, the ``(dx, dy)`` shift per ID (root +
            region), and the mapping of ``id(old_texture)`` ->
            ``(atlas_texture, dx, dy)``.
        """
        old_textures: dict[str, Texture] = {}
        delta_map: dict[str, tuple[float, float]] = {}
        texture_map: dict[int, tuple[Texture, float, float]] = {}
        for root_id, placement in placements.items():
            old = self._textures[root_id]
            old_textures[root_id] = old.texture

            page_id = page_ids[placement.page]
            texture = page_textures[placement.page]
            dx = float(placement.x) - old.source_rect[0]
            dy = float(placement.y) - old.source_rect[1]

            self._textures[root_id] = TextureData(
                id=root_id,
                parent_id=page_id,
                texture=texture,
                source_rect=(
                    float(placement.x),
                    float(placement.y),
                    float(placement.width),
                    float(placement.height),
                ),
            )
            self._regions[page_id].add(root_id)
            delta_map[root_id] = (dx, dy)
            texture_map[id(old.texture)] = (texture, dx, dy)

            for region_id in self._regions.pop(root_id, ()):
                self._textures[region_id] = TextureData(
                    id=region_id,
                    parent_id=page_id,
                    texture=texture,
                    source_rect=_shift_rect(
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
        texture_map: Mapping[int, tuple[Texture, float, float]],
    ) -> None:
        """Fix animation frames holding old texture/source_rect values.

        Frames with an ``asset_id`` but no ``source_rect`` need no change
        (resolution is lazy via :meth:`get_source_rect`). Frames with an
        explicit ``source_rect`` or a direct ``texture`` are shifted to
        match the asset's position in the atlas.

        Args:
            delta_map: The ``(dx, dy)`` shift per asset ID.
            texture_map: Mapping of ``id(old_texture)`` ->
                ``(atlas_texture, dx, dy)``.
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
                elif frame.texture is not None:
                    entry = texture_map.get(id(frame.texture))
                    if entry is not None:
                        frame.texture, dx, dy = entry
                        delta = (dx, dy)

                if delta is not None and frame.source_rect is not None:
                    frame.source_rect = _shift_rect(frame.source_rect, *delta)

    def _unique_atlas_id(self, base: str, page_index: int) -> str:
        """Find an atlas page ID not yet used by another asset.

        Args:
            base: The user-provided atlas ID base.
            page_index: Page index (0-based).

        Returns:
            A unique ID for the atlas page.
        """
        suffix = "" if page_index == 0 else f"_{page_index + 1}"
        candidate = f"{base}{suffix}"
        counter = 2
        while candidate in self._textures:
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
        source: SourceRectType | None = None,
        dest: RectType | None = None,
        origin: Vec2Type = (0.0, 0.0),
    ):
        """Render the asset with the given ID.

        The asset's source rect (spritesheet region or atlas region) is
        sent along as ``source`` unless the caller provides its own
        ``source`` value, so the rendered result is identical with or
        without :meth:`build_texture_atlas`.

        Args:
            asset_id: The ID of the asset to render.
            z: The z value for render order.
            layer: The render layer used to determine draw order.
            pos: Position of the sprite (x, y).
            tint: Tint color (r, g, b, a).
            rotation: Rotation in degrees.
            scale: Uniform scale factor.
            source: Source rectangle within the texture; defaults to the
                asset's own region (spritesheet or atlas).
            dest: Destination rectangle to draw into, if any.
            origin: Rotation/scale origin offset (x, y).
        """
        t_data = self.get_texture_data(asset_id)
        logger.debug(
            f"Rendering aset '{asset_id}' pada z={z}, layer={layer} dengan "
            f"params: pos = {pos} tint = {tint} rotation = {rotation} scale = {scale} "
            f"source = {source} dest = {dest} origin = {origin}"
        )

        self.one("Renderer").render_sprite(
            z=z,
            layer=layer,
            texture=t_data.texture,
            source=source or t_data.source_rect,
            pos=pos,
            tint=tint,
            rotation=rotation,
            scale=scale,
            dest=dest,
            origin=origin,
        )
