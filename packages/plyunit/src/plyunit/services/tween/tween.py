"""Playable tween: property tracks, transform helper, sequence/parallel.

This module defines:
    - ``_Track`` — a single property interpolation path.
    - ``Tween`` — base playable with multiple tracks.
    - ``TransformTween`` — fluent builder for ``TransformState``.
    - ``SequenceTween`` / ``ParallelTween`` — playable compositions.
    - ``make_property_tween`` — factory for a single-property tween.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Self

from plyunit.utils.math.easing import EaseFn, get_easing
from plyunit.utils.math.utils import lerp, lerp_vector2

if TYPE_CHECKING:
    from plyunit.services.tween.service import TweenAnimation

TimeBase = Literal["fixed", "wall", "scaled"]
Callback = Callable[[], None]
Getter = Callable[[], Any]
Setter = Callable[[Any], None]


@dataclass(slots=True)
class _Track:
    """Internal: a single interpolation path from ``start`` to ``end``.

    Attributes:
        prop_key: Identification key (target id, property name).
        getter: Function to read the current property value.
        setter: Function to write the new property value.
        start: Initial value snapshot (filled by ``capture_starts``).
        end: Interpolation target value.
        is_vector: ``True`` if the value is an ``(x, y)`` tuple.
    """

    prop_key: tuple[int, str]
    getter: Getter
    setter: Setter
    start: Any
    end: Any
    is_vector: bool


class Tween:
    """Property tween (single or multiple tracks).

    Attributes:
        id: Internal ID (assigned by the service on ``play()``).
        duration: Tween duration in seconds.
        ease: Easing function ``(t_norm) -> eased_t``.
        elapsed: Time elapsed since ``play()`` (seconds).
        forward: Direction for yoyo (``True`` = forward).
        loops_left: Loops remaining (``-1`` = infinite).
        yoyo_enabled: ``True`` to ping-pong start->end->start.
        playing: ``True`` while the tween is active.
        alive: ``True`` until killed.
        tracks: List of tracks being interpolated.
        on_complete_cbs: Callbacks fired when the tween finishes.
        target: Target object (for ``kill_by_target``).
        tag: Tag for ``kill_by_tag``.
        time_base: Time base (``"fixed"`` / ``"wall"`` / ``"scaled"``).
    """

    __slots__ = (
        "_service",
        "alive",
        "duration",
        "ease",
        "elapsed",
        "forward",
        "id",
        "loops_left",
        "on_complete_cbs",
        "playing",
        "tag",
        "target",
        "time_base",
        "tracks",
        "yoyo_enabled",
    )

    def __init__(
        self,
        service: TweenAnimation,
        *,
        duration: float,
        ease: EaseFn,
        time_base: TimeBase,
        target: Any | None = None,
        tag: str | None = None,
    ) -> None:
        """Initialize an empty tween (no tracks yet).

        Args:
            service: ``TweenAnimation`` that will run this tween.
            duration: Duration in seconds.
            ease: Easing function.
            time_base: Time base.
            target: Target object (for lookup / kill).
            tag: Tag for lookup / kill.
        """
        self._service = service
        self.id = 0
        self.duration = max(0.0, float(duration))
        self.elapsed = 0.0
        self.ease = ease
        self.time_base = time_base
        self.tracks: list[_Track] = []
        self.on_complete_cbs: list[Callback] = []
        self.yoyo_enabled = False
        self.loops_left = 1  # plays remaining; -1 infinite
        self.forward = True
        self.alive = True
        self.playing = False
        self.target = target
        self.tag = tag

    def on_complete(self, callback: Callback) -> Self:
        """Register a callback invoked when the tween finishes.

        Args:
            callback: Function taking no arguments.

        Returns:
            Self, for chaining.
        """
        self.on_complete_cbs.append(callback)
        return self

    def yoyo(self, enabled: bool = True) -> Self:
        """Enable/disable yoyo mode (ping-pong).

        Args:
            enabled: ``True`` to enable yoyo.

        Returns:
            Self, for chaining.
        """
        self.yoyo_enabled = bool(enabled)
        return self

    def loop(self, count: int = -1) -> Self:
        """Set the tween's loop count.

        Args:
            count: ``-1`` for infinite; ``N >= 1`` for N total plays.

        Returns:
            Self, for chaining.

        Raises:
            ValueError: If count < -1 or count == 0.
        """
        n = int(count)
        if n < -1 or n == 0:
            raise ValueError("loop count must be -1 or >= 1")
        self.loops_left = n
        return self

    def play(self) -> Self:
        """Register and start the tween on the service.

        Returns:
            Self, for chaining.
        """
        self._service._register(self)
        return self

    def kill(self) -> None:
        """Stop the tween and remove it from the service."""
        self._service._kill(self)

    @property
    def is_alive(self) -> bool:
        """True if the tween is alive and playing."""
        return self.alive and self.playing

    def capture_starts(self) -> None:
        """Snapshot each track's initial value as the interpolation starting point."""
        for track in self.tracks:
            track.start = track.getter()

    def apply(self, t_norm: float) -> None:
        """Compute and apply interpolated values to all tracks.

        Args:
            t_norm: Normalized time ``[0, 1]`` (eased internally via ``ease``).
        """
        e = self.ease(t_norm)
        for track in self.tracks:
            if track.is_vector:
                track.setter(lerp_vector2(track.start, track.end, e))
            else:
                track.setter(lerp(float(track.start), float(track.end), e))


class TransformTween(Tween):
    """Fluent builder for tweening a ``TransformState``.

    Example:
        >>> tw = TweenAnimation().to(transform, duration=0.5) \\
        ...     .position((100, 100)).rotation(45).scale((2, 2)) \\
        ...     .yoyo().loop(-1).play()
    """

    def position(self, end: tuple[float, float]) -> Self:
        """Add a position track (vector ``(x, y)``).

        Args:
            end: Target position ``(x, y)``.

        Returns:
            Self, for chaining.
        """
        t = self.target
        self._add(
            "position",
            lambda: t.local.position,
            lambda v: t.set_position(v[0], v[1]),
            end,
            is_vector=True,
        )
        return self

    def rotation(self, end: float) -> Self:
        """Add a rotation track (degrees, scalar).

        Args:
            end: Target angle in degrees.

        Returns:
            Self, for chaining.
        """
        t = self.target
        self._add(
            "rotation",
            lambda: float(t.local.rotation),
            lambda v: t.set_rotation(float(v)),
            float(end),
            is_vector=False,
        )
        return self

    def scale(self, end: tuple[float, float]) -> Self:
        """Add a scale track (vector ``(x, y)``).

        Args:
            end: Target scale ``(x, y)``.

        Returns:
            Self, for chaining.
        """
        t = self.target
        self._add(
            "scale",
            lambda: t.local.scale,
            lambda v: t.set_scale(v[0], v[1]),
            end,
            is_vector=True,
        )
        return self

    def _add(
        self,
        prop: str,
        getter: Getter,
        setter: Setter,
        end: Any,
        *,
        is_vector: bool,
    ) -> None:
        """Internal: append a new track to ``self.tracks``."""
        self.tracks.append(
            _Track(
                prop_key=(id(self.target), prop),
                getter=getter,
                setter=setter,
                start=None,
                end=end,
                is_vector=is_vector,
            )
        )


class SequenceTween:
    """Play children one by one (sequential).

    Attributes:
        id: Internal ID (assigned by the service).
        children: List of child playables.
        index: Index of the currently running child.
        on_complete_cbs: Callbacks fired when the sequence finishes.
        alive: ``True`` until killed.
        playing: ``True`` while running.
        tag: Tag for lookup.
    """

    __slots__ = (
        "_service",
        "alive",
        "children",
        "id",
        "index",
        "on_complete_cbs",
        "playing",
        "tag",
    )

    def __init__(self, service: TweenAnimation, children: list[Any]) -> None:
        """Initialize a sequence with a list of children.

        Args:
            service: ``TweenAnimation`` that will run it.
            children: List of playables.
        """
        self._service = service
        self.id = 0
        self.children = list(children)
        self.index = 0
        self.on_complete_cbs: list[Callback] = []
        self.alive = True
        self.playing = False
        self.tag: str | None = None

    def on_complete(self, callback: Callback) -> Self:
        """Register a callback invoked when the sequence finishes.

        Args:
            callback: Function taking no arguments.

        Returns:
            Self, for chaining.
        """
        self.on_complete_cbs.append(callback)
        return self

    def play(self) -> Self:
        """Register the sequence with the service and start the first child.

        Returns:
            Self, for chaining.
        """
        self._service._register_sequence(self)
        return self

    def kill(self) -> None:
        """Stop the sequence and kill its running child."""
        self._service._kill_sequence(self)

    @property
    def is_alive(self) -> bool:
        """True if the sequence is alive and playing."""
        return self.alive and self.playing


class ParallelTween:
    """Play children simultaneously; finishes when all children finish.

    Attributes:
        id: Internal ID.
        children: List of child playables.
        remaining: Number of children not yet finished.
        on_complete_cbs: Callbacks fired when the parallel finishes.
        alive: ``True`` until killed.
        playing: ``True`` while running.
        tag: Tag for lookup.
    """

    __slots__ = (
        "_service",
        "alive",
        "children",
        "id",
        "on_complete_cbs",
        "playing",
        "remaining",
        "tag",
    )

    def __init__(self, service: TweenAnimation, children: list[Any]) -> None:
        """Initialize a parallel with a list of children.

        Args:
            service: ``TweenAnimation`` that will run it.
            children: List of playables to run simultaneously.
        """
        self._service = service
        self.id = 0
        self.children = list(children)
        self.remaining = 0
        self.on_complete_cbs: list[Callback] = []
        self.alive = True
        self.playing = False
        self.tag: str | None = None

    def on_complete(self, callback: Callback) -> Self:
        """Register a callback invoked when the parallel finishes.

        Args:
            callback: Function taking no arguments.

        Returns:
            Self, for chaining.
        """
        self.on_complete_cbs.append(callback)
        return self

    def play(self) -> Self:
        """Register the parallel with the service and play all children.

        Returns:
            Self, for chaining.
        """
        self._service._register_parallel(self)
        return self

    def kill(self) -> None:
        """Stop the parallel and kill all its children."""
        self._service._kill_parallel(self)

    @property
    def is_alive(self) -> bool:
        """True if the parallel is alive and playing."""
        return self.alive and self.playing


def make_property_tween(
    service: TweenAnimation,
    getter: Getter,
    setter: Setter,
    end: Any,
    *,
    duration: float,
    easing: str | EaseFn,
    time_base: TimeBase,
    is_vector: bool | None = None,
    tag: str | None = None,
) -> Tween:
    """Factory for a single-property ``Tween``.

    Args:
        service: ``TweenAnimation`` that will run it.
        getter: Function to read the current value.
        setter: Function to write the new value.
        end: Target value.
        duration: Tween duration in seconds.
        easing: Easing name or function.
        time_base: Time base.
        is_vector: ``True`` for an ``(x, y)`` tuple; ``None`` = auto-detect.
        tag: Tag for lookup.

    Returns:
        Tween: Tween instance (not played yet).
    """
    tw = Tween(
        service,
        duration=duration,
        ease=get_easing(easing),
        time_base=time_base,
        tag=tag,
    )
    if is_vector is None:
        sample = getter()
        is_vector = isinstance(sample, tuple) and len(sample) == 2
    tw.tracks.append(
        _Track(
            prop_key=(id(setter), "raw"),
            getter=getter,
            setter=setter,
            start=None,
            end=end,
            is_vector=bool(is_vector),
        )
    )
    return tw
