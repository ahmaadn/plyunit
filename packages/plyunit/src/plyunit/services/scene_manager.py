"""Scene stack management with deferred transitions and fade-out/-in behavior."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from plyunit.core.units.scene_unit import SceneUnit
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.events.signal import Signal

if TYPE_CHECKING:
    from plyunit.rendering.renderer import Renderer


class TransitionType(Enum):
    """Kinds of scene transition supported by :class:`SceneManager`."""

    PUSH = auto()
    """Push a new scene on top of the stack."""
    POP = auto()
    """Pop the top scene from the stack."""
    CHANGE = auto()
    """Replace the top scene (pop + push in one operation)."""
    REPLACE_ALL = auto()
    """Clear the whole stack, then push the new scene as root."""


@dataclass
class _Pending:
    """A pending transition to be applied at the end of the frame."""

    kind: TransitionType
    """The requested transition kind."""
    unit: SceneUnit | None = field(default=None)
    """Target scene (for transitions that need one)."""


@dataclass(slots=True)
class SceneTransitionEvent:
    """Event data emitted when a transition is applied.

    Attributes:
        kind: The transition kind that was just applied.
        previous: Active scene before the transition (``None`` if the stack was empty).
        current: Active scene after the transition (``None`` if the stack is empty).
        depth: Number of scenes on the stack after the transition.
    """

    kind: TransitionType
    previous: SceneUnit | None
    current: SceneUnit | None
    depth: int


class SceneManager(ServiceUnit):
    """Manage scene stack with deferred transitions.

    All public methods only queue a transition (deferred). The actual
    transition is executed by ``apply_pending()`` after the fixed-step update.
    """

    MAX_STACK_DEPTH: int = 8
    """Maximum number of scenes allowed on the stack."""

    def __init__(self) -> None:
        """Initialize scene manager, signals, and default transition behavior."""
        super().__init__(name="SceneManager", tags={"service", "scene_manager"})
        self._stack: list[SceneUnit] = []
        self._pending: _Pending | None = None
        self._pending_midpoint: TransitionType | None = None
        self._step_scene: SceneUnit | None = None
        self.on_transition_queued = Signal("on_scene_transition_queued")
        self.on_transition_applied = Signal("on_scene_transition_applied")
        self.on_transition_started = Signal("on_scene_transition_started")
        self.on_transition_midpoint = Signal("on_scene_transition_midpoint")
        self.on_transition_finished = Signal("on_scene_transition_finished")
        self._transition_behavior: SceneController | None = None
        self.set_transition_behavior(SceneController(duration=0.25))

    @property
    def current(self) -> SceneUnit | None:
        """Get currently active scene.

        Returns:
            SceneUnit | None: Scene at the top of the stack, or ``None``
                if the stack is empty.
        """
        return self._stack[-1] if self._stack else None

    @property
    def depth(self) -> int:
        """Get current stack depth.

        Returns:
            int: Number of scenes on the stack.
        """
        return len(self._stack)

    @property
    def transition_behavior(self) -> SceneController | None:
        """Get active transition behavior.

        Returns:
            SceneController | None: The currently installed transition behavior.
        """
        return self._transition_behavior

    def set_transition_behavior(self, behavior: SceneController | None) -> None:
        """Set or replace transition behavior.

        Args:
            behavior: New transition behavior. Pass ``None`` to detach
                the behavior.
        """
        if self._transition_behavior is behavior:
            return

        if self._transition_behavior is not None:
            self._transition_behavior.unbind()

        self._transition_behavior = behavior
        if behavior is not None:
            behavior.bind(self)

    def request_transition(
        self,
        kind: TransitionType,
        scene_factory: Callable[[], SceneUnit] | None = None,
    ) -> bool:
        """Request transition via the installed behavior.

        Args:
            kind: The requested transition kind.
            scene_factory: Factory that creates the new scene for
                transitions that need a target scene.

        Returns:
            bool: ``True`` if the request was accepted, ``False`` if the
            behavior is busy.

        Raises:
            RuntimeError: If no transition behavior is installed.
        """
        if self._transition_behavior is None:
            raise RuntimeError("Scene transition behavior belum dipasang.")
        return self._transition_behavior.request(kind, scene_factory)

    def request_push(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Request push transition via active behavior.

        Args:
            scene_factory: Factory that creates the scene to push.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request_transition(TransitionType.PUSH, scene_factory)

    def request_pop(self) -> bool:
        """Request pop transition via active behavior.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request_transition(TransitionType.POP)

    def request_change(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Request change transition via active behavior.

        Args:
            scene_factory: Factory that creates the replacement scene for
                the stack top.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request_transition(TransitionType.CHANGE, scene_factory)

    def request_replace_all(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Request replace_all transition via active behavior.

        Args:
            scene_factory: Factory that creates the new scene as the sole
                stack entry.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request_transition(TransitionType.REPLACE_ALL, scene_factory)

    def push(self, unit: SceneUnit) -> None:
        """Queue push operation for a scene.

        Args:
            unit: Scene to push onto the top of the stack.
        """
        self._queue_transition(TransitionType.PUSH, unit)

    def pop(self) -> None:
        """Queue pop operation for the top scene."""
        self._queue_transition(TransitionType.POP)

    def change(self, unit: SceneUnit) -> None:
        """Queue change operation for the top scene.

        Args:
            unit: Replacement scene for the top of the stack.
        """
        self._queue_transition(TransitionType.CHANGE, unit)

    def replace_all(self, unit: SceneUnit) -> None:
        """Queue replace_all operation for the stack.

        Args:
            unit: New scene that becomes the only scene on the stack.
        """
        self._queue_transition(TransitionType.REPLACE_ALL, unit)

    def begin_step(self) -> None:
        """Open spawn gate on current scene (App calls this at fixed-step start)."""
        self._step_scene = self.current
        if self._step_scene is not None:
            self._step_scene._begin_step()

    def end_step(self) -> None:
        """Close spawn gate on the scene that began this step."""
        if self._step_scene is not None:
            self._step_scene._end_step()
            self._step_scene = None

    def update(self, dt: float) -> None:
        """Update transition behavior and current scene.

        Args:
            dt: Delta time in seconds.
        """
        if self._transition_behavior is not None:
            self._transition_behavior.update(dt)
        if self.current is not None:
            self.current._dispatch_update(dt)

    def render(self, renderer: Renderer) -> None:
        """Forward render submission to current scene.

        Args:
            renderer: Renderer to submit to.
        """
        if self.current is not None:
            self.current.dispatch_render(renderer)

    # ---------------------------------------------------- apply pending (internal)

    def _notify_transition_started(self, kind: TransitionType) -> None:
        """Emit signal when transition behavior starts.

        Args:
            kind: The transition kind that started running.
        """
        self.on_transition_started.emit(kind)

    def _notify_transition_midpoint(
        self,
        kind: TransitionType,
        current: SceneUnit | None,
    ) -> None:
        """Emit signal at transition midpoint.

        Args:
            kind: The transition kind currently running.
            current: Active scene after the transition operation was applied.
        """
        self.on_transition_midpoint.emit(kind, current)

    def _notify_transition_finished(self, current: SceneUnit | None) -> None:
        """Emit signal when transition behavior finishes.

        Args:
            current: Active scene when the transition ends.
        """
        self.on_transition_finished.emit(current)

    def _queue_transition(
        self, kind: TransitionType, unit: SceneUnit | None = None
    ) -> None:
        """Store a transition request as pending operation.

        Args:
            kind: Transition kind.
            unit: Target scene if the transition requires one.
        """
        self._pending = _Pending(kind, unit)
        self._pending_midpoint = None
        self.on_transition_queued.emit(kind, unit)

    def apply_pending(self) -> None:
        """Apply the transition queued during this fixed step."""
        if self._pending is None:
            return
        self._apply_pending()
        if self._pending_midpoint is not None:
            kind = self._pending_midpoint
            self._pending_midpoint = None
            self._notify_transition_midpoint(kind, self.current)

    def _apply_pending(self) -> None:
        """Apply pending transition operation.

        Emits ``on_transition_applied`` after the operation completes.
        """
        if self._pending is None:
            return

        pending = self._pending
        self._pending = None
        previous = self.current

        match pending.kind:
            case TransitionType.PUSH:
                self._do_push(pending.unit)
            case TransitionType.POP:
                self._do_pop()
            case TransitionType.CHANGE:
                self._do_change(pending.unit)
            case TransitionType.REPLACE_ALL:
                self._do_replace_all(pending.unit)

        self.on_transition_applied.emit(
            SceneTransitionEvent(
                kind=pending.kind,
                previous=previous,
                current=self.current,
                depth=len(self._stack),
            )
        )

    def _do_push(self, unit: SceneUnit | None) -> None:
        """Push scene to stack and call ``load``.

        Args:
            unit: Target scene.

        Raises:
            RuntimeError: If the stack reaches ``MAX_STACK_DEPTH``.
        """
        if unit is None:
            return
        if len(self._stack) >= self.MAX_STACK_DEPTH:
            raise RuntimeError(
                f"SceneManager stack overflow (max {self.MAX_STACK_DEPTH}). "
                "Terlalu banyak scene di-push tanpa pop."
            )
        self._stack.append(unit)
        unit.load()

    def _do_pop(self) -> None:
        """Pop top scene from stack and call ``unload``."""
        if not self._stack:
            return
        unit = self._stack.pop()
        unit.unload()

    def _do_change(self, unit: SceneUnit | None) -> None:
        """Replace top scene with a new scene.

        Args:
            unit: Replacement scene.
        """
        if unit is None:
            return
        if self._stack:
            old = self._stack.pop()
            old.unload()
        self._stack.append(unit)
        unit.load()

    def _do_replace_all(self, unit: SceneUnit | None) -> None:
        """Unload all scenes and install a new root scene.

        Args:
            unit: New scene that becomes the sole stack entry.
        """
        if unit is None:
            return
        # Exit all scenes from top to bottom
        for existing in reversed(self._stack):
            existing.unload()
        self._stack.clear()
        self._stack.append(unit)
        unit.load()

    # ----------------------------------------------------------------- cleanup

    def shutdown(self) -> None:
        """Cancel pending transitions and unload all scenes from top to bottom."""
        self._pending = None
        self._pending_midpoint = None
        self._step_scene = None
        failures: list[BaseException] = []
        while self._stack:
            unit = self._stack.pop()
            try:
                unit.unload()
            except BaseException as exc:
                failures.append(exc)
        behavior = self._transition_behavior
        self._transition_behavior = None
        if behavior is not None:
            try:
                behavior.unbind()
            except BaseException as exc:
                failures.append(exc)
        if failures:
            raise failures[0]

    def __repr__(self) -> str:
        """Build debug representation.

        Returns:
            str: Summary of the scene stack contents.
        """
        names = [u.name for u in self._stack]
        return f"SceneManager(stack={names})"


class SceneController:
    """Handle fade-based transition behavior for ``SceneManager``.

    This behavior separates visual timing (the fade) from the scene
    manager's stack operations, then executes the operation at the fade
    midpoint.
    """

    @dataclass
    class _QueuedTransition:
        """A transition queued by :class:`SceneController`."""

        kind: TransitionType
        """The queued transition kind."""
        scene_factory: Callable[[], SceneUnit] | None = None
        """Factory for the target scene (for transitions that need one)."""

    def __init__(self, duration: float = 0.25) -> None:
        """Initialize the fade transition behavior.

        Args:
            duration: Fade out/in duration in seconds.
        """
        self._scene_manager: SceneManager | None = None
        self.duration = max(0.01, float(duration))
        self.alpha = 0.0
        self.state = "idle"
        self._pending: SceneController._QueuedTransition | None = None

    def bind(self, scene_manager: SceneManager) -> None:
        """Bind behavior to a scene manager.

        Args:
            scene_manager: Target scene manager.
        """
        self._scene_manager = scene_manager

    def unbind(self) -> None:
        """Unbind behavior from manager and reset internal transition state."""
        self._scene_manager = None
        self._pending = None
        self.state = "idle"
        self.alpha = 0.0

    @property
    def busy(self) -> bool:
        """Check whether behavior is processing a transition.

        Returns:
            bool: ``True`` if the state is not ``idle``.
        """
        return self.state != "idle"

    def request(
        self,
        kind: TransitionType,
        scene_factory: Callable[[], SceneUnit] | None = None,
    ) -> bool:
        """Request a new transition.

        Args:
            kind: The requested transition kind.
            scene_factory: Factory that creates the new scene for
                transitions that require a target scene.

        Returns:
            bool: ``True`` if the request was accepted, ``False`` if the
            behavior is still busy.

        Raises:
            ValueError: If the transition requires a scene_factory but none
                was provided.
        """
        if self.busy:
            return False

        if (
            kind
            in (
                TransitionType.PUSH,
                TransitionType.CHANGE,
                TransitionType.REPLACE_ALL,
            )
            and scene_factory is None
        ):
            raise ValueError(f"scene_factory wajib untuk transisi {kind.name}")

        self._pending = SceneController._QueuedTransition(kind, scene_factory)
        self.state = "fading_out"
        if self._scene_manager is not None:
            self._scene_manager._notify_transition_started(kind)
        return True

    def request_push(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Shortcut for push transition request.

        Args:
            scene_factory: Factory that creates the target scene.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request(TransitionType.PUSH, scene_factory)

    def request_pop(self) -> bool:
        """Shortcut for pop transition request.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request(TransitionType.POP)

    def request_change(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Shortcut for change transition request.

        Args:
            scene_factory: Factory that creates the replacement scene.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request(TransitionType.CHANGE, scene_factory)

    def request_replace_all(self, scene_factory: Callable[[], SceneUnit]) -> bool:
        """Shortcut for replace_all transition request.

        Args:
            scene_factory: Factory that creates the new root scene.

        Returns:
            bool: ``True`` if the request was accepted.
        """
        return self.request(TransitionType.REPLACE_ALL, scene_factory)

    def _apply_to_manager(self, pending: _QueuedTransition) -> None:
        """Apply queued transition to bound scene manager.

        Args:
            pending: Pending transition to apply.
        """
        manager = self._scene_manager
        if manager is None:
            return

        scene = pending.scene_factory() if pending.scene_factory is not None else None

        match pending.kind:
            case TransitionType.PUSH:
                if scene is None:
                    return
                manager.push(scene)
            case TransitionType.POP:
                manager.pop()
            case TransitionType.CHANGE:
                if scene is None:
                    return
                manager.change(scene)
            case TransitionType.REPLACE_ALL:
                if scene is None:
                    return
                manager.replace_all(scene)

        manager._pending_midpoint = pending.kind

    def update(self, dt: float) -> None:
        """Update fade state and apply transition at midpoint.

        Args:
            dt: Delta time in seconds.
        """
        if self.state == "idle":
            self.alpha = 0.0
            return

        step = 255.0 * float(dt) / self.duration

        if self.state == "fading_out":
            self.alpha = min(255.0, self.alpha + step)
            if self.alpha >= 255.0 and self._pending is not None:
                pending = self._pending
                self._pending = None
                self._apply_to_manager(pending)
                self.state = "fading_in"
            return

        if self.state == "fading_in":
            self.alpha = max(0.0, self.alpha - step)
            if self.alpha <= 0.0:
                self.state = "idle"
                if self._scene_manager is not None:
                    self._scene_manager._notify_transition_finished(
                        self._scene_manager.current,
                    )
            return

        self.alpha = 0.0
