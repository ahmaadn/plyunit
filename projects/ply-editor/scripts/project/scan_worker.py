"""Background project scanning: the job and its main-thread worker.

:class:`ScanJob` runs :func:`~scripts.project.scan.scan_project` in
a daemon thread and exposes progress/result via a lock. The UI never
blocks: it polls :class:`ScanWorker` once per frame from the main
thread.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, cast

import plyunit
from scripts import constants as const
from scripts.context import StatusType
from scripts.exclude import ExcludeRules
from scripts.project.scan import ScanResult, scan_project

if TYPE_CHECKING:
    from app import EditorApp

    from scripts.assets import Assets

logger = logging.getLogger(__name__)


class ScanState(IntEnum):
    """Lifecycle state of a :class:`ScanJob`."""

    IDLE = auto()
    RUNNING = auto()
    DONE = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass(slots=True)
class ScanProgress:
    """A UI-safe progress snapshot.

    Attributes:
        files: Number of files found so far.
        current: Last relative path processed.
        state: Job state when the snapshot was taken.
    """

    files: int = 0
    current: str = ""
    state: ScanState = ScanState.IDLE

    @property
    def running(self) -> bool:
        """True while the scan is running."""
        return self.state is ScanState.RUNNING


class ScanJob:
    """A project scan running in the background.

    Main-thread usage::

        job = ScanJob(root, rules)
        job.start()
        ...
        result = job.take_result()   # None while still running
        if result is not None:
            apply(result)

    Attributes:
        root: Project root being scanned.
        rules: Exclude rules in effect.
    """

    def __init__(
        self,
        root: Path,
        rules: ExcludeRules,
        *,
        on_done: Callable[[ScanResult], None] | None = None,
    ) -> None:
        """Prepare bookkeeping for one scan.

        Args:
            root: Project root to scan.
            rules: Exclude rules to apply.
            on_done: Optional callback invoked in the worker thread
                with the result (keep it side-effect free).
        """
        self.root = root
        self.rules = rules
        self._on_done = on_done

        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._state: ScanState = ScanState.IDLE
        self._files: int = 0
        self._current: str = ""
        self._result: ScanResult | None = None
        self._error: BaseException | None = None
        self._consumed: bool = False

    def start(self) -> bool:
        """Run the scan.

        Returns:
            True when the thread started; False when the job is
            already running.
        """
        with self._lock:
            if self._state is ScanState.RUNNING:
                return False
            self._state = ScanState.RUNNING
            self._files = 0
            self._current = ""
            self._result = None
            self._error = None
            self._consumed = False
        self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            name=f"ply-editor-scan-{self.root.name or 'project'}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def cancel(self) -> None:
        """Ask the scan to stop at the next opportunity."""
        self._cancel.set()

    def shutdown(self, timeout: float = const.JOIN_TIMEOUT) -> None:
        """Cancel and wait for the thread to finish.

        Called on application close; without it the process can hang
        because the thread may still be walking a large folder.

        Args:
            timeout: Seconds to wait.
        """
        self.cancel()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Thread scan belum berhenti setelah %.1fs", timeout)
        self._thread = None

    @property
    def state(self) -> ScanState:
        """Current lifecycle state."""
        with self._lock:
            return self._state

    @property
    def running(self) -> bool:
        """True while the scan is running."""
        return self.state is ScanState.RUNNING

    @property
    def cancel_requested(self) -> bool:
        """True when cancellation was requested."""
        return self._cancel.is_set()

    @property
    def error(self) -> BaseException | None:
        """The exception that failed the scan, if any."""
        with self._lock:
            return self._error

    def progress(self) -> ScanProgress:
        """Latest progress snapshot (safe to call every frame)."""
        with self._lock:
            return ScanProgress(
                files=self._files, current=self._current, state=self._state
            )

    def take_result(self) -> ScanResult | None:
        """Take the scan result exactly once.

        Returns:
            The :class:`ScanResult` when the scan finished and the
            result has not been taken yet; ``None`` otherwise.
        """
        with self._lock:
            if self._result is None or self._consumed:
                return None
            self._consumed = True
            return self._result

    def _report(self, files: int, current: str) -> None:
        with self._lock:
            self._files = files
            self._current = current

    def _run(self) -> None:
        result: ScanResult | None = None
        error: BaseException | None = None
        try:
            result = scan_project(
                self.root,
                self.rules,
                should_cancel=self._cancel.is_set,
                on_progress=self._report,
            )
        except BaseException as exc:
            error = exc
            logger.exception("Pemindaian project gagal: %s", self.root)

        with self._lock:
            self._result = result
            self._error = error
            if error is not None:
                self._state = ScanState.FAILED
            elif result is not None and result.cancelled:
                self._state = ScanState.CANCELLED
            else:
                self._state = ScanState.DONE

        if result is not None and error is None and self._on_done is not None:
            # The callback runs in the worker thread; in this editor it
            # is only used for logging. UI state changes still go
            # through take_result().
            try:
                self._on_done(result)
            except Exception:
                logger.exception("Callback on_done pemindaian gagal")


class ScanWorker(plyunit.ServiceUnit):
    """Main-thread coordinator for the current background scan."""

    def on_attach(self, app: EditorApp) -> None:
        """Capture the shared context and reset job bookkeeping."""
        self.ctx = app.ctx
        self.active_job: ScanJob | None = None
        self._scan_reason: str | None = None

    def start(self, root: Path, rules: ExcludeRules, *, reason: str = "open") -> None:
        """Start a new scan, replacing any running one.

        Args:
            root: Project root to scan.
            rules: Exclude rules to apply.
            reason: Scan reason (``"open"`` or ``"refresh"``); only
                affects the final status message.
        """
        self.cancel()
        self.active_job = ScanJob(root, rules)
        self._scan_reason = reason
        self.active_job.start()

    def cancel(self) -> None:
        """Stop the running scan, if any."""
        if self.active_job is not None:
            self.active_job.shutdown()
            self.active_job = None

    def poll(self) -> None:
        """Apply finished scan results; call once per frame.

        When the active job produced a result, this loads assets,
        rebuilds the file tree, updates the explorer panel, and sets
        the status message.
        """
        job = self.active_job
        project = self.one_or_none("@Project")
        if job is None or project is None:
            return

        result = job.take_result()
        if result is None:
            if job.state is ScanState.FAILED:
                self.ctx.set_status(
                    "Pemindaian project gagal; lihat log.", status=StatusType.ERROR
                )
                self.active_job = None
            return

        assets = cast("Assets", self.one("@Assets"))
        assets.load_from_scan(result)

        # The explorer tree is built from the same scan result, so
        # there is no second disk traversal and the exclude rules are
        # already applied.
        tree = self.one("@FileTree")
        tree.build(project.root, result)

        imgui_layer = self.one("@ImGuiLayer")
        imgui_layer.explorer.set_tree(tree)

        verb = "dipindai ulang" if self._scan_reason == "refresh" else "ditemukan"
        self.ctx.set_status(
            f"aset {verb}." + (" (dibatalkan)" if result.cancelled else ""),
            status=StatusType.INFO,
        )
        self.active_job = None
