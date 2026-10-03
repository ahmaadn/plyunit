"""Project scanning: one walk, pruning excluded folders.

The previous implementation used ``Path.rglob`` — five times for images
and once more for maps — then filtered the results. Post-filtering
does not help: ``rglob`` already walked ``.venv/Lib/site-packages``
before a single result was dropped.

This module replaces it with a single :func:`os.scandir`-based
traversal that **prunes** excluded folders before entering them, and
produces image, map, and sidecar candidates in one pass.

The result model lives in :mod:`scripts.core.scan`; this module only
owns the disk traversal and the shallow JSON classification. Nothing
here calls raylib or ImGui, so it is safe to run in a worker thread
(see :mod:`scripts.services.scan_worker`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from scripts import constants as const
from scripts.core.exclude import ExcludeRules
from scripts.core.scan import (
    JSON_KIND_ANIMATION,
    JSON_KIND_IMAGE_CONFIG,
    JSON_KIND_MAP,
    JSON_KIND_OTHER,
    JSONKind,
    ScanEntry,
    ScanResult,
)

logger = logging.getLogger(__name__)


def classify_json(path: Path, *, probe_bytes: int = const.MAP_PROBE_BYTES) -> JSONKind:
    """Guess what kind of editor JSON a file is.

    The check is deliberately shallow — only the head of the file is
    read — because parsing every JSON in a large project costs far
    more than it is worth.

    Args:
        path: Candidate JSON file.
        probe_bytes: Number of leading bytes to read.

    Returns:
        One of ``"map"``, ``"animation"``, ``"image_config"``, or
        ``"other"``.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(probe_bytes)
    except OSError:
        return JSON_KIND_OTHER

    if '"settings"' in head or '"tilesets"' in head or '"map_type"' in head:
        return JSON_KIND_MAP

    if '"group"' in head or '"animations"' in head:
        return JSON_KIND_ANIMATION

    if '"image_path"' in head or '"texture"' in head:
        return JSON_KIND_IMAGE_CONFIG

    return JSON_KIND_OTHER


def iter_files(
    root: Path,
    rules: ExcludeRules,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_directory: Callable[[str], None] | None = None,
    on_pruned: Callable[[str], None] | None = None,
    follow_symlinks: bool = False,
) -> Iterator[ScanEntry]:
    """Walk ``root`` iteratively, pruning excluded folders.

    Folders matching the exclude rules are never opened at all, so they
    cost nothing instead of being walked and then discarded.

    Args:
        root: Starting folder.
        rules: Compiled exclude rules.
        should_cancel: Polled per folder; ``True`` stops the walk.
        on_directory: Called for every folder walked.
        on_pruned: Called for every folder skipped.
        follow_symlinks: Follow folder symlinks (off by default, safe
            against cycles).

    Yields:
        A :class:`ScanEntry` for every file that passed the excludes.
    """
    try:
        base = root.resolve()
    except OSError:
        logger.warning("Root pemindaian tidak dapat dibaca: %s", root)
        return

    if not base.is_dir():
        logger.warning("Root pemindaian bukan folder: %s", base)
        return

    # The stack holds (absolute path, relative posix path) pairs.
    stack: list[tuple[Path, str]] = [(base, "")]
    seen_dirs: set[str] = set()

    while stack:
        if should_cancel is not None and should_cancel():
            return

        current, relative = stack.pop()
        if on_directory is not None:
            on_directory(relative)

        try:
            with os.scandir(current) as it:
                entries = list(it)
        except (OSError, PermissionError):
            logger.debug("Folder dilewati (tidak terbaca): %s", current, exc_info=True)
            continue

        for entry in entries:
            child_rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                continue

            if is_dir:
                if rules.is_excluded_dir(entry.name, child_rel):
                    if on_pruned is not None:
                        on_pruned(child_rel)
                    continue
                if not follow_symlinks:
                    try:
                        real = os.path.realpath(entry.path)
                    except OSError:
                        real = entry.path
                    if real in seen_dirs:
                        continue
                    seen_dirs.add(real)
                stack.append((Path(entry.path), child_rel))
                continue

            try:
                if not entry.is_file(follow_symlinks=follow_symlinks):
                    continue
            except OSError:
                continue
            if rules.is_excluded_dir(entry.name, child_rel):
                if on_pruned is not None:
                    on_pruned(child_rel)
                continue

            yield ScanEntry(
                path=Path(entry.path),
                relative=child_rel,
                suffix=os.path.splitext(entry.name)[1].lower(),
            )


def scan_project(
    root: Path,
    rules: ExcludeRules,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, str], None] | None = None,
    detect_maps: bool = True,
    collect_other: bool = True,
) -> ScanResult:
    """Scan a project in one pass for images, JSON, and maps.

    Args:
        root: Project root.
        rules: Exclude rules.
        should_cancel: Polled periodically; ``True`` stops the scan and
            marks the result as ``cancelled``.
        on_progress: Called with ``(file_count, last_relative_path)``.
        detect_maps: Run :func:`classify_json` on every ``.json``.
        collect_other: Also record other file types (for the full tree).

    Returns:
        A :class:`ScanResult` with every finding.
    """
    result = ScanResult()
    count = 0

    for entry in iter_files(
        root,
        rules,
        should_cancel=should_cancel,
        on_directory=lambda rel: result.directories.append(rel),
        on_pruned=lambda rel: result.pruned.append(rel),
    ):
        if entry.is_image:
            result.images.append(entry)
        elif entry.is_json:
            result.json_files.append(entry)
            if detect_maps:
                kind = classify_json(entry.path)
                if kind == JSON_KIND_ANIMATION:
                    result.animations.append(entry)
                elif kind == JSON_KIND_MAP:
                    result.maps.append(entry)
                elif kind == JSON_KIND_IMAGE_CONFIG:
                    result.image_configs.append(entry)
        elif collect_other:
            if entry.is_audio:
                result.audio.append(entry)
            elif entry.is_font:
                result.fonts.append(entry)
            else:
                result.other.append(entry)

        count += 1
        if on_progress is not None and count % 64 == 0:
            on_progress(count, entry.relative)

    if should_cancel is not None and should_cancel():
        result.cancelled = True

    result.audio.sort(key=lambda e: e.relative.lower())
    result.animations.sort(key=lambda e: e.relative.lower())
    result.fonts.sort(key=lambda e: e.relative.lower())
    result.images.sort(key=lambda e: e.relative.lower())
    result.json_files.sort(key=lambda e: e.relative.lower())
    result.maps.sort(key=lambda e: e.relative.lower())
    result.other.sort(key=lambda e: e.relative.lower())

    if on_progress is not None:
        on_progress(count, "")

    logger.info(
        "Scan %s: %d file (%d gambar, %d json, %d map), %d folder dipangkas%s",
        root,
        count,
        len(result.images),
        len(result.json_files),
        len(result.maps),
        len(result.pruned),
        " [dibatalkan]" if result.cancelled else "",
    )
    return result


__all__ = ["classify_json", "iter_files", "scan_project"]
