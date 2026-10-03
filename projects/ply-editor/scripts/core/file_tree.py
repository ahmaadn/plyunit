"""Pure tree model behind the VS Code-style Explorer panel.

:data:`DirEntry` and :data:`FileEntry` describe a folder hierarchy with
posix-relative paths. They are pure dataclasses: the service that
builds them from a scan result lives in
:mod:`scripts.services.file_tree`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from scripts.core.file_kind import FileKind


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


__all__ = ["DirEntry", "FileEntry"]
