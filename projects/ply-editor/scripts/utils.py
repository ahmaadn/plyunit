import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_json_atomic(path: Path, data: dict[str, Any]) -> bool:
    """Tulis dict ke JSON secara atomik (temp file + ``os.replace``).

    Args:
        path: Path file tujuan.
        data: Dict yang diserialisasi.

    Returns:
        True bila berhasil.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return True
    except OSError:
        logger.exception("Gagal menulis %s", path)
        return False


def read_json_safe(path: Path) -> dict[str, Any] | None:
    """Baca file JSON; ``None`` bila hilang, rusak, atau bukan objek.

    File rusak dicadangkan ke ``<nama>.bak`` sebelum diabaikan.
    """
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.exception("Gagal membaca %s", path)
        _backup_corrupt(path)
        return None
    if not isinstance(raw, dict):
        logger.warning("%s bukan objek JSON, diabaikan", path)
        _backup_corrupt(path)
        return None
    return raw


def _backup_corrupt(path: Path) -> None:
    try:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
        logger.warning("File rusak dicadangkan ke %s", backup)
    except OSError:
        logger.exception("Gagal mencadangkan %s", path)


def known_keys_stripped(raw: dict[str, Any], known: frozenset[str]) -> dict[str, Any]:
    """Ambil key tak dikenal agar dapat ditulis ulang tanpa hilang."""
    return {k: v for k, v in raw.items() if k not in known}
