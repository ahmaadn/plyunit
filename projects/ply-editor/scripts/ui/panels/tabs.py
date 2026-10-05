from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

from imgui_bundle import imgui

from scripts.state.document import Document
from scripts.ui.panel import Panel

logger = logging.getLogger(__name__)


class TabActionKind(Enum):
    """Types of actions the user can request through the tab bar."""

    ACTIVATE = auto()
    CLOSE = auto()
    CLOSE_OTHERS = auto()
    CLOSE_ALL = auto()
    SAVE = auto()
    NEW_MAP = auto()


@dataclass(slots=True)
class TabAction:
    """An action request on a tab.

    Attributes:
        kind: Action type.
        index: Target tab index; ``-1`` for global actions.
    """

    kind: TabActionKind
    index: int = -1


class TabBar(Panel):
    """Draws the tab bar and collects user actions."""

    def draw(self) -> list[TabAction]:
        """Draw the tab bar.

        Returns:
            List of actions the user requested this frame.
        """
        actions: list[TabAction] = []

        if self.ctx.workspace.is_empty:
            return actions

        flags = int(
            imgui.TabBarFlags_.auto_select_new_tabs
            | imgui.TabBarFlags_.fitting_policy_scroll
            | imgui.TabBarFlags_.no_close_with_middle_mouse_button
        )
        if not imgui.begin_tab_bar("##map_tabs", flags):
            return actions

        suffixes = self.ctx.workspace.unique_suffixes()
        for index, tab in enumerate(list(self.ctx.workspace.tabs)):
            self._draw_tab(index, tab, suffixes.get(index, ""), actions)

        imgui.end_tab_bar()
        self.ctx.workspace._force_select_tab = None
        return actions

    def _draw_tab(
        self,
        index: int,
        tab: Document,
        suffix: str,
        actions: list[TabAction],
    ) -> None:
        """Draw a single tab and its context menu."""
        item_flags = int(imgui.TabItemFlags_.none)
        if self.ctx.workspace._force_select_tab == index:
            item_flags |= int(imgui.TabItemFlags_.set_selected)
        if tab.dirty:
            # ImGui's built-in dot marker clearly shows the unsaved status.
            item_flags |= int(imgui.TabItemFlags_.unsaved_document)

        label = f"{tab.label(unique_suffix=suffix)}###tab{index}"
        opened, still_open = imgui.begin_tab_item(label, True, item_flags)

        if imgui.is_item_hovered():
            imgui.set_tooltip(tab.tooltip)

        self._draw_context_menu(index, actions)

        if opened:
            if index != self.ctx.workspace.active_index:
                actions.append(TabAction(TabActionKind.ACTIVATE, index))
            imgui.end_tab_item()

        if not still_open:
            actions.append(TabAction(TabActionKind.CLOSE, index))

    def _draw_context_menu(self, index: int, actions: list[TabAction]) -> None:
        """Right-click menu on a tab."""
        if not imgui.begin_popup_context_item(f"##tabctx{index}"):
            return

        if imgui.menu_item("Simpan", "Ctrl+S", False)[0]:
            actions.append(TabAction(TabActionKind.SAVE, index))
        imgui.separator()
        if imgui.menu_item("Tutup", "Ctrl+W", False)[0]:
            actions.append(TabAction(TabActionKind.CLOSE, index))
        if imgui.menu_item("Tutup Lainnya", "", False)[0]:
            actions.append(TabAction(TabActionKind.CLOSE_OTHERS, index))
        if imgui.menu_item("Tutup Semua", "", False)[0]:
            actions.append(TabAction(TabActionKind.CLOSE_ALL))
        imgui.separator()
        if imgui.menu_item("Map Baru", "Ctrl+N", False)[0]:
            actions.append(TabAction(TabActionKind.NEW_MAP))

        imgui.end_popup()


__all__ = ["TabAction", "TabActionKind"]
