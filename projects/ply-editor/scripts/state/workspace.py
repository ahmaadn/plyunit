"""Session state: what is open and what is happening."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from scripts.state.document import Document, DocumentKind

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CameraState:
    """Per-tab camera position so switching tabs does not lose the viewport."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = 2.0


@dataclass
class WorkspaceState:
    """Session state: what is open and what is happening.

    Attributes:
        scanning: True while a background project scan is in flight.
            Owned by
            :class:`~scripts.services.scan_worker.ScanWorker`.
    """

    scanning: bool = False
    tabs: list[Document] = field(default_factory=list)
    active_index: int = -1

    def __post_init__(self) -> None:
        """Initialize the one-shot tab selection request."""
        self._force_select_tab: int | None = None

    @property
    def active(self) -> Document | None:
        """Currently active tab, or ``None`` when the workspace is empty."""
        if 0 <= self.active_index < len(self.tabs):
            return self.tabs[self.active_index]
        return None

    @property
    def is_empty(self) -> bool:
        """True when no tabs are open."""
        return not self.tabs

    @property
    def dirty_tabs(self) -> list[Document]:
        """Tabs with unsaved changes."""
        return [tab for tab in self.tabs if tab.dirty]

    def index_of_path(self, path: Path) -> int:
        """Index of the tab containing a specific file, or ``-1``."""
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        for i, tab in enumerate(self.tabs):
            if tab.path is not None and tab.path == resolved:
                return i
        return -1

    def unique_suffixes(self) -> dict[int, str]:
        """Disambiguator for tabs with the same name.

        VS Code adds a parent-folder fragment when two files share a
        name. Here only the parent folder name is used, computed only
        for conflicting names.

        Returns:
            Tab index -> disambiguation text (empty when not needed).
        """
        counts: dict[str, int] = {}
        for tab in self.tabs:
            counts[tab.title] = counts.get(tab.title, 0) + 1

        out: dict[int, str] = {}
        for i, tab in enumerate(self.tabs):
            if counts.get(tab.title, 0) <= 1 or tab.path is None:
                out[i] = ""
                continue
            parent = tab.path.parent.name
            out[i] = parent or ""
        return out

    def add(self, document: Document, *, activate: bool = True) -> Document:
        """Append a document as a new tab.

        Args:
            document: The document to open.
            activate: Immediately make this tab active.

        Returns:
            The newly added tab.
        """
        self.tabs.append(document)
        if activate or self.active_index < 0:
            self.active_index = len(self.tabs) - 1
        return document

    def activate(self, index: int) -> bool:
        """Switch to the tab at the given index."""
        if not (0 <= index < len(self.tabs)):
            return False
        self.active_index = index
        return True

    def activate_path(self, path: Path) -> bool:
        """Activate the tab containing a specific file if already open."""
        index = self.index_of_path(path)
        if index < 0:
            return False
        self.active_index = index
        return True

    def close(self, index: int) -> Document | None:
        """Close a tab without checking dirty status.

        The caller is responsible for asking confirmation first if
        needed.

        Returns:
            The closed tab, or ``None`` when the index is invalid.
        """
        if not (0 <= index < len(self.tabs)):
            return None
        tab = self.tabs.pop(index)

        if not self.tabs:
            self.active_index = -1
        elif index < self.active_index:
            self.active_index -= 1
        elif index == self.active_index:
            # Follow common editor behavior: focus moves to the tab to
            # the left when the last tab is closed, otherwise to the tab
            # at the same position.
            self.active_index = min(index, len(self.tabs) - 1)
        return tab

    def close_others(self, keep_index: int) -> list[Document]:
        """Close all tabs except one."""
        if not (0 <= keep_index < len(self.tabs)):
            return []
        keep = self.tabs[keep_index]
        closed = [tab for i, tab in enumerate(self.tabs) if i != keep_index]
        self.tabs = [keep]
        self.active_index = 0
        return closed

    def close_all(self) -> list[Document]:
        """Close every tab."""
        closed = list(self.tabs)
        self.tabs.clear()
        self.active_index = -1
        return closed

    def move(self, from_index: int, to_index: int) -> bool:
        """Reorder tabs (drag-reorder)."""
        if not (0 <= from_index < len(self.tabs)):
            return False
        if not (0 <= to_index < len(self.tabs)) or from_index == to_index:
            return False

        tab = self.tabs.pop(from_index)
        self.tabs.insert(to_index, tab)

        active = self.active_index
        if active == from_index:
            self.active_index = to_index
        elif from_index < active <= to_index:
            self.active_index -= 1
        elif to_index <= active < from_index:
            self.active_index += 1
        return True

    def next_tab(self) -> bool:
        """Cycle to the next tab."""
        if len(self.tabs) < 2:
            return False
        self.active_index = (self.active_index + 1) % len(self.tabs)
        return True

    def previous_tab(self) -> bool:
        """Cycle to the previous tab."""
        if len(self.tabs) < 2:
            return False
        self.active_index = (self.active_index - 1) % len(self.tabs)
        return True

    def index_of_kind(self, kind: DocumentKind) -> list[int]:
        """Indices of all tabs with a specific document type."""
        return [i for i, tab in enumerate(self.tabs) if tab.kind is kind]

    def open_paths(self, kind: DocumentKind | None = None) -> list[str]:
        """Paths of saved tabs, for restoring the next session.

        Args:
            kind: Limit to one document type; ``None`` means all.

        Returns:
            List of absolute paths as strings.
        """
        return [
            str(tab.path)
            for tab in self.tabs
            if tab.path is not None and (kind is None or tab.kind is kind)
        ]

    def select_tab_externally(self, index: int) -> None:
        """Ask the tab bar to select ``index`` on the next draw.

        Args:
            index: Tab index to force-select.
        """
        self._force_select_tab = index


__all__ = ["Document", "WorkspaceState"]
