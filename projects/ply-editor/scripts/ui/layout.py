"""Fixed IDE-style window layout: left sidebar, center, right sidebar.

Every panel used to be a floating ImGui window that stacked and covered
the canvas. This module installs a fixed layout instead:

* **Left sidebar** — assets & palette (tile sources).
* **Center** — map tab bar plus canvas (kept transparent so the raylib
  render behind it stays visible).
* **Right sidebar** — properties: layers, physics, objects, autotiles,
  settings.

Both sidebars can be resized with splitters. The center viewport rect
is exposed through :attr:`DockLayout.viewport` so the canvas knows
which area accepts mouse input — without it, clicks on a sidebar would
also paint tiles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from imgui_bundle import imgui

logger = logging.getLogger(__name__)

MIN_SIDEBAR_WIDTH = 180.0
MAX_SIDEBAR_WIDTH = 640.0
MAX_SIDEBAR_FRACTION = 0.4
DEFAULT_LEFT_WIDTH = 300.0
DEFAULT_RIGHT_WIDTH = 340.0
SPLITTER_THICKNESS = 6.0
TOOLBAR_HEIGHT = 40.0
STATUS_BAR_HEIGHT = 26.0
TAB_BAR_HEIGHT = 32.0

MIN_SECTION_FRACTION = 0.15
"""Minimum share of one section in a vertical sidebar split.

Without this limit, dragging a divider all the way makes one browser
vanish entirely and it cannot be recovered without editing
``editor.json``.
"""


@dataclass(slots=True)
class Rect:
    """A rectangle in screen coordinates."""

    x: float
    y: float
    width: float
    height: float

    def contains(self, px: float, py: float) -> bool:
        """Return whether the point lies inside the rectangle."""
        return (
            self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
        )


class DockLayout:
    """Computes and draws the editor's layout skeleton.

    Attributes:
        left_width: Left sidebar width in pixels.
        right_width: Right sidebar width in pixels.
        show_left: Whether the left sidebar is visible.
        show_right: Whether the right sidebar is visible.
        show_tabs: Reserve :data:`TAB_BAR_HEIGHT` above the center area
            for a tab bar (set ``False`` when there is no tab bar).
        viewport: Center canvas area after subtracting sidebars and
            bars.
    """

    def __init__(
        self,
        left_width: float = DEFAULT_LEFT_WIDTH,
        right_width: float = DEFAULT_RIGHT_WIDTH,
    ) -> None:
        """Initialize the layout with the given sidebar widths."""
        self.left_width = left_width
        self.right_width = right_width
        self.show_left = True
        self.show_right = True
        self.show_tabs = False
        self.viewport = Rect(0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def max_sidebar_width(total_width: float) -> float:
        """Return the maximum width of one sidebar for a given window width.

        This is the smaller of the absolute cap and
        :data:`MAX_SIDEBAR_FRACTION` of the window width, but never
        below :data:`MIN_SIDEBAR_WIDTH` so a sidebar stays visible in
        very narrow windows.
        """
        fraction = max(0.0, total_width) * MAX_SIDEBAR_FRACTION
        return max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, fraction))

    def clamp_widths(self, total_width: float) -> None:
        """Keep the sidebars from consuming the whole screen.

        The clamped values are written back to :attr:`left_width` /
        :attr:`right_width` so the widths saved to ``editor.json`` are
        already valid and do not jump when the window is resized.
        """
        max_each = self.max_sidebar_width(total_width)
        self.left_width = min(max(self.left_width, MIN_SIDEBAR_WIDTH), max_each)
        self.right_width = min(max(self.right_width, MIN_SIDEBAR_WIDTH), max_each)

    def reset_widths(self) -> None:
        """Restore both sidebars to their default widths."""
        self.left_width = DEFAULT_LEFT_WIDTH
        self.right_width = DEFAULT_RIGHT_WIDTH

    def compute(self) -> tuple[Rect, Rect, Rect]:
        """Compute the left, center, and right rects for this frame.

        Returns:
            Tuple ``(left, center, right)``.
        """
        viewport = imgui.get_main_viewport()
        origin_x = viewport.work_pos.x
        origin_y = viewport.work_pos.y
        total_w = viewport.work_size.x
        total_h = viewport.work_size.y

        self.clamp_widths(total_w)
        left_w = self.left_width if self.show_left else 0.0
        right_w = self.right_width if self.show_right else 0.0

        body_y = origin_y + TOOLBAR_HEIGHT
        body_h = max(0.0, total_h - TOOLBAR_HEIGHT - STATUS_BAR_HEIGHT)

        left = Rect(origin_x, body_y, left_w, body_h)
        center = Rect(
            origin_x + left_w,
            body_y,
            max(0.0, total_w - left_w - right_w),
            body_h,
        )
        right = Rect(origin_x + total_w - right_w, body_y, right_w, body_h)

        # The canvas only accepts the mouse below the tab bar (when present).
        tabs = TAB_BAR_HEIGHT if self.show_tabs else 0.0
        self.viewport = Rect(
            center.x,
            center.y + tabs,
            center.width,
            max(0.0, center.height - tabs),
        )
        return left, center, right

    def toolbar_rect(self) -> Rect:
        """Return the toolbar strip rect below the menu bar."""
        viewport = imgui.get_main_viewport()
        return Rect(
            viewport.work_pos.x,
            viewport.work_pos.y,
            viewport.work_size.x,
            TOOLBAR_HEIGHT,
        )

    def status_bar_rect(self) -> Rect:
        """Return the status-bar strip rect at the bottom of the window."""
        viewport = imgui.get_main_viewport()
        return Rect(
            viewport.work_pos.x,
            viewport.work_pos.y + viewport.work_size.y - STATUS_BAR_HEIGHT,
            viewport.work_size.x,
            STATUS_BAR_HEIGHT,
        )

    @staticmethod
    def begin_fixed(
        name: str, rect: Rect, *, transparent: bool = False, padding: bool = True
    ) -> bool:
        """Open an undecorated window locked to a rect.

        Args:
            name: Window ID.
            rect: Position and size.
            transparent: Skip drawing the background (used by the
                canvas viewport).
            padding: Use standard ImGui padding.

        Returns:
            True when the window's contents should be drawn.
        """
        imgui.set_next_window_pos(imgui.ImVec2(rect.x, rect.y))
        imgui.set_next_window_size(imgui.ImVec2(rect.width, rect.height))

        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_bring_to_front_on_focus
            | imgui.WindowFlags_.no_nav_focus
            | imgui.WindowFlags_.no_saved_settings
        )
        if transparent:
            flags |= imgui.WindowFlags_.no_background

        if not padding:
            imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(0, 0))
        expanded, _ = imgui.begin(name, None, int(flags))
        if not padding:
            imgui.pop_style_var()  # imgui.StyleVar_.window_padding
        return bool(expanded)

    def draw_splitter(self, name: str, rect: Rect, *, is_left: bool) -> None:
        """Draw a draggable handle at the edge of a sidebar.

        Args:
            name: Unique splitter ID.
            rect: Sidebar rect adjacent to the splitter.
            is_left: True when the splitter is at the right edge of the
                left sidebar.
        """
        x = rect.x + rect.width if is_left else rect.x - SPLITTER_THICKNESS
        handle = Rect(x, rect.y, SPLITTER_THICKNESS, rect.height)

        imgui.set_next_window_pos(imgui.ImVec2(handle.x, handle.y))
        # Without ``window_min_size`` 0, ImGui forces this window to
        # ``style.window_min_size`` (32px), showing as a dark box at the
        # sidebar edge. ``no_background`` + border 0 hides the window;
        # only the highlight rect below is visible on hover.
        flags: imgui.WindowFlags_ = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_bring_to_front_on_focus
        )
        imgui.set_next_window_size(imgui.ImVec2(handle.width, handle.height))
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(0, 0))
        imgui.push_style_var(imgui.StyleVar_.window_min_size, imgui.ImVec2(0, 0))
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 0.0)
        imgui.begin(f"##splitter_{name}", None, int(flags))
        imgui.invisible_button(
            f"##grip_{name}", imgui.ImVec2(handle.width, handle.height)
        )
        hovered = imgui.is_item_hovered()
        active = imgui.is_item_active()

        if hovered or active:
            imgui.set_mouse_cursor(imgui.MouseCursor_.resize_ew)
        if active:
            delta = imgui.get_io().mouse_delta.x
            if delta:
                if is_left:
                    self.left_width += delta
                else:
                    self.right_width -= delta
                # Clamp right away instead of waiting for the next
                # frame's compute(), so the grip is never seen crossing
                # the limit and bouncing back.
                self.clamp_widths(imgui.get_main_viewport().work_size.x)

        if imgui.is_item_hovered() and imgui.is_mouse_double_clicked(0):
            self.reset_widths()

        if hovered or active:
            color = imgui.get_color_u32(imgui.Col_.separator_active)
            draw_list = imgui.get_window_draw_list()
            draw_list.add_rect_filled(
                imgui.ImVec2(handle.x, handle.y),
                imgui.ImVec2(handle.x + handle.width, handle.y + handle.height),
                color,
            )

        imgui.end()
        imgui.pop_style_var()  # imgui.StyleVar_.window_padding
        imgui.pop_style_var()  # imgui.StyleVar_.window_min_size
        imgui.pop_style_var()  # imgui.StyleVar_.window_border_size


def clamp_split(ratio: float) -> float:
    """Keep a split ratio within the usable range."""
    return min(max(ratio, MIN_SECTION_FRACTION), 1.0 - MIN_SECTION_FRACTION)


def draw_horizontal_splitter(
    name: str, ratio: float, *, height: float, thickness: float = SPLITTER_THICKNESS
) -> float:
    """Draw a draggable horizontal divider inside a panel.

    Unlike :meth:`DockLayout.draw_splitter`, which uses its own ImGui
    window in screen coordinates, this helper is drawn inline inside
    its parent layout — used to split one sidebar into two stacked
    sections.

    Args:
        name: Unique divider ID.
        ratio: Current top-section height ratio (0..1).
        height: Total height of the split area, in pixels.
        thickness: Handle thickness.

    Returns:
        The new ratio after interaction, already clamped.
    """
    imgui.invisible_button(f"##hsplit_{name}", imgui.ImVec2(-1, thickness))
    hovered = imgui.is_item_hovered()
    active = imgui.is_item_active()

    if hovered or active:
        imgui.set_mouse_cursor(imgui.MouseCursor_.resize_ns)
    if active and height > 0.0:
        delta = imgui.get_io().mouse_delta.y
        if delta:
            ratio = clamp_split(ratio + delta / height)
    if hovered and imgui.is_mouse_double_clicked(0):
        ratio = 0.5

    color = imgui.get_color_u32(
        imgui.Col_.separator_active if (hovered or active) else imgui.Col_.separator
    )
    rect_min = imgui.get_item_rect_min()
    rect_max = imgui.get_item_rect_max()
    imgui.get_window_draw_list().add_rect_filled(rect_min, rect_max, color)
    return clamp_split(ratio)


__all__ = [
    "DEFAULT_LEFT_WIDTH",
    "DEFAULT_RIGHT_WIDTH",
    "MAX_SIDEBAR_FRACTION",
    "MAX_SIDEBAR_WIDTH",
    "MIN_SECTION_FRACTION",
    "MIN_SIDEBAR_WIDTH",
    "STATUS_BAR_HEIGHT",
    "TAB_BAR_HEIGHT",
    "TOOLBAR_HEIGHT",
    "DockLayout",
    "Rect",
    "clamp_split",
    "draw_horizontal_splitter",
]
