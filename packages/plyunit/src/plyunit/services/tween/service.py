"""``TweenAnimation`` — property tweens with fixed/wall/scaled time bases.

Supports:
- Single tweens (``to`` / ``tween``) with multiple property tracks.
- Yoyo and looping.
- SequenceTween (plays one by one) and ParallelTween (plays together).
- Fast lookup by target or tag.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from plyunit.core.units.service_unit import ServiceUnit
from plyunit.services.tween.tween import (
    ParallelTween,
    SequenceTween,
    TransformTween,
    Tween,
    make_property_tween,
)
from plyunit.utils.math.easing import EaseFn, get_easing

if TYPE_CHECKING:
    from plyunit.core.app import App

TimeBase = Literal["fixed", "wall", "scaled"]
Callback = Callable[[], None]
Getter = Callable[[], Any]
Setter = Callable[[Any], None]


class TweenAnimation(ServiceUnit):
    """Global tween runner.

    Attaches automatically to the active ``App``. Once active, it listens
    to ``on_fixed_update`` (``fixed`` base) and ``on_start_frame``
    (``wall`` and ``scaled`` bases).
    """

    def __init__(self) -> None:
        """Initialize an empty service."""
        super().__init__(name="TweenAnimation", tags={"service", "tween"})
        self._app: App | None = None
        self._paused = False
        self._next_id = 1
        self._tweens: dict[int, Tween] = {}
        self._sequences: dict[int, SequenceTween] = {}
        self._parallels: dict[int, ParallelTween] = {}
        self._prop_owners: dict[tuple[int, str], int] = {}

    def on_attach(self, app: App) -> None:
        """Lifecycle hook: subscribe to fixed tick and start_frame.

        Args:
            app: App this service is attached to.
        """
        self._app = app
        app.on_fixed_update.connect(self._on_fixed_update)
        app.on_start_frame.connect(self._on_start_frame)

    def on_detach(self, app: App) -> None:
        """Lifecycle hook: kill all tweens and unsubscribe.

        Args:
            app: App this service is detached from.
        """
        app.on_fixed_update.disconnect(self._on_fixed_update)
        app.on_start_frame.disconnect(self._on_start_frame)
        self.kill_all()
        self._app = None

    @property
    def paused(self) -> bool:
        """True if all ticks are paused."""
        return self._paused

    def pause(self) -> None:
        """Pause all tween ticks."""
        self._paused = True

    def resume(self) -> None:
        """Resume tween ticks."""
        self._paused = False

    def to(
        self,
        transform: Any,
        duration: float = 0.3,
        *,
        easing: str | EaseFn = "linear",
        time_base: TimeBase = "wall",
        tag: str | None = None,
    ) -> TransformTween:
        """Create a ``TransformTween`` for a single ``TransformState``.

        Not played yet; call ``.position()`` / ``.rotation()`` / ``.scale()``
        to add tracks, then ``.play()``.

        Args:
            transform: Target ``TransformState`` to tween.
            duration: Tween duration in seconds.
            easing: Easing name (``"linear"`` / ``"ease_in"`` / ...) or function.
            time_base: Time base.
            tag: Tag for lookup / kill_by_tag.

        Returns:
            TransformTween: Builder ready for tracks to be added.
        """
        return TransformTween(
            self,
            duration=float(duration),
            ease=get_easing(easing),
            time_base=time_base,
            target=transform,
            tag=tag,
        )

    def tween(
        self,
        getter: Getter,
        setter: Setter,
        end: Any,
        duration: float = 0.3,
        *,
        easing: str | EaseFn = "linear",
        time_base: TimeBase = "wall",
        is_vector: bool | None = None,
        tag: str | None = None,
        on_complete: Callback | None = None,
        autoplay: bool = True,
    ) -> Tween:
        """Create a single-property ``Tween`` (auto-played by default).

        Args:
            getter: Function to read the current value.
            setter: Function to write the new value.
            end: Target value.
            duration: Tween duration in seconds.
            easing: Easing name or function.
            time_base: Time base.
            is_vector: ``True`` if an ``(x, y)`` tuple (auto-detected when ``None``).
            tag: Tag for lookup / kill_by_tag.
            on_complete: Callback when the tween finishes.
            autoplay: Automatically ``play()`` after creation.

        Returns:
            Tween: A tween instance that is ready (or already running).
        """
        tw = make_property_tween(
            self,
            getter,
            setter,
            end,
            duration=duration,
            easing=easing,
            time_base=time_base,
            is_vector=is_vector,
            tag=tag,
        )
        if on_complete is not None:
            tw.on_complete(on_complete)
        if autoplay:
            tw.play()
        return tw

    def sequence(self, *children: Any) -> SequenceTween:
        """Wrap several playables into a ``SequenceTween``.

        Args:
            *children: Playables to run in order.

        Returns:
            SequenceTween: Not played yet; call ``.play()`` to start.
        """
        return SequenceTween(self, list(children))

    def parallel(self, *children: Any) -> ParallelTween:
        """Wrap several playables into a ``ParallelTween``.

        Args:
            *children: Playables to run simultaneously.

        Returns:
            ParallelTween: Not played yet; call ``.play()`` to start.
        """
        return ParallelTween(self, list(children))

    def kill(self, playable: Tween | SequenceTween | ParallelTween) -> None:
        """Kill one specific playable.

        Args:
            playable: Tween / SequenceTween / ParallelTween to stop.
        """
        playable.kill()

    def kill_by_target(self, target: Any) -> None:
        """Kill every tween that owns ``target`` or a track belonging to ``target``.

        Args:
            target: Target object used as the kill reference.
        """
        tid = id(target)
        for tw in list(self._tweens.values()):
            if tw.target is target or any(tr.prop_key[0] == tid for tr in tw.tracks):
                self._kill(tw)

    def kill_by_tag(self, tag: str) -> None:
        """Kill every tween/sequence/parallel with the given ``tag``.

        Args:
            tag: Tag to match.
        """
        for tw in list(self._tweens.values()):
            if tw.tag == tag:
                self._kill(tw)
        for seq in list(self._sequences.values()):
            if seq.tag == tag:
                self._kill_sequence(seq)
        for par in list(self._parallels.values()):
            if par.tag == tag:
                self._kill_parallel(par)

    def kill_all(self) -> None:
        """Kill all active tweens, sequences, and parallels."""
        for tw in list(self._tweens.values()):
            self._kill(tw)
        for seq in list(self._sequences.values()):
            self._kill_sequence(seq)
        for par in list(self._parallels.values()):
            self._kill_parallel(par)

    def _register(self, tw: Tween) -> None:
        """Internal: register a tween with the service and capture start values."""
        if tw.playing and tw.alive:
            return
        if not tw.tracks:
            raise ValueError("tween has no properties")
        for track in tw.tracks:
            owner_id = self._prop_owners.get(track.prop_key)
            if owner_id is not None and owner_id != tw.id:
                old = self._tweens.get(owner_id)
                if old is not None:
                    self._kill(old)
        if tw.id == 0:
            tw.id = self._next_id
            self._next_id += 1
        tw.alive = True
        tw.playing = True
        tw.elapsed = 0.0
        tw.forward = True
        tw.capture_starts()
        self._tweens[tw.id] = tw
        for track in tw.tracks:
            self._prop_owners[track.prop_key] = tw.id
        if tw.duration <= 0.0:
            tw.apply(1.0)
            self._finish(tw)

    def _register_sequence(self, seq: SequenceTween) -> None:
        """Internal: register a sequence and start its first child."""
        if not seq.children:
            seq.playing = True
            seq.alive = False
            for cb in list(seq.on_complete_cbs):
                cb()
            return
        if seq.id == 0:
            seq.id = self._next_id
            self._next_id += 1
        seq.alive = True
        seq.playing = True
        seq.index = 0
        self._sequences[seq.id] = seq
        self._start_seq_child(seq)

    def _register_parallel(self, par: ParallelTween) -> None:
        """Internal: register a parallel and play all children."""
        if not par.children:
            par.playing = True
            par.alive = False
            for cb in list(par.on_complete_cbs):
                cb()
            return
        if par.id == 0:
            par.id = self._next_id
            self._next_id += 1
        par.alive = True
        par.playing = True
        par.remaining = len(par.children)
        self._parallels[par.id] = par
        for child in par.children:

            def done(p: ParallelTween = par) -> None:
                """Count down one finished child; finish the parallel at zero."""
                if not p.alive:
                    return
                p.remaining -= 1
                if p.remaining <= 0:
                    self._finish_parallel(p)

            child.on_complete(done)
            child.play()

    def _start_seq_child(self, seq: SequenceTween) -> None:
        """Internal: start the next child in a sequence."""
        if not seq.alive:
            return
        if seq.index >= len(seq.children):
            self._finish_sequence(seq)
            return
        child = seq.children[seq.index]

        def nxt(s: SequenceTween = seq) -> None:
            """Advance the sequence to its next child."""
            if s.alive:
                s.index += 1
                self._start_seq_child(s)

        child.on_complete(nxt)
        child.play()

    def _kill(self, tw: Tween) -> None:
        """Internal: remove a tween from the service."""
        tw.alive = False
        tw.playing = False
        self._tweens.pop(tw.id, None)
        for track in tw.tracks:
            if self._prop_owners.get(track.prop_key) == tw.id:
                del self._prop_owners[track.prop_key]

    def _kill_sequence(self, seq: SequenceTween) -> None:
        """Internal: remove a sequence and kill its running child."""
        seq.alive = False
        seq.playing = False
        self._sequences.pop(seq.id, None)
        if 0 <= seq.index < len(seq.children):
            seq.children[seq.index].kill()

    def _kill_parallel(self, par: ParallelTween) -> None:
        """Internal: remove a parallel and kill all its children."""
        par.alive = False
        par.playing = False
        self._parallels.pop(par.id, None)
        for child in par.children:
            child.kill()

    def _finish(self, tw: Tween) -> None:
        """Internal: a tween reached the end of its duration (handle yoyo/loop)."""
        if tw.yoyo_enabled:
            tw.forward = not tw.forward
            for track in tw.tracks:
                track.start, track.end = track.end, track.start
            if tw.forward and not self._more_loops(tw):
                self._complete(tw)
                return
            tw.elapsed = 0.0
            return
        if not self._more_loops(tw):
            self._complete(tw)
            return
        tw.elapsed = 0.0
        tw.capture_starts()

    def _more_loops(self, tw: Tween) -> bool:
        """Internal: check whether another loop remains (``-1`` = infinite)."""
        if tw.loops_left == -1:
            return True
        if tw.loops_left > 1:
            tw.loops_left -= 1
            return True
        return False

    def _complete(self, tw: Tween) -> None:
        """Internal: finish a tween (kill + fire callbacks)."""
        self._kill(tw)
        for cb in list(tw.on_complete_cbs):
            cb()

    def _finish_sequence(self, seq: SequenceTween) -> None:
        """Internal: a sequence finished."""
        seq.alive = False
        seq.playing = False
        self._sequences.pop(seq.id, None)
        for cb in list(seq.on_complete_cbs):
            cb()

    def _finish_parallel(self, par: ParallelTween) -> None:
        """Internal: a parallel finished (all children done)."""
        par.alive = False
        par.playing = False
        self._parallels.pop(par.id, None)
        for cb in list(par.on_complete_cbs):
            cb()

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
        """Advance tweens on base ``base`` by ``dt`` seconds."""
        if dt <= 0.0:
            return
        for tid in list(self._tweens):
            tw = self._tweens.get(tid)
            if tw is None or not tw.playing or tw.time_base != base:
                continue
            tw.elapsed += dt
            if tw.duration <= 0.0 or tw.elapsed >= tw.duration:
                tw.apply(1.0)
                self._finish(tw)
            else:
                tw.apply(tw.elapsed / tw.duration)
