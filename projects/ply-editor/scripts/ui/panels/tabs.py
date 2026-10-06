from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from imgui_bundle import imgui

from scripts.ui import icons
from scripts.ui.panel import Panel
from scripts.ui.text_utils import elide_text

if TYPE_CHECKING:
    from scripts.state.document import Document

logger = logging.getLogger(__name__)

# Max width of a tab label, in "em" (multiples of the current font size),
# so it scales with the font / DPI instead of being a fixed pixel value.
TAB_LABEL_MAX_EM = 12.0


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
            # Dropdown button listing every tab: lets the user jump to a tab
            # that is scrolled out of view.
            | imgui.TabBarFlags_.tab_list_popup_button
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
        doc: Document,
        suffix: str,
        actions: list[TabAction],
    ) -> None:
        """Draw a single tab and its context menu."""
        item_flags = int(imgui.TabItemFlags_.none)
        if self.ctx.workspace._force_select_tab == index:
            item_flags |= int(imgui.TabItemFlags_.set_selected)
        if doc.dirty:
            # ImGui's built-in dot marker clearly shows the unsaved status.
            item_flags |= int(imgui.TabItemFlags_.unsaved_document)

        full_text = icons.with_icon(
            icons.icon_for_document_kind(doc.kind), doc.label(unique_suffix=suffix)
        )
        max_width = imgui.get_font_size() * TAB_LABEL_MAX_EM
        shown_text = elide_text(full_text, max_width)

        # Stable ID per document (NOT per index). With an index-based ID,
        # closing a tab on the left shifts every ID after it, so ImGui's
        # remembered selection / scroll position lands on the wrong tab.
        # If Document has its own uid, prefer that over id(tab).
        label = f"{shown_text}###tab{id(doc)}"
        opened, still_open = imgui.begin_tab_item(label, True, item_flags)

        if imgui.is_item_hovered():
            if shown_text == full_text:
                imgui.set_tooltip(doc.tooltip)
            else:
                imgui.set_tooltip(f"{full_text}\n{doc.tooltip}")

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

        if imgui.menu_item("Save", "Ctrl+S", False)[0]:
            actions.append(TabAction(TabActionKind.SAVE, index))
        imgui.separator()
        if imgui.menu_item("Close", "Ctrl+W", False)[0]:
            actions.append(TabAction(TabActionKind.CLOSE, index))

        imgui.end_popup()


__all__ = ["TabAction", "TabActionKind"]
