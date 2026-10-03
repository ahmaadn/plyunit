"""Ephemeral UI state: never persisted, replaced every frame as needed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, auto


class StatusType(IntEnum):
    """Severity of a status-bar message."""

    NONE = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()


@dataclass
class UIState:
    """Ephemeral UI state, never persisted.

    Attributes:
        status_msg: Message shown in the status bar.
        status_type: Severity of the status-bar message.
    """

    status_msg: str = ""
    status_type: StatusType = StatusType.NONE

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


__all__ = ["StatusType", "UIState"]
