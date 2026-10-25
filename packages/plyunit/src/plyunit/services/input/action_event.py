from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class InputEvents(NamedTuple):
    """Pre-built ``key.*`` event names for one action."""

    pressed: str
    down: str
    released: str
    repeat: str

    @classmethod
    def for_action(cls, action: str) -> InputEvents:
        """Build the event names for ``action``.

        Args:
            action: Name of the action.

        Returns:
            InputEvents: The four event names for the action.
        """
        return cls(
            f"key.{action}.pressed",
            f"key.{action}.down",
            f"key.{action}.released",
            f"key.{action}.repeat",
        )


class MouseEvents(NamedTuple):
    """A mouse button with its pre-built ``mouse.*`` event names."""

    action: str
    code: int
    pressed: str
    down: str
    released: str

    @classmethod
    def for_action(cls, action: str, code: int) -> MouseEvents:
        """Build the event names for ``action``.

        Args:
            action: Name of the action.
            code: raylib mouse button constant.

        Returns:
            MouseEvents: The three event names for the action.
        """
        return cls(
            action=action,
            code=code,
            pressed=f"mouse.{action}.pressed",
            down=f"mouse.{action}.down",
            released=f"mouse.{action}.released",
        )


@dataclass(frozen=True, slots=True)
class AxisBinding:
    """Definition of a 1D virtual axis made of keyboard keys.

    Attributes:
        key_neg: Keyboard keys for the negative direction.
        key_pos: Keyboard keys for the positive direction.
    """

    key_neg: tuple[int, ...] = ()
    key_pos: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, list[int]]:
        """Serialize to a JSON-friendly dict.

        Returns:
            dict[str, list[int]]: The binding using the on-disk schema.
        """
        return {"key_neg": list(self.key_neg), "key_pos": list(self.key_pos)}
