"""Base class for editor UI panels."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Panel(ABC):
    """One docked or floating piece of editor UI."""

    @abstractmethod
    def draw(self) -> None:
        """Draw the panel.

        Docked panels draw content only (the caller owns
        ``imgui.begin``/``imgui.end``). Floating panels own their whole
        window.
        """
