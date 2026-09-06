"""``Timer`` — delay, interval, pause, and generator wait/run.

Supports three time bases:
    - ``"fixed"`` — fixed timestep (subscribes to ``App.on_fixed_update``).
    - ``"wall"`` — wall-clock (real seconds, unaffected by time scale).
    - ``"scaled"`` — scaled time (real seconds x time scale).

Additional API:
    - ``run(generator)`` — run a coroutine that yields ``WaitToken`` or a
      playable (Tween / SequenceTween / ParallelTween).
    - ``delay`` / ``interval`` — schedule one-shot / repeating callbacks.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from plyunit.core.app import App

TimeBase = Literal["fixed", "wall", "scaled"]
Callback = Callable[[], None]
_VALID_BASES = frozenset({"fixed", "wall", "scaled"})


@dataclass(frozen=True, slots=True)
class TimerHandle:
    """Handle referencing one active timer in ``Timer``.

    Attributes:
        id: Internal timer ID.
    """

    id: int
    _service: Timer = field(repr=False, compare=False)

    def cancel(self) -> None:
        """Cancel the timer (no-op if already finished/cancelled)."""
        self._service.cancel(self)

    @property
    def is_alive(self) -> bool:
        """True if the timer is still present in the service."""
        return self.id in self._service._entries


@dataclass(frozen=True, slots=True)
class WaitToken:
    """Yielded from a generator given to ``Timer.run``.

    When ``run`` encounters a ``WaitToken``, it schedules a delay and
    resumes the generator when the timer matures.

    Attributes:
        seconds: Delay duration (≥ 0).
        time_base: Time base (``"fixed"``, ``"wall"``, ``"scaled"``).
    """

    seconds: float
    time_base: TimeBase = "fixed"


@dataclass(slots=True)
class CoroutineHandle:
    """Handle for a coroutine run by ``Timer.run``.

    Attributes:
        id: Internal coroutine ID.
    """

    id: int
    _service: Timer = field(repr=False, compare=False)

    def cancel(self) -> None:
        """Cancel the coroutine (close generator + kill pending playable)."""
        self._service.cancel_run(self)

    @property
    def is_alive(self) -> bool:
        """True if the coroutine is still registered and not finished."""
        entry = self._service._coros.get(self.id)
        return entry is not None and entry.alive and not entry.done

    @property
    def done(self) -> bool:
        """True if the coroutine has finished or was already removed."""
        entry = self._service._coros.get(self.id)
        return entry is None or entry.done


@dataclass(slots=True)
class _TimerEntry:
    """Internal record of a single timer entry."""

    remaining: float
    interval: float | None  # None = one-shot
    callback: Callback
    time_base: TimeBase
    count_left: int | None  # None = infinite interval


@dataclass(slots=True)
class _CoroEntry:
    """Internal record of a single coroutine entry."""

    gen: Generator[Any, None, None]
    wait_handle: TimerHandle | None = None
    playable: Any | None = None
    alive: bool = True
    done: bool = False


class Timer(ServiceUnit):
    """Timer with ``fixed`` / ``wall`` / ``scaled`` time bases.

    Attaches automatically to the active ``App``. Once active, it listens
    to ``on_fixed_update`` (``fixed`` base) and ``on_start_frame``
    (``wall`` and ``scaled`` bases).
    """

    def __init__(self) -> None:
        """Initialize an empty service."""
        super().__init__(name="Timer", tags={"service", "timers"})
        self._app: App | None = None
        self._paused = False
        self._next_id = 1
        self._entries: dict[int, _TimerEntry] = {}
        self._next_coro_id = 1
        self._coros: dict[int, _CoroEntry] = {}

    def on_attach(self, app: App) -> None:
        """Lifecycle hook: subscribe to fixed tick and start_frame.

        Args:
            app: App this service is attached to.
        """
        self._app = app
        app.on_fixed_update.connect(self._on_fixed_update)
        app.on_start_frame.connect(self._on_start_frame)

    def on_detach(self, app: App) -> None:
        """Lifecycle hook: unsubscribe and clean up all timers/coroutines.

        Args:
            app: App this service is detached from.
        """
        app.on_fixed_update.disconnect(self._on_fixed_update)
        app.on_start_frame.disconnect(self._on_start_frame)
        self.clear()
        self._app = None

    @property
    def paused(self) -> bool:
        """True if all ticks are paused."""
        return self._paused

    def pause(self) -> None:
        """Pause all timer ticks (entries remain, nothing is decremented)."""
        self._paused = True

    def resume(self) -> None:
        """Resume timer ticks."""
        self._paused = False

    def delay(
        self,
        seconds: float,
        callback: Callback,
        *,
        time_base: TimeBase = "fixed",
    ) -> TimerHandle:
        """Schedule a one-shot callback after ``seconds``.

        Args:
            seconds: Delay duration (≥ 0).
            callback: Function to call when the timer matures.
            time_base: Time base (``"fixed"`` / ``"wall"`` / ``"scaled"``).

        Returns:
            A cancellable TimerHandle.
        """
        return self._add(float(seconds), callback, time_base, interval=None, count=None)

    def interval(
        self,
        seconds: float,
        callback: Callback,
        *,
        time_base: TimeBase = "fixed",
        count: int | None = None,
    ) -> TimerHandle:
        """Schedule a repeating callback every ``seconds``.

        Args:
            seconds: Interval period (> 0).
            callback: Function to call each period.
            time_base: Time base.
            count: Number of repetitions (``None`` = infinite).

        Returns:
            A cancellable TimerHandle.

        Raises:
            ValueError: If the period ≤ 0 or count < 1.
        """
        period = float(seconds)
        if period <= 0.0:
            raise ValueError("interval period must be > 0")
        if count is not None and int(count) < 1:
            raise ValueError("interval count must be >= 1 or None")
        return self._add(
            period,
            callback,
            time_base,
            interval=period,
            count=None if count is None else int(count),
        )

    def wait(self, seconds: float, *, time_base: TimeBase = "fixed") -> WaitToken:
        """Create a ``WaitToken`` to ``yield`` inside a ``run`` coroutine.

        Args:
            seconds: Delay duration (≥ 0).
            time_base: Time base.

        Returns:
            WaitToken: Token ready to be yielded from a generator.

        Raises:
            ValueError: If ``seconds`` < 0.
        """
        if float(seconds) < 0.0:
            raise ValueError("wait seconds must be >= 0")
        return WaitToken(seconds=float(seconds), time_base=time_base)

    def run(self, gen: Generator[Any, None, None]) -> CoroutineHandle:
        """Run a generator, resuming automatically on ``WaitToken`` or playable yields.

        Args:
            gen: Generator that yields ``WaitToken``, ``Tween``,
                ``SequenceTween``, or ``ParallelTween``.

        Returns:
            CoroutineHandle: A cancellable handle.
        """
        cid = self._next_coro_id
        self._next_coro_id += 1
        entry = _CoroEntry(gen=gen)
        self._coros[cid] = entry
        handle = CoroutineHandle(id=cid, _service=self)
        self._advance(cid, entry)
        return handle

    def cancel(self, handle: TimerHandle) -> None:
        """Cancel a timer by handle.

        Args:
            handle: Handle to remove.
        """
        self._entries.pop(handle.id, None)

    def cancel_run(self, handle: CoroutineHandle) -> None:
        """Cancel a coroutine: close the generator, kill the pending playable.

        Args:
            handle: Coroutine handle to stop.
        """
        entry = self._coros.pop(handle.id, None)
        if entry is None:
            return
        entry.alive = False
        entry.done = True
        if entry.wait_handle is not None:
            entry.wait_handle.cancel()
        if entry.playable is not None:
            entry.playable.kill()
        entry.gen.close()

    def clear(self) -> None:
        """Remove all active timers and coroutines."""
        self._entries.clear()
        for _cid, entry in list(self._coros.items()):
            entry.alive = False
            entry.done = True
            if entry.wait_handle is not None:
                entry.wait_handle.cancel()
            if entry.playable is not None:
                entry.playable.kill()
            entry.gen.close()
        self._coros.clear()

    def _add(
        self,
        remaining: float,
        callback: Callback,
        time_base: TimeBase,
        *,
        interval: float | None,
        count: int | None,
    ) -> TimerHandle:
        """Internal: add a new timer entry to the service.

        Args:
            remaining: Initial remaining time.
            callback: Callback function.
            time_base: Time base.
            interval: Period (None = one-shot).
            count: Number of repetitions.

        Returns:
            The new TimerHandle.

        Raises:
            ValueError: If ``time_base`` is invalid or ``remaining`` < 0.
        """
        if time_base not in _VALID_BASES:
            raise ValueError(f"invalid time_base {time_base!r}")
        if remaining < 0.0:
            raise ValueError("seconds must be >= 0")
        hid = self._next_id
        self._next_id += 1
        self._entries[hid] = _TimerEntry(
            remaining=remaining,
            interval=interval,
            callback=callback,
            time_base=time_base,
            count_left=count,
        )
        return TimerHandle(id=hid, _service=self)

    def _on_fixed_update(self, dt: float) -> None:
        """Tick the ``fixed`` base on every ``App`` fixed update."""
        if not self._paused:
            self._tick("fixed", float(dt))

    def _on_start_frame(self) -> None:
        """Tick the ``wall`` and ``scaled`` bases on every frame start."""
        if self._paused or self._app is None:
            return
        if self._app.window is None:
            return
        self._tick("wall", float(self._app.window.unscaled_dt))
        self._tick("scaled", float(self._app.window.dt))

    def _tick(self, base: TimeBase, dt: float) -> None:
        """Decrement all entries with base ``base`` by ``dt`` seconds."""
        if dt <= 0.0:
            return
        for hid in list(self._entries):
            entry = self._entries.get(hid)
            if entry is None or entry.time_base != base:
                continue
            entry.remaining -= dt
            while entry.remaining <= 1e-12:
                cb = entry.callback
                if entry.interval is None:
                    del self._entries[hid]
                    cb()
                    break
                cb()
                if entry.count_left is not None:
                    entry.count_left -= 1
                    if entry.count_left <= 0:
                        del self._entries[hid]
                        break
                entry.remaining += entry.interval
                if entry.remaining > 0.0:
                    break

    def _advance(self, cid: int, entry: _CoroEntry) -> None:
        """Advance the generator: wait on a ``WaitToken`` or run a playable."""
        if not entry.alive or entry.done:
            return
        entry.wait_handle = None
        entry.playable = None
        while entry.alive and not entry.done:
            try:
                item = next(entry.gen)
            except StopIteration:
                entry.done = True
                entry.alive = False
                self._coros.pop(cid, None)
                return

            if isinstance(item, WaitToken):

                def resume(c: int = cid) -> None:
                    """Advance the coroutine when its wait delay elapses."""
                    e = self._coros.get(c)
                    if e is not None and e.alive and not e.done:
                        self._advance(c, e)

                entry.wait_handle = self.delay(
                    item.seconds, resume, time_base=item.time_base
                )
                return

            # Tween / Sequence / Parallel
            from plyunit.services.tween.tween import ParallelTween, SequenceTween, Tween

            if isinstance(item, (Tween, SequenceTween, ParallelTween)):
                entry.playable = item

                def resume_play(c: int = cid) -> None:
                    """Advance the coroutine when its playable completes."""
                    e = self._coros.get(c)
                    if e is not None and e.alive and not e.done:
                        self._advance(c, e)

                item.on_complete(resume_play)
                if not item.is_alive:
                    item.play()
                return

            raise TypeError(f"yield WaitToken or tween playable, got {type(item)!r}")
