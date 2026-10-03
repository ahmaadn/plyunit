"""Session state: what is open and what is happening."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkspaceState:
    """Session state: what is open and what is happening.

    Attributes:
        scanning: True while a background project scan is in flight.
            Owned by
            :class:`~scripts.services.scan_worker.ScanWorker`.
    """

    scanning: bool = False
