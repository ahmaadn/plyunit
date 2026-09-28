"""The project file tree powering the VS Code-style Explorer panel.

Nothing else in the editor describes the **entire** project contents
the way an Explorer panel needs, so this module builds that tree from
a :class:`~scripts.project.scan.ScanResult` already computed in the
worker thread: ``images``, ``json_files``, ``other``, and
``directories`` are merged into one tree. Consequently there is no
second disk traversal, and the exclude rules were already applied
during the scan.

Every file is classified into a :class:`FileKind`. The classification
decides what happens when the file is clicked and which files the
"editor files only" toggle hides:

* :attr:`FileKind.IMAGE` — open an asset document tab.
* :attr:`FileKind.MAP` — open a map tab.
* :attr:`FileKind.SIDECAR` — asset config; routed to its parent image.
* :attr:`FileKind.ANIMATION` — animation config.
* :attr:`FileKind.FONT` / :attr:`FileKind.AUDIO` — shown, not openable.
* :attr:`FileKind.OTHER` — not openable by the editor.

Maps and sidecars cannot be told apart by extension (both are
``.json``); the scan already separated them via
:func:`~scripts.project.scan.classify_json`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, cast

from imgui_bundle import icons_fontawesome_6 as icons_fa

import plyunit

if TYPE_CHECKING:
    from scripts.project.scan import ScanEntry, ScanResult

logger = logging.getLogger(__name__)


class FileKind(Enum):
    """The role of a file inside the editor.

    Values double as icon/sort keys in the UI, so do not change them
    without updating :data:`KIND_ICONS`.
    """

    IMAGE = "image"
    MAP = "map"
    ANIMATION = "animation"
    SIDECAR = "sidecar"
    OTHER = "other"
    FONT = "font"
    AUDIO = "audio"

    @property
    def is_openable(self) -> bool:
        """True when clicking this file opens a document tab."""
        return self not in (
            FileKind.OTHER,
            FileKind.ANIMATION,
            FileKind.AUDIO,
            FileKind.FONT,
        )

    @property
    def is_relevant(self) -> bool:
        """True when the file shows in "editor files only" mode."""
        return self is not FileKind.OTHER


KIND_ICONS: dict[FileKind, str] = {
    FileKind.IMAGE: icons_fa.ICON_FA_FILE_IMAGE,
    FileKind.MAP: icons_fa.ICON_FA_MAP,
    FileKind.SIDECAR: icons_fa.ICON_FA_FILE_CODE,
    FileKind.OTHER: icons_fa.ICON_FA_FILE_CIRCLE_QUESTION,
    FileKind.ANIMATION: icons_fa.ICON_FA_FILM,
    FileKind.AUDIO: icons_fa.ICON_FA_FILE_AUDIO,
    FileKind.FONT: icons_fa.ICON_FA_FONT,
}
"""Font Awesome glyph shown per file kind."""


@dataclass(slots=True)
class FileEntry:
    """One file in the explorer tree.

    Attributes:
        name: File name including extension.
        path: Absolute path.
        relative: Path relative to the project root, posix separators.
        kind: The file's classification.
        asset_id: Asset id when this file is an image, or its parent
            image when this file is a sidecar. ``None`` otherwise.
    """

    name: str
    path: Path
    relative: str
    kind: FileKind = FileKind.OTHER
    asset_id: str | None = None

    @property
    def icon(self) -> str:
        """The Font Awesome glyph for this file's kind."""
        return KIND_ICONS[self.kind]

    @property
    def is_openable(self) -> bool:
        """True when the file can be opened as a tab.

        A sidecar is only openable when its parent image is actually
        indexed; an orphan sidecar leads nowhere.
        """
        if self.kind is FileKind.SIDECAR:
            return self.asset_id is not None
        return self.kind.is_openable


@dataclass(slots=True)
class DirEntry:
    """One folder in the explorer tree.

    Attributes:
        name: Folder name (``""`` for the root).
        relative: Path relative to the project root, posix separators.
        children: Sub-folders, sorted by name.
        files: Files directly inside this folder, sorted by name.
    """

    name: str
    relative: str
    children: dict[str, DirEntry] = field(default_factory=dict)
    files: list[FileEntry] = field(default_factory=list)
    is_open: bool = field(default=False, init=False)

    def iter_files(self) -> Iterator[FileEntry]:
        """Yield every file in this node and its descendants."""
        yield from self.files
        for child in self.children.values():
            yield from child.iter_files()

    def total_files(self, *, relevant_only: bool = False) -> int:
        """Count files in this node and its descendants.

        Args:
            relevant_only: Count only files the editor knows.
        """
        if not relevant_only:
            return sum(1 for _ in self.iter_files())
        return sum(1 for f in self.iter_files() if f.kind.is_relevant)

    def has_relevant(self) -> bool:
        """True when at least one relevant file exists below this node.

        Used by the explorer to hide folders that become empty while
        the "editor files only" toggle is active.
        """
        return any(f.kind.is_relevant for f in self.iter_files())


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
        from scripts.assets import Assets

        self.assets = cast(Assets, self.one("@Assets"))

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
        if kind == FileKind.OTHER:
            print(node)

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
        )
        if kind == FileKind.OTHER:
            print("------------------------------\n\n")
            print(file_entry)
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


__all__ = [
    "KIND_ICONS",
    "DirEntry",
    "FileEntry",
    "FileKind",
    "FileTree",
]
