"""Safe and atomic JSON persistence helpers.

Every config file in the editor goes through these functions so that a
crash can never leave a half-written file and a corrupt file can never
crash the editor on startup.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_json_atomic(path: Path, data: dict[str, Any]) -> bool:
    """Write a dict as JSON atomically (temp file + ``os.replace``).

    Args:
        path: Destination file path.
        data: Dict to serialize.

    Returns:
        True when the write succeeded.
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
    """Read a JSON file; ``None`` when missing, corrupt, or not an object.

    A corrupt file is backed up as ``<name>.bak`` before being ignored.

    Args:
        path: File to read.

    Returns:
        The parsed object, or ``None``.
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
    """Copy a corrupt file aside so the user can inspect it later."""
    try:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
        logger.warning("File rusak dicadangkan ke %s", backup)
    except OSError:
        logger.exception("Gagal mencadangkan %s", path)


def known_keys_stripped(raw: dict[str, Any], known: frozenset[str]) -> dict[str, Any]:
    """Return the keys not covered by ``known`` so they survive a rewrite.

    Args:
        raw: Raw config dict.
        known: Keys the config dataclass already handles.

    Returns:
        Dict of unknown keys only.
    """
    return {k: v for k, v in raw.items() if k not in known}
