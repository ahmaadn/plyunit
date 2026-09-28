"""AppContext — the editor's single shared state hub.

Every element (panels, shell, your future canvas/tools) receives the
same ``AppContext`` on bind and talks to **it**, never to another
element. This keeps dependencies one-directional: UI → Context → model.

The base ships the generic parts — settings, undo history, viewport
camera, layout, status message. Add your own fields here (document,
selection, active tool, …) and intent methods for them; menu bar,
toolbar and hotkeys should all call the same intent.
"""

from __future__ import annotations

from enum import IntEnum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import plyunit


class StatusType(IntEnum):
    NONE = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()


class AppContext:
    """Shared editor state and intents.

    Attributes:
        app: The running plyunit app (window, scenes, services).
        settings: Persisted editor preferences.
        paused: When ``True`` the app freezes scene simulation.
        status: Message shown in the status bar.
    """

    def __init__(self, app: plyunit.App) -> None:
        """Create the context around a bootstrapped app."""
        self.app = app
        self.paused = False
        self.status_msg = ""
        self.status_type = StatusType.NONE
        self.project_name = ""

        self.one = app.one
        self.one_or_none = app.one_or_none
        bus = app.one_or_none("@EventBus")
        if bus is None:
            raise RuntimeError("Require Event Bus")
        self.bus = bus

    def set_status(self, message: str, status: StatusType | None = None) -> None:
        """Replace the status-bar message."""
        self.status_msg = message
        if isinstance(status, StatusType):
            self.status_type = status

    # ------------------------------------------------------------------
    # History intents
    # ------------------------------------------------------------------

    # def undo(self) -> None:
    #     """Undo the last edit."""
    #     if self.history.undo():
    #         self.set_status(f"Undo: {self.history.redo_label}")

    # def redo(self) -> None:
    #     """Redo the last undone edit."""
    #     if self.history.redo():
    #         self.set_status(f"Redo: {self.history.undo_label}")

    # ------------------------------------------------------------------
    # Your intents go here, e.g.
    #
    # def new_document(self) -> None: ...
    # def open_document(self, path: str) -> bool: ...
    # def save_document(self) -> bool: ...
    # ------------------------------------------------------------------
