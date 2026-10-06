"""The project file tree service powering the VS Code-style Explorer panel.

The pure tree model (folders, files, classification) lives in
:mod:`scripts.core.file_tree`; this module is the service that builds
and owns the tree from a :class:`~scripts.core.scan.ScanResult` already
computed in the worker thread. Consequently there is no second disk
traversal, and the exclude rules were already applied during the scan.

Every file is classified into a :class:`~scripts.core.file_kind.FileKind`.
The classification decides what happens when the file is clicked and
which files the "editor files only" toggle hides. Maps and sidecars
cannot be told apart by extension (both are ``.json``); the scan already
separated them via
:func:`~scripts.services.scan.classify_json`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

import plyunit
from scripts.core.file_kind import FileKind
from scripts.core.file_tree import DirEntry, FileEntry

if TYPE_CHECKING:
    from scripts.core.scan import ScanEntry, ScanResult

logger = logging.getLogger(__name__)


class FileTree(plyunit.ServiceUnit):
    """The tree of all project contents, built from a scan result.

    Attributes:
        root_path: Project root folder.
        root: Root tree node.
    """

    def __init__(self, root_path: Path = Path()) -> None:
        super().__init__("FileTree", tags={"filetree", "service"})
        self.root_path = root_path
        self.root = DirEntry(name=root_path.name, relative="")
        self._by_relative: dict[str, FileEntry] = {}

    def on_attach(self, app) -> None:
        """Resolve the asset index service."""
        from scripts.services.assets import Assets

        self.assets = cast(Assets, self.one("@Assets"))

    def reset(self) -> None:
        """Drop the current tree.

        Called when a *different* project starts scanning: the old
        project's tree is invalid then, and keeping it would show stale
        files until the new scan finishes. A same-root refresh keeps
        the tree visible instead.
        """
        self.root_path = Path()
        self.root = DirEntry(name="", relative="")
        self._by_relative.clear()

    def build(self, root_path: Path, result: ScanResult) -> int:
        """Rebuild the tree from a :class:`ScanResult`.

        Empty folders recorded in ``result.directories`` are still
        created so the project structure looks complete, as in VS Code
        — not just folders that happen to contain files.

        Args:
            root_path: Project root folder.
            result: The project scan result.

        Returns:
            The number of files in the tree.
        """
        self.root_path = root_path
        self.root = DirEntry(name=self.root_path.name, relative="")
        self._by_relative.clear()

        # Register folders first so empty ones still appear.
        for relative in result.directories:
            self._ensure_dir(relative)

        for entry in result.images:
            self._add_file(entry, FileKind.IMAGE)
        for entry in result.image_configs:
            self._add_file(entry, FileKind.SIDECAR)
        for entry in result.animations:
            self._add_file(entry, FileKind.ANIMATION)
        for entry in result.fonts:
            self._add_file(entry, FileKind.FONT)
        for entry in result.audio:
            self._add_file(entry, FileKind.AUDIO)
        for entry in result.maps:
            self._add_file(entry, FileKind.MAP)
        for entry in result.other:
            self._add_file(entry, FileKind.OTHER)

        self._sort(self.root)
        logger.info("File tree: %d file di %s", len(self._by_relative), self.root_path)
        return len(self._by_relative)

    def _ensure_dir(self, relative: str) -> DirEntry:
        """Return the tree node for a relative path, creating it if needed."""
        node = self.root
        for part in relative.split("/"):
            if not part:
                continue
            child = node.children.get(part)
            if child is None:
                child_rel = f"{node.relative}/{part}" if node.relative else part
                child = DirEntry(name=part, relative=child_rel)
                node.children[part] = child
            node = child
        return node

    def _add_file(self, entry: ScanEntry, kind: FileKind) -> None:
        """Insert one scan entry into the tree under its parent folder."""
        parent_rel, _, name = entry.relative.rpartition("/")
        node = self._ensure_dir(parent_rel) if parent_rel else self.root

        asset_id = None
        if kind in (FileKind.IMAGE, FileKind.SIDECAR):
            result = self.assets.get_asset_id_by_path(entry)
            if result is not None:
                asset_id = result

        file_entry = FileEntry(
            name=name or entry.relative,
            path=entry.path,
            relative=entry.relative,
            kind=kind,
            asset_id=asset_id,
            suffix=entry.suffix
        )

        node.files.append(file_entry)
        self._by_relative[entry.relative] = file_entry

    def _sort(self, node: DirEntry) -> None:
        """Sort children and files by name, recursively (case-insensitive)."""
        node.children = dict(
            sorted(node.children.items(), key=lambda kv: kv[0].lower())
        )
        node.files.sort(key=lambda f: f.name.lower())
        for child in node.children.values():
            self._sort(child)

    def get(self, relative: str) -> FileEntry | None:
        """Look up a file by its posix relative path."""
        return self._by_relative.get(relative)

    def directory(self, relative: str) -> DirEntry | None:
        """Look up a folder by its posix relative path."""
        if not relative:
            return self.root
        node = self.root
        for part in relative.split("/"):
            child = node.children.get(part)
            if child is None:
                return None
            node = child
        return node

    def absolute(self, relative: str) -> Path:
        """Turn a tree-relative path into an absolute one."""
        return self.root_path / relative if relative else self.root_path

    @property
    def file_count(self) -> int:
        """Number of files in the tree."""
        return len(self._by_relative)

    @property
    def is_empty(self) -> bool:
        """True when the tree has neither files nor folders."""
        return not self._by_relative and not self.root.children

    def search(self, query: str, *, relevant_only: bool = False) -> Sequence[FileEntry]:
        """Search files by a substring of their name or path.

        Args:
            query: Case-insensitive substring.
            relevant_only: Restrict to files the editor knows.

        Returns:
            Matching files, sorted by relative path.
        """
        needle = query.strip().lower()
        out = [
            f
            for f in self.root.iter_files()
            if (not relevant_only or f.kind.is_relevant)
            and (not needle or needle in f.relative.lower())
        ]
        out.sort(key=lambda f: f.relative.lower())
        return out


__all__ = ["FileTree"]
