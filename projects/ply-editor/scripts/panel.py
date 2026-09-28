from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.context import AppContext


class Element(ABC):
    """One docked or floating piece of editor UI.

    Attributes:
        name: Window/id label; also the shell's lookup key.
        visible: When ``False`` the shell skips the element entirely.
        floating: True when :meth:`draw` owns its window.
        window_flags: Extra ``imgui.WindowFlags_`` for docked windows.
        elements: Child elements, bound together with this one.
    """

    def __init__(self, ctx: AppContext) -> None:
        """Initialize identity, visibility and window behaviour."""
        self.ctx = ctx

    @abstractmethod
    def draw(self) -> None:
        """Draw the element.

        Docked elements: content only (the caller owns ``begin``/``end``).
        Floating elements: the full window, menu bar, or popup.
        """
