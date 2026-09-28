"""Editor asset index built from project scan results.

Unlike :class:`plyunit.Assets`, which loads folders, this subclass
loads from :class:`~scripts.project.scan.ScanResult` so there is no
second disk traversal. The asset base path is set to the project root
by :meth:`~scripts.project.project.Project.open_project`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import plyunit
from plyunit.utils import read_json
from scripts import constants as const

if TYPE_CHECKING:
    from scripts.project.scan import ScanEntry, ScanResult

logger = logging.getLogger(__name__)


class Assets(plyunit.Assets):
    """Asset index fed by project scans."""

    def load_from_scan(self, scan: ScanResult) -> None:
        """Load every asset from a project scan result.

        Image configs are processed first (images referenced by a
        config are not loaded again as standalone assets). Configs that
        fail to load are moved back to ``json_files`` so they still
        appear in the file tree.

        Args:
            scan: Result of :func:`~scripts.project.scan.scan_project`.
        """
        images = scan.images
        image_config = list(scan.image_configs)

        loaded_image_paths, not_loaded_config = self._load_image_configs(image_config)
        for item in not_loaded_config:
            if item in scan.image_configs:
                scan.image_configs.remove(item)
            if item not in scan.json_files:
                scan.json_files.append(item)

        standalone_count = self._load_scan_images(
            images,
            loaded_image_paths=loaded_image_paths,
        )

        logger.info(
            "Folder berhasil diproses (%d aset config, %d gambar standalone)",
            len(loaded_image_paths),
            standalone_count,
        )

    def _resolve_config_image_path(self, image_path: str, config_path: Path) -> Path:
        """Resolve a config's ``image_path``, preferring sidecars.

        The engine restricts config images to ``_asset_base_path`` and
        therefore rejects legitimate sidecars (e.g. a config at
        ``data/tile/tileset.json`` pointing at ``tile/tileset.png``).
        Since the editor sets the base path to the project root and the
        scan is already limited to the project tree, the candidate
        order here is:

        1. The path as-is, when absolute.
        2. Relative to the config's folder (full sidecar).
        3. The file name next to the config (name-only sidecar).
        4. Relative to the base path (legacy configs).

        Args:
            image_path: ``image_path`` value from the config JSON.
            config_path: Path of the config JSON file.

        Returns:
            The first candidate that exists on disk; when none exists,
            the first sidecar candidate (so the error message points
            somewhere sensible).
        """
        raw = Path(image_path)
        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            config_dir = config_path.resolve().parent
            candidates.append((config_dir / raw).resolve())
            candidates.append((config_dir / raw.name).resolve())
            candidates.append((self._asset_base_path.resolve() / raw).resolve())

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def _load_image_configs(
        self, image_config: list[ScanEntry]
    ) -> tuple[set[Path], set[ScanEntry]]:
        """Load every image config; collect what succeeded and what did not.

        Args:
            image_config: Image-config scan entries.

        Returns:
            Tuple ``(loaded_image_paths, failed_configs)`` — absolute
            image paths loaded via configs, and config entries that
            must be demoted back to plain JSON files.
        """
        failed_configs: set[ScanEntry] = set()
        loaded_image_paths: set[Path] = set()
        for config in image_config:
            try:
                config_data = read_json(str(config.path))

                if "image_path" not in config_data or not config_data["image_path"]:
                    logger.debug(f"image_path is required in config : '{config.path}'")
                    failed_configs.add(config)
                    continue

                config_data["config_path"] = config.path
                image_path = self._resolve_config_image_path(
                    str(config_data["image_path"]), config.path
                )
                if image_path.parent != config.path.resolve().parent:
                    logger.warning(
                        f"Disarankan file config '{config.path.name}' dan gambar "
                        f"{image_path.name!r} berada di folder yang sama."
                    )

                if not image_path.is_file():
                    logger.error(
                        f"File gambar '{image_path.name}' "
                        f"tidak ada (config: '{config.path.name}')"
                    )
                    failed_configs.add(config)
                    continue

                loaded_image_paths.add(image_path.absolute())

                self.load_from_dict(config_data)
                logger.debug(
                    f"Config diproses: {config.path.stem} (gambar: {image_path.name})"
                )

            except Exception as error:
                logger.error(f"Gagal memproses config '{config.path.name}': {error}")
                failed_configs.add(config)

        return loaded_image_paths, failed_configs

    def _load_scan_images(
        self,
        images: list[ScanEntry],
        *,
        loaded_image_paths: set[Path],
    ) -> int:
        """Load standalone images (those not used by a config).

        Args:
            images: All images found by the scan.
            loaded_image_paths: Absolute paths of images already loaded
                via a config.

        Returns:
            The number of standalone images loaded.
        """
        standalone_count = 0

        for image in images:
            if (
                not image.path.is_file()
                or image.path.absolute() in loaded_image_paths
                or not image.is_image
            ):
                continue

            try:
                logger.debug(f"Memproses gambar standalone: {image.path.stem}")
                self.load_asset(image.relative)
                standalone_count += 1

            except Exception as error:
                logger.error(f"Gagal memproses gambar '{image.path.name}': {error}")

        if standalone_count > 0:
            logger.info(f"{standalone_count} gambar standalone dimuat")

        return standalone_count

    def get_asset_id_by_path(self, scan: ScanEntry) -> str | None:
        """Return the asset id owning a scan entry, if any.

        Args:
            scan: A file found by the scan.

        Returns:
            The asset id when the file is a config or a known image of
            some asset; ``None`` otherwise.
        """
        for asset_id, config in self._configs.items():
            if (scan.suffix == ".json" and config.config_path == scan.path) or (
                scan.suffix in const.IMAGE_EXTENSIONS and config.image_path == scan.path
            ):
                return asset_id
        return None
