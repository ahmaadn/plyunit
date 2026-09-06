"""raylib input backend: action map for the keyboard (+ optional gamepad).

Defines the :class:`Input` class which maps actions to keyboard
keys and/or gamepad buttons, supports virtual axes, and defers
``key.*`` events to :class:`~plyunit.events.event_bus.EventBus`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyray as pr

from plyunit.backends.integrations.raylib.input.gamepad import (
    DEFAULT_DEADZONE,
    Gamepad,
    _axis,
    _button,
    apply_deadzone,
)
from plyunit.backends.interfaces import IInput
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils.io import read_json, write_json

if TYPE_CHECKING:
    from collections.abc import Sequence

    from plyunit.events.event_bus import EventBus


__all__ = ("Input",)


class Input(ServiceUnit, IInput):
    """Action map for the keyboard (+ optional gamepad).

    Service name ``Input``; query with ``@Input``.

    Args:
        gamepad: ``True`` / player index / :class:`Gamepad` instance
            to enable gamepad bindings. ``None`` means keyboard
            only.
        deadzone: Default dead zone for virtual axes.

    Attributes:
        actions: Mapping of actions to sets of keyboard key codes.
        deadzone: Default dead zone for virtual axes.
        emit_to_bus: Whether events are deferred to the EventBus.
        gamepad: The active :class:`Gamepad` instance, or ``None``.
    """

    def __init__(
        self,
        *,
        gamepad: bool | Gamepad | None = None,
        deadzone: float = DEFAULT_DEADZONE,
    ) -> None:
        """Initialize an Input instance with an empty action map."""
        super().__init__("Input", tags={"service", "input"})
        self.actions: dict[str, set[int]] = {}
        self._buttons: dict[str, set[str | int]] = {}
        self._axes: dict[str, dict[str, Any]] = {}
        self.deadzone = deadzone
        self.emit_to_bus: bool = True
        self._event_bus: EventBus | None = None
        self.gamepad = self._init_gamepad(gamepad)

    @staticmethod
    def _init_gamepad(gamepad: bool | Gamepad | None) -> Gamepad | None:
        """Create a :class:`Gamepad` instance from the config parameter.

        Args:
            gamepad: ``None`` / ``False`` (no gamepad), ``True``
                (player 0), an integer (player index), or an
                existing :class:`Gamepad` instance.

        Returns:
            Gamepad | None: A :class:`Gamepad` instance, or ``None``
                when disabled.
        """
        if gamepad is None or gamepad is False:
            return None
        if isinstance(gamepad, Gamepad):
            return gamepad
        if isinstance(gamepad, bool) and gamepad:
            return Gamepad(0)
        return Gamepad(gamepad)

    # def _resolve_bus(self) -> EventBus | None:
    #     """Find and cache the global EventBus for deferring events.

    #     Returns:
    #         EventBus | None: The EventBus instance found, or
    #             ``None`` when there is none.
    #     """
    #     if self._event_bus is not None:
    #         return self._event_bus
    #     bus = self.one_or_none("@EventBus", scope="global")
    #     if bus is not None:
    #         self._event_bus = bus
    #     return bus

    def _defer_if_listened(self, bus: EventBus, event_name: str, **kwargs: Any) -> None:
        """Defer an event to the EventBus only when it has listeners.

        Args:
            bus: Target EventBus instance.
            event_name: Name of the event to defer.
            **kwargs: Additional event payload.
        """
        if bus.has_listeners(event_name):
            bus.defer(event_name, **kwargs)

    def _allow_edge(self) -> bool:
        """Check whether edge polling is allowed on this substep.

        Returns ``True`` when there is no App or when this is the
        first fixed step within the current wall-clock frame.

        Returns:
            bool: ``True`` if edge polling is allowed.
        """
        app = self.one_or_none("@App", scope="global")
        return True if app is None else bool(app.is_first_fixed_step)

    def update(self, dt: float) -> None:
        """Poll all actions and defer ``key.*`` events to the EventBus.

        Args:
            dt: Delta time of the current frame, in seconds. Not
                used directly; raylib polling is frame-based.
        """
        if not self.emit_to_bus or not self.actions:
            return
        bus = self.one_or_none("@EventBus", scope="global")
        if bus is None:
            return
        for action in self.actions:
            payload = {"action": action, "device": "input"}
            if self.is_pressed(action):
                self._defer_if_listened(bus, f"key.{action}.pressed", **payload)
            if self.is_down(action):
                self._defer_if_listened(bus, f"key.{action}.down", **payload)
            if self.is_released(action):
                self._defer_if_listened(bus, f"key.{action}.released", **payload)
            if self.is_pressed_repeat(action):
                self._defer_if_listened(bus, f"key.{action}.repeat", **payload)

    def map(
        self,
        action: str,
        *keys: int,
        buttons: Sequence[str | int] | None = None,
    ) -> None:
        """Bind an action to keyboard keys and/or gamepad buttons.

        Examples::

            input.map("jump", pr.KEY_SPACE, pr.KEY_UP)
            input.map("jump", pr.KEY_SPACE, buttons=["a"])

        Args:
            action: Name of the action to map.
            *keys: One or more raylib keyboard key codes.
            buttons: Optional list of gamepad button names.
        """
        if action not in self.actions:
            self.actions[action] = set()
        if keys:
            self.actions[action].update(keys)
        if buttons:
            self._buttons.setdefault(action, set()).update(buttons)

    def unmap(self, action: str, *keys: int) -> None:
        """Unbind an action or specific keyboard keys from an action.

        If ``keys`` is empty, the entire action (including gamepad
        buttons) is removed. If ``keys`` are given, only those keys
        are unbound; the action is removed when no keys remain.

        Args:
            action: Name of the action to unbind.
            *keys: Specific keyboard keys to unbind (optional).
        """
        if action not in self.actions:
            return
        if not keys:
            del self.actions[action]
            self._buttons.pop(action, None)
            return
        for key in keys:
            self.actions[action].discard(key)
        if not self.actions[action] and action not in self._buttons:
            del self.actions[action]

    def map_axis(
        self,
        name: str,
        *,
        key_neg: Sequence[int] | None = None,
        key_pos: Sequence[int] | None = None,
        pad_axis: str | int | None = None,
        pad_buttons_neg: Sequence[str | int] | None = None,
        pad_buttons_pos: Sequence[str | int] | None = None,
        deadzone: float | None = None,
    ) -> None:
        """Define a 1D virtual axis from keys and/or an analog stick.

        Args:
            name: Name of the virtual axis.
            key_neg: Keyboard keys for the negative direction.
            key_pos: Keyboard keys for the positive direction.
            pad_axis: Gamepad analog axis name/constant (optional).
            pad_buttons_neg: Gamepad buttons for the negative direction.
            pad_buttons_pos: Gamepad buttons for the positive direction.
            deadzone: Dead zone override; ``None`` means use
                ``self.deadzone``.
        """
        self._axes[name] = {
            "key_neg": list(key_neg or ()),
            "key_pos": list(key_pos or ()),
            "pad_axis": pad_axis,
            "pad_buttons_neg": list(pad_buttons_neg or ()),
            "pad_buttons_pos": list(pad_buttons_pos or ()),
            "deadzone": self.deadzone if deadzone is None else deadzone,
        }

    def is_pressed(self, action: str) -> bool:
        """Check whether an action was just pressed (edge).

        Checks keyboard keys and gamepad buttons (when active).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action was pressed this frame.
        """
        if not self._allow_edge():
            return False
        if any(pr.is_key_pressed(k) for k in self.actions.get(action, ())):
            return True
        pad = self.gamepad
        if pad is None or not pad.is_available():
            return False
        return any(pad.is_pressed(b) for b in self._buttons.get(action, ()))

    def is_pressed_repeat(self, action: str) -> bool:
        """Check whether an action is pressed with auto-repeat (edge).

        Only checks keyboard keys (gamepad not included).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action repeated this frame.
        """
        if not self._allow_edge():
            return False
        return any(pr.is_key_pressed_repeat(k) for k in self.actions.get(action, ()))

    def is_down(self, action: str) -> bool:
        """Check whether an action is currently held down.

        Checks keyboard keys and gamepad buttons (when active).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action is currently held.
        """
        if any(pr.is_key_down(k) for k in self.actions.get(action, ())):
            return True
        pad = self.gamepad
        if pad is None or not pad.is_available():
            return False
        return any(pad.is_down(b) for b in self._buttons.get(action, ()))

    def is_released(self, action: str) -> bool:
        """Check whether an action was just released (edge).

        Checks keyboard keys and gamepad buttons (when active).

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if the action was released this frame.
        """
        if not self._allow_edge():
            return False
        if any(pr.is_key_released(k) for k in self.actions.get(action, ())):
            return True
        pad = self.gamepad
        if pad is None or not pad.is_available():
            return False
        return any(pad.is_released(b) for b in self._buttons.get(action, ()))

    def is_up(self, action: str) -> bool:
        """Check whether an action is currently not pressed.

        Only checks keyboard keys.

        Args:
            action: Name of the action to check.

        Returns:
            bool: ``True`` if none of the action's keys are pressed.
        """
        return any(pr.is_key_up(k) for k in self.actions.get(action, ()))

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

        value = 0.0
        if self.is_down(left):
            value -= 1.0
        if self.is_down(right):
            value += 1.0
        return value

    def _named_axis(self, name: str) -> float:
        """Compute the value of a named virtual axis from keyboard+gamepad bindings.

        Combines contributions from discrete buttons and the analog
        stick, keeping the value with the largest absolute magnitude.

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
        value = 0.0
        if any(pr.is_key_down(k) for k in binding["key_neg"]):
            value -= 1.0
        if any(pr.is_key_down(k) for k in binding["key_pos"]):
            value += 1.0

        pad = self.gamepad
        if pad is not None and pad.is_available():
            if binding["pad_axis"] is not None:
                raw = pr.get_gamepad_axis_movement(
                    pad.player, _axis(binding["pad_axis"])
                )
                value = _max_abs(value, apply_deadzone(raw, binding["deadzone"]))
            for b in binding["pad_buttons_neg"]:
                if pr.is_gamepad_button_down(pad.player, _button(b)):
                    value = _max_abs(value, -1.0)
            for b in binding["pad_buttons_pos"]:
                if pr.is_gamepad_button_down(pad.player, _button(b)):
                    value = _max_abs(value, 1.0)
        return value

    def get_vector(self, axis_x: str, axis_y: str) -> tuple[float, float]:
        """Get an X and Y axis pair as a 2D vector.

        Args:
            axis_x: Action/axis name for the horizontal component.
            axis_y: Action/axis name for the vertical component.

        Returns:
            tuple[float, float]: The ``(x, y)`` pair.
        """
        return (self.get_axis(axis_x), self.get_axis(axis_y))

    def load(self, path: str | Path) -> None:
        """Load action/axis mappings from a JSON file.

        Supports two schemas: (1) ``{"actions": {...}, "axes": {...}}``
        or (2) the simple ``{action: [keys]}`` format.

        Args:
            path: Path to the JSON file.

        Raises:
            FileNotFoundError: If the file is not found.
            ValueError: If the extension is not ``.json``.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Input mapping file not found: {path}")
        if path.suffix.lower() != ".json":
            raise ValueError(f"Input mapping must be JSON (.json); got {path.suffix!r}")
        data = read_json(path)
        if "actions" in data or "axes" in data:
            for action, binding in (data.get("actions") or {}).items():
                self.map(
                    action,
                    *list(binding.get("keys") or ()),
                    buttons=binding.get("buttons"),
                )
            for name, binding in (data.get("axes") or {}).items():
                self.map_axis(
                    name,
                    key_neg=binding.get("key_neg"),
                    key_pos=binding.get("key_pos"),
                    pad_axis=binding.get("pad_axis"),
                    pad_buttons_neg=binding.get("pad_buttons_neg"),
                    pad_buttons_pos=binding.get("pad_buttons_pos"),
                    deadzone=binding.get("deadzone"),
                )
            return
        for action, keys in data.items():
            self.map(action, *keys)

    def save(self, path: str | Path) -> None:
        """Save action/axis mappings to a JSON file.

        Writes the full ``{"actions": {...}, "axes": {...}}`` schema
        including keyboard keys and gamepad buttons.

        Args:
            file: Destination path for the JSON file.
        """
        path = Path(path)
        data = {
            "actions": {
                name: {
                    "keys": sorted(self.actions.get(name, ())),
                    "buttons": sorted(str(b) for b in self._buttons.get(name, ())),
                }
                for name in set(self.actions) | set(self._buttons)
            },
            "axes": {
                name: {
                    "key_neg": list(b["key_neg"]),
                    "key_pos": list(b["key_pos"]),
                    "pad_axis": b["pad_axis"],
                    "pad_buttons_neg": list(b["pad_buttons_neg"]),
                    "pad_buttons_pos": list(b["pad_buttons_pos"]),
                    "deadzone": b["deadzone"],
                }
                for name, b in self._axes.items()
            },
        }
        write_json(path, data)


def _max_abs(a: float, b: float) -> float:
    """Return the value with the largest absolute magnitude of two values.

    Args:
        a: First value.
        b: Second value.

    Returns:
        float: ``b`` if ``abs(b) > abs(a)``, otherwise ``a``.
    """
    return b if abs(b) > abs(a) else a
