from __future__ import annotations

from imgui_bundle import icons_fontawesome_6 as icons_fa, imgui

from scripts.state.ui import StatusType
from scripts.ui.layout import STATUS_BAR_HEIGHT
from scripts.ui.panel import Panel


class StatusBar(Panel):
    """Draws the status message strip at the bottom of the window."""

    def draw(self) -> None:
        """Draw the status strip."""
        viewport = imgui.get_main_viewport()
        height = STATUS_BAR_HEIGHT
        imgui.set_next_window_pos(
            imgui.ImVec2(
                viewport.work_pos.x, viewport.work_pos.y + viewport.work_size.y - height
            )
        )
        imgui.set_next_window_size(imgui.ImVec2(viewport.work_size.x, height))
        flags = int(
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_saved_settings
        )
        imgui.begin("##status", None, flags)

        status = self.ctx.ui
        if status.status_type == StatusType.ERROR:
            imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(1.0, 0.4, 0.4, 1.0))
            imgui.text(f"{icons_fa.ICON_FA_CIRCLE_XMARK} {status.status_msg}")
            imgui.pop_style_color()  # imgui.Col_.text
        elif status.status_type == StatusType.INFO:
            imgui.text(f"{icons_fa.ICON_FA_INFO} {status.status_msg}")
        elif status.status_type == StatusType.WARNING:
            imgui.text(f"{icons_fa.ICON_FA_TRIANGLE_EXCLAMATION} {status.status_msg}")
        else:
            imgui.text(status.status_msg)

        imgui.end()


__all__ = ["StatusBar"]
