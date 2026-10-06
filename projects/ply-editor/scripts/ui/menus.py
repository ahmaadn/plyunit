"""The main menu bar: File, View, and Assets menus plus the project title.

The menu is a thin view: every item publishes an intent on the event
bus; the composition root turns intents into commands. The only state
it mutates directly is ephemeral layout state (sidebar visibility and
width), which belongs to the view layer.
"""

from __future__ import annotations

from imgui_bundle import imgui

from scripts.app import events
from scripts.ui import icons
from scripts.ui.layout import DockLayout
from scripts.ui.panel import Panel


class MainMenuBar(Panel):
    """Draws the editor's main menu bar.

    The shared app context and event bus are auto-attached by
    :meth:`Panel.__new__`.

    Args:
        layout: The dock layout (sidebar toggles and widths).
    """

    def __init__(self, layout: DockLayout) -> None:
        """Store the dock layout used by the View menu.

        Args:
            layout: Sidebar visibility and widths.
        """
        self._layout = layout

    def draw(self) -> None:
        """Draw the main menu bar and the centered project title."""
        if not imgui.begin_main_menu_bar():
            return

        if imgui.begin_menu("File"):
            if imgui.menu_item(
                icons.with_icon(icons.FOLDER_OPEN, "Open Folder..."), "", False
            )[0]:
                self.bus.publish(events.APP_OPEN_FOLDER_PROJECT)
            imgui.separator()
            if imgui.menu_item(icons.with_icon(None, "New Map"), "Ctrl+N", False)[0]:
                self.bus.publish(events.APP_NEW_MAP)
            if imgui.menu_item(icons.with_icon(icons.SAVE, "Save"), "Ctrl+S", False)[0]:
                self.bus.publish(events.APP_SAVE)
            imgui.separator()
            if imgui.menu_item(
                icons.with_icon(icons.CLOSE, "Close Project"), "", False
            )[0]:
                self.bus.publish(events.APP_CLOSE_PROJECT)
            imgui.end_menu()

        if imgui.begin_menu("View"):
            clicked, value = imgui.menu_item(
                icons.with_icon(None, "Left Sidebar"), "Ctrl+B", self._layout.show_left
            )
            if clicked:
                self._layout.show_left = value
            clicked, value = imgui.menu_item(
                icons.with_icon(None, "Right Sudebar"),
                "Ctrl+J",
                self._layout.show_right,
            )
            if clicked:
                self._layout.show_right = value
            clicked, value = imgui.menu_item(
                icons.with_icon(None, "Show Tabs"), "", self._layout.show_tabs
            )
            if clicked:
                self._layout.show_tabs = value

            imgui.separator()
            if imgui.menu_item(
                icons.with_icon(icons.REFRESH, "Reset Lebar Sidebar"), "", False
            )[0]:
                self._layout.reset_widths()
            imgui.end_menu()

        if imgui.begin_menu("Assets"):
            if imgui.menu_item(
                icons.with_icon(icons.REFRESH, "Pindai Ulang Folder"), "F5", False
            )[0]:
                self.bus.publish(events.APP_REFRESH_ASSETS)
            imgui.end_menu()

        # Project title, centered in the menu bar. Read live from the
        # project service so it can never go stale.
        name = (
            self.ctx.project.name
            if self.ctx.project and self.ctx.project_active
            else ""
        )
        title = f"Project: {name or '(tanpa project)'}"
        title_size = imgui.calc_text_size(title)
        imgui.same_line((imgui.get_window_width() - title_size.x) * 0.5)
        imgui.text_disabled(title)

        imgui.end_main_menu_bar()


__all__ = ["MainMenuBar"]
