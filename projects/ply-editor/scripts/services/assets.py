from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import plyunit
import scripts.constants as const
from plyunit.utils import read_json

if TYPE_CHECKING:
    from scripts.project.scan import ScanEntry, ScanResult

logger = logging.getLogger(__name__)


class Assets(plyunit.Assets):
    """Assets editor berbasis hasil pemindaian project.

    Berbeda dari :class:`plyunit.Assets` yang memuat folder, kelas ini memuat
    dari :class:`~scripts.project.scan.ScanResult` sehingga tidak ada traversal
    disk kedua. Path dasar aset di-set ke root project oleh
    :meth:`scripts.project.project.Project.open_project`.
    """

    def load_from_scan(self, scan: ScanResult) -> None:
        """Muat semua aset dari hasil pemindaian project.

        Config gambar diproses lebih dulu (gambar yang dipakai config tidak
        dimuat ulang sebagai aset standalone). JSON yang gagal dipakai sebagai
        config dikembalikan ke daftar ``json_files`` agar tetap muncul di tree.

        Args:
            scan: Hasil :func:`scripts.project.scan.scan_project`.
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
        """Resolusi ``image_path`` sebuah config, prioritas sidecar.

        Engine membatasi gambar config ke ``_asset_base_path`` dan justru
        menolak sidecar yang sah (mis. config di ``data/tile/tileset.json``
        menunjuk ``tile/tileset.png``). Karena di editor base path di-set ke
        root project dan pemindaian sudah membatasi ke pohon project, di sini
        urutan kandidat adalah:

        1. Path absolut apa adanya.
        2. Relatif terhadap folder config (sidecar lengkap).
        3. Nama file di samping config (sidecar nama saja).
        4. Relatif terhadap base path (kompatibel dengan config lama).

        Args:
            image_path: Nilai ``image_path`` dari JSON config.
            config_path: Path file JSON config.

        Returns:
            Kandidat pertama yang ada di disk; bila tidak ada, kandidat
            sidecar pertama (agar pesan error menunjuk lokasi yang wajar).
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

    def _load_image_configs(self, image_config: list[ScanEntry]):
        remove_scan = set()
        loaded_image_paths = set()
        for config in image_config:
            try:
                config_data = read_json(str(config.path))

                if "image_path" not in config_data or not config_data["image_path"]:
                    logger.debug(f"image_path is required in config : '{config.path}'")

                    # convert to other type
                    remove_scan.add(config)
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
                    remove_scan.add(config)
                    continue

                loaded_image_paths.add(image_path.absolute())

                self.load_from_dict(config_data)
                logger.debug(
                    f"Config diproses: {config.path.stem} (gambar: {image_path.name})"
                )

            except Exception as error:
                logger.error(f"Gagal memproses config '{config.path.name}': {error}")
                remove_scan.add(config)

        return loaded_image_paths, remove_scan

    def _load_scan_images(
        self,
        images: list[ScanEntry],
        *,
        loaded_image_paths: set[Path],
    ) -> int:
        """Muat gambar standalone (yang tidak dipakai config).

        Args:
            images: Seluruh gambar hasil pemindaian.
            loaded_image_paths: Path absolut gambar yang sudah dimuat lewat config.

        Returns:
            Jumlah gambar standalone yang berhasil dimuat.
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

    def get_asset_id_by_path(self, scan: ScanEntry):
        for asset_id, config in self._configs.items():
            if (scan.suffix == ".json" and config.config_path == scan.path) or (
                scan.suffix in const.IMAGE_EXTENSIONS and config.image_path == scan.path
            ):
                return asset_id
        return None
