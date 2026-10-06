"""Editor document contract.

The editor originally knew only one document type: :class:`MapDocument`.
Every tab, workspace, and sidebar layer referenced that class directly,
so adding a new document type meant patching many places at once.

This module separates *what a tab needs* from *which document type it
holds*. A document only needs to provide:

* :attr:`Document.path` — disk location (``None`` when not yet saved),
* :attr:`Document.dirty` — unsaved changes exist,
* :meth:`Document.save` — write to disk,
* :attr:`Document.kind` — document type, used by the UI to select the
  appropriate canvas and property panel.

The contract is intentionally narrow. All type-specific details — chunks
and layers for maps, regions and grids for spritesheets — stay in their
respective classes and are reached through explicit branching on
:class:`DocumentKind`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DocumentKind(Enum):
    """Document types that can be opened as tabs.

    Values are also used as markers when saving the open-tab list to
    ``.ryeditor/editor.json``, so do not change them without migration.
    """

    MAP = "map"
    IMAGE = "image"


@dataclass(slots=True)
class CameraState:
    """Per-tab camera position so switching tabs does not lose the viewport."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = 2.0


@dataclass(slots=True, kw_only=True)
class Document(ABC):
    """Minimum capabilities required for tab content."""

    #: Document type; determines which canvas and property panel are used.
    kind: DocumentKind
    camera: CameraState = field(default_factory=CameraState)
    pending_close: bool = field(default=False)
    is_dirty: bool = field(default=False, init=False)

    def mark_dirty(self) -> None:
        """Mark that there are unsaved changes."""
        self.is_dirty = True

    @property
    def dirty(self) -> bool:
        """True when there are changes not yet written to disk."""
        return self.is_dirty

    @property
    @abstractmethod
    def path(self) -> Path | None:
        """File location on disk, or ``None`` when never saved."""
        ...

    @property
    @abstractmethod
    def title(self) -> str:
        """Short name for the tab label."""
        ...

    @abstractmethod
    def save(self, path: Path | None = None) -> Path:
        """Write the document to disk.

        Args:
            path: Destination; ``None`` uses the existing :attr:`path`.

        Returns:
            The file path that was actually written.

        Raises:
            ValueError: When no usable path is available.
            OSError: When the write fails.
        """
        ...

    @property
    def tooltip(self) -> str:
        """Hover text: the file path, or a placeholder when unsaved."""
        return str(self.path) if self.path else "Never saved"

    def label(self, *, unique_suffix: str = "") -> str:
        """Tab label including dirty marker and disambiguating suffix."""
        mark = " *" if self.dirty else ""
        name = self.title
        if unique_suffix:
            name = f"{name} ({unique_suffix})"
        return f"{name}{mark}"


__all__ = ["Document", "DocumentKind"]
