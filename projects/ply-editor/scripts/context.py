"""AppContext — the editor's single shared state hub.

Every panel and service receives the same :class:`AppContext` and talks
to **it**, never to another panel. This keeps dependencies
one-directional: UI -> context -> project model.

The context ships the generic parts — status message and app/service
access. Add your own fields here (document, selection, active tool, …)
and intent methods for them; menu bar, toolbar, and hotkeys should all
call the same intent.
"""

from __future__ import annotations

from enum import IntEnum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import EditorApp


class StatusType(IntEnum):
    """Severity of a status-bar message."""

    NONE = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()


class AppContext:
    """Shared editor state and intents.

    Attributes:
        app: The running plyunit app (window, scenes, services).
        paused: When ``True`` the app freezes scene simulation.
        status_msg: Message shown in the status bar.
        status_type: Severity of the status-bar message.
        project_name: Display name of the open project ("" when none).
        one: Service locator (see ``plyunit.App.one``).
        one_or_none: Optional service locator.
        bus: The engine event bus.
    """

    def __init__(self, app: EditorApp) -> None:
        """Create the context around a bootstrapped app.

        Raises:
            RuntimeError: When the event bus service is not registered.
        """
        self.app = app
        self.paused = False
        self.status_msg = ""
        self.status_type = StatusType.NONE
        self.project_name = ""
        self.scaning_project = False

        self.one = app.one
        self.one_or_none = app.one_or_none
        self.global_config = app.global_config

    def set_status(self, message: str, status: StatusType | None = None) -> None:
        """Replace the status-bar message.

        Args:
            message: New message text.
            status: Optional severity; when omitted the previous
                severity is kept.
        """
        self.status_msg = message
        if isinstance(status, StatusType):
            self.status_type = status
