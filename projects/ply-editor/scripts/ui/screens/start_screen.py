"""Start screen: recent projects and an open-folder action.

Shown when the editor has no active project — on first launch, or after
the user chooses ``File > Open Project``. When ``last_project`` in the
global config is still valid, the application opens it immediately and
this screen is skipped.
"""

from __future__ import annotations

import logging
import time

from imgui_bundle import imgui

from scripts import events
from scripts.ui.panel import Panel

logger = logging.getLogger(__name__)


def _format_age(timestamp: float) -> str:
    """Format a timestamp as a short relative age.

    Args:
        timestamp: Unix time in seconds. Non-positive values yield an
            empty string.

    Returns:
        An empty string when ``timestamp`` is non-positive, otherwise a
        short relative phrase (``"recently"``, or minutes, hours, or
        days ago).
    """
    if timestamp <= 0:
        return ""
    delta = max(0.0, time.time() - timestamp)
    if delta < 60:
        return "recently"
    if delta < 3600:
        return f"{int(delta // 60)} minutes ago"
    if delta < 86400:
        return f"{int(delta // 3600)} hours ago"
    return f"{int(delta // 86400)} days ago"


class StartScreen(Panel):
    """Project picker shown before a project is open.

    Attributes:
        config: Global config holding the recent-project list.
        on_open: Callback ``(path) -> bool`` invoked when the user picks
            a project. A false return means opening failed and an error
            is shown.
        on_project: Callback invoked by the open-folder button.
        error: Last error message, or an empty string.

    Events:
        APP_OPEN_PROJECT_BY_PATH
        APP_OPEN_FOLDER_PROJECT
    """

    def __init__(self) -> None:
        self.error: str = ""
        self._pending_removal: str | None = None

    def draw(self) -> None:
        """Draw the start screen filling the main viewport."""
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.work_pos)
        imgui.set_next_window_size(viewport.work_size)
        flags = int(
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_bring_to_front_on_focus
        )

        imgui.begin("##start_screen", None, flags)

        imgui.dummy(imgui.ImVec2(0, 24))
        imgui.text("RyUnit Map Editor")
        imgui.text_disabled(
            "Buka sebuah folder sebagai project untuk mulai mengedit peta."
        )
        imgui.dummy(imgui.ImVec2(0, 16))

        if imgui.button("Buka Folder...", imgui.ImVec2(180, 34)):
            # start = self.config.valid_last_project()
            self.bus.publish(events.APP_OPEN_FOLDER_PROJECT)
            # self.picker.show(start)

        if self.error:
            imgui.dummy(imgui.ImVec2(0, 8))
            imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(1.0, 0.4, 0.4, 1.0))
            imgui.text_wrapped(self.error)
            imgui.pop_style_color()

        imgui.dummy(imgui.ImVec2(0, 20))
        imgui.separator()
        imgui.text("Project Terakhir")
        imgui.dummy(imgui.ImVec2(0, 6))

        self._draw_recents()

        imgui.end()

        if self._pending_removal is not None:
            self.ctx.global_config.remove_project(self._pending_removal)
            self._pending_removal = None

    def _draw_recents(self) -> None:
        """Draw the recent-project list, or a placeholder when empty."""
        if not self.ctx.global_config.recent_projects:
            imgui.text_disabled("(belum ada project yang pernah dibuka)")
            return

        imgui.begin_child(
            "##recents", imgui.ImVec2(0, 0), int(imgui.ChildFlags_.borders)
        )
        for index, entry in enumerate(self.ctx.global_config.recent_projects):
            exists = entry.exists
            if not exists:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(0.6, 0.6, 0.6, 1.0)
                )

            clicked, _ = imgui.selectable(
                f"{entry.name}##recent{index}",
                False,
                imgui.SelectableFlags_.allow_double_click,
            )
            if not exists:
                imgui.pop_style_color()

            imgui.same_line()
            imgui.text_disabled(entry.path)
            age = _format_age(entry.opened_at)
            if age:
                imgui.same_line()
                imgui.text_disabled(f"- {age}")
            if not exists:
                imgui.same_line()
                imgui.text_disabled("[folder hilang]")

            imgui.same_line(imgui.get_window_width() - 40)
            if imgui.small_button(f"X##remove{index}"):
                self._pending_removal = entry.path

            if clicked and exists:
                self.bus.publish(events.APP_OPEN_PROJECT_BY_PATH, path=entry.path)
            elif clicked and not exists:
                self.error = f"Folder tidak ditemukan: {entry.path}"

        imgui.end_child()


__all__ = ["StartScreen"]
