"""raylib input backend: action map for the keyboard.

Defines the :class:`Input` class which maps actions to keyboard
keys, supports virtual axes, and defers ``key.*`` events to
:class:`~plyunit.events.event_bus.EventBus`.

Gamepads are a separate service (``Gamepad``); they are not part of
this action map.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyray as pr

from plyunit.backends.interfaces import IInput
from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from plyunit.events.event_bus import EventBus
    from plyunit.services.input.action_event import AxisBinding, InputEvents


__all__ = ("Input",)

logger = logging.getLogger(__name__)


class Input(ServiceUnit, IInput):
    """Action map for the keyboard.

    Service name ``Input``; query with ``@Input``.

    Attributes:
        actions: Mapping of actions to sets of keyboard key codes.
        emit_to_bus: Whether events are deferred to the EventBus.
    """

    def __init__(self, *, emit_to_bus: bool = False) -> None:
        """Initialize an Input instance with an empty action map."""
        super().__init__("Input", tags={"service", "input"})
        self.actions: dict[str, set[int]] = {}
        self.emit_to_bus: bool = emit_to_bus
        self._axes: dict[str, AxisBinding] = {}
        self._event_names: dict[str, InputEvents] = {}
        self._app = None
        self._bus = None

    def on_attach(self, app) -> None:
        """Remember the owning app."""
        self._app = app

        bus = app.one_or_none("@EventBus", scope="global")
        if bus:
            self._bus = bus
        if bus is None and self.emit_to_bus:
            self._bus = None
            self.emit_to_bus = False
            logger.info("Event bus not found and emit to bus auto disable")

    def on_detach(self, app) -> None:
        """Forget the owning app and the cached EventBus."""
        self._app = None
        self._bus = None

    def _events_for(self, action: str) -> InputEvents:
        """Return the cached event names for ``action``.

        Args:
            action: Name of the action.

        Returns:
            InputEvents: Pre-built ``key.*`` event names.
        """
        events = self._event_names.get(action)
        if events is None:
            from plyunit.services.input.action_event import InputEvents

            events = self._event_names[action] = InputEvents.for_action(action)
        return events

    def update(self, dt: float) -> None:
        """Poll all actions and defer ``key.*`` events to the EventBus.

        An action is only polled for an event when something is
        listening to it, which avoids needless raylib calls.

        Args:
            dt: Delta time of the current frame, in seconds. Not
                used directly; raylib polling is frame-based.
        """
        if not self._bus or not self.emit_to_bus or not self.actions:
            return

        first_step = self._allow_edge()
        for action in self.actions:
            self._emit_action(self._bus, action, first_step)

    def _emit_action(self, bus: EventBus, action: str, first_step: bool) -> None:
        """Defer every ``key.<action>.*`` event that fired this frame.

        Args:
            bus: Target EventBus instance.
            action: Name of the action to poll.
            first_step: Whether this is the first fixed step; edge
                events (pressed/released/repeat) only fire then.
        """
        events = self._events_for(action)
        polls = (
            (events.pressed, self._pressed, True),
            (events.down, self._down, False),
            (events.released, self._released, True),
            (events.repeat, self._repeat, True),
        )
        for name, poll, edge_only in polls:
            if edge_only and not first_step:
                continue
            if bus.has_listeners(name) and poll(action):
                bus.defer(name, action=action, device="Input")

    def map(self, action: str, *keys: int) -> None:
        """Bind an action to keyboard keys.

        Examples::

            input.map("jump", pr.KEY_SPACE, pr.KEY_UP)

        Args:
            action: Name of the action to map.
            *keys: One or more raylib keyboard key codes.
        """
        self.actions.setdefault(action, set()).update(keys)

    def unmap(self, action: str, *keys: int) -> None:
        """Unbind an action or specific keyboard keys from an action.

        If ``keys`` is empty, the entire action is removed. If
        ``keys`` are given, only those keys are unbound; the action
        is removed when no keys remain.

        Args:
            action: Name of the action to unbind.
            *keys: Specific keyboard keys to unbind (optional).
        """
        bound_keys = self.actions.get(action)
        if bound_keys is None:
            return
        bound_keys.difference_update(keys)
        if not keys or not bound_keys:
            del self.actions[action]

    def map_axis(
        self,
        name: str,
        *,
        key_neg: Sequence[int] | None = None,
        key_pos: Sequence[int] | None = None,
    ) -> None:
        """Define a 1D virtual axis from keyboard keys.

        Args:
            name: Name of the virtual axis.
            key_neg: Keyboard keys for the negative direction.
            key_pos: Keyboard keys for the positive direction.
        """
        from plyunit.services.input.action_event import AxisBinding

        self._axes[name] = AxisBinding(
            key_neg=tuple(key_neg or ()),
            key_pos=tuple(key_pos or ()),
        )

    def _allow_edge(self) -> bool:
        """Check whether edge polling is allowed on this substep.

        Edge polling only runs on the first fixed step within the
        current wall-clock frame. Without an App (isolated unit
        tests), edges stay active.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        app = self._app
        return app is None or bool(app.is_first_fixed_step)

    def _pressed(self, action: str) -> bool:
        """Edge-press check without the fixed-step gate."""
        return any(map(pr.is_key_pressed, self.actions.get(action, ())))

    def _down(self, action: str) -> bool:
        """Held-down check."""
        return any(map(pr.is_key_down, self.actions.get(action, ())))

    def _released(self, action: str) -> bool:
        """Edge-release check without the fixed-step gate."""
        return any(map(pr.is_key_released, self.actions.get(action, ())))

    def _repeat(self, action: str) -> bool:
        """Auto-repeat check without the fixed-step gate."""
        return any(map(pr.is_key_pressed_repeat, self.actions.get(action, ())))

    def is_pressed(self, action: str) -> bool:
        """Check whether an action was just pressed (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action was pressed this frame.
        """
        return self._allow_edge() and self._pressed(action)

    def is_pressed_repeat(self, action: str) -> bool:
        """Check whether an action is pressed with auto-repeat (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action repeated this frame.
        """
        return self._allow_edge() and self._repeat(action)

    def is_down(self, action: str) -> bool:
        """Check whether an action is currently held down.

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action is currently held.
        """
        return self._down(action)

    def is_released(self, action: str) -> bool:
        """Check whether an action was just released (edge).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action was released this frame.
        """
        return self._allow_edge() and self._released(action)

    def is_up(self, action: str) -> bool:
        """Check whether none of an action's keys are pressed.

        Unmapped actions return ``False``.

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if every key of the action is up.
        """
        keys = self.actions.get(action)
        return bool(keys) and all(map(pr.is_key_up, keys))

    def get_axis(self, left: str, right: str | None = None) -> float:
        """Get an axis value from two action names or one named axis.

        If ``right`` is ``None``, read the virtual axis defined via
        :meth:`map_axis`. Otherwise, combine two discrete actions
        into a ``-1.0`` / ``0.0`` / ``1.0`` value.

        Args:
            left: Negative action name (or the axis name when
                ``right`` is ``None``).
            right: Positive action name (optional).

        Returns:
            float: Axis value between ``-1.0`` and ``1.0``.
        """
        if right is None:
            return self._named_axis(left)
        return float(self._down(right)) - float(self._down(left))

    def _named_axis(self, name: str) -> float:
        """Compute the value of a named virtual axis.

        Args:
            name: Name of the virtual axis defined via
                :meth:`map_axis`.

        Returns:
            float: Axis value between ``-1.0`` and ``1.0``
                (``0.0`` when not yet defined).
        """
        binding = self._axes.get(name)
        if binding is None:
            return 0.0
        positive = any(map(pr.is_key_down, binding.key_pos))
        negative = any(map(pr.is_key_down, binding.key_neg))
        return float(positive) - float(negative)

    def get_vector(self, axis_x: str, axis_y: str) -> tuple[float, float]:
        """Get an X and Y axis pair as a 2D vector.

        Args:
            axis_x: Action/axis name for the horizontal component.
            axis_y: Action/axis name for the vertical component.

        Returns:
            tuple[float, float]: The ``(x, y)`` pair.
        """
        return (self.get_axis(axis_x), self.get_axis(axis_y))
