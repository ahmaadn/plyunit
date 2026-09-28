"""Tata letak jendela: sidebar kiri, viewport tengah, sidebar kanan.

Sebelumnya setiap panel adalah jendela ImGui mengambang yang saling menumpuk
dan menutupi kanvas. Modul ini memasang tata letak tetap seperti IDE:

* **Sidebar kiri** — aset & palette (sumber tile).
* **Tengah** — tab map + kanvas peta (dibiarkan transparan agar render raylib
  di belakangnya terlihat).
* **Sidebar kanan** — properti: layer, physics, objek, autotile, pengaturan.

Lebar kedua sidebar dapat digeser lewat *splitter* dan disimpan di
``.ryeditor/editor.json``. Rect viewport tengah diekspos lewat
:attr:`DockLayout.viewport` supaya kanvas tahu area yang boleh menerima
input mouse — tanpa itu, klik di atas sidebar akan ikut melukis tile.
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


@dataclass(slots=True)
class Rect:
    """Persegi di koordinat layar."""

    x: float
    y: float
    width: float
    height: float

    def contains(self, px: float, py: float) -> bool:
        """True bila titik berada di dalam persegi."""
        return (
            self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
        )


class DockLayout:
    """Menghitung dan menggambar kerangka tata letak editor.

    Attributes:
        left_width: Lebar sidebar kiri dalam pixel.
        right_width: Lebar sidebar kanan dalam pixel.
        show_left: Tampilkan sidebar kiri.
        show_right: Tampilkan sidebar kanan.
        show_tabs: Sisakan :data:`TAB_BAR_HEIGHT` di atas area tengah
            untuk tab bar (set ``False`` bila belum ada tab bar).
        viewport: Area kanvas tengah setelah dikurangi sidebar & bar.
    """

    def __init__(
        self,
        left_width: float = DEFAULT_LEFT_WIDTH,
        right_width: float = DEFAULT_RIGHT_WIDTH,
    ) -> None:
        self.left_width = left_width
        self.right_width = right_width
        self.show_left = True
        self.show_right = True
        self.show_tabs = False
        self.viewport = Rect(0.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Geometri
    # ------------------------------------------------------------------

    @staticmethod
    def max_sidebar_width(total_width: float) -> float:
        """Lebar maksimum satu sidebar untuk lebar jendela tertentu.

        Diambil dari nilai terkecil antara batas absolut dan
        :data:`MAX_SIDEBAR_FRACTION` dari lebar jendela, tetapi tidak pernah
        turun di bawah :data:`MIN_SIDEBAR_WIDTH` supaya sidebar tetap dapat
        ditampilkan pada jendela yang sangat sempit.
        """
        fraction = max(0.0, total_width) * MAX_SIDEBAR_FRACTION
        return max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, fraction))

    def clamp_widths(self, total_width: float) -> None:
        """Jaga agar sidebar tidak memakan seluruh layar.

        Nilai hasil clamp ditulis balik ke :attr:`left_width` /
        :attr:`right_width` sehingga lebar yang tersimpan di ``editor.json``
        sudah valid dan tidak melompat saat jendela diubah ukurannya.
        """
        max_each = self.max_sidebar_width(total_width)
        self.left_width = min(max(self.left_width, MIN_SIDEBAR_WIDTH), max_each)
        self.right_width = min(max(self.right_width, MIN_SIDEBAR_WIDTH), max_each)

    def reset_widths(self) -> None:
        """Kembalikan kedua sidebar ke lebar default."""
        self.left_width = DEFAULT_LEFT_WIDTH
        self.right_width = DEFAULT_RIGHT_WIDTH

    def compute(self) -> tuple[Rect, Rect, Rect]:
        """Hitung rect sidebar kiri, tengah, dan kanan untuk frame ini.

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

        # Kanvas hanya boleh menerima mouse di bawah tab bar (bila ada).
        tabs = TAB_BAR_HEIGHT if self.show_tabs else 0.0
        self.viewport = Rect(
            center.x,
            center.y + tabs,
            center.width,
            max(0.0, center.height - tabs),
        )
        return left, center, right

    def toolbar_rect(self) -> Rect:
        """Rect strip toolbar di bawah menu bar."""
        viewport = imgui.get_main_viewport()
        return Rect(
            viewport.work_pos.x,
            viewport.work_pos.y,
            viewport.work_size.x,
            TOOLBAR_HEIGHT,
        )

    def status_bar_rect(self) -> Rect:
        """Rect strip status bar di dasar jendela."""
        viewport = imgui.get_main_viewport()
        return Rect(
            viewport.work_pos.x,
            viewport.work_pos.y + viewport.work_size.y - STATUS_BAR_HEIGHT,
            viewport.work_size.x,
            STATUS_BAR_HEIGHT,
        )

    # ------------------------------------------------------------------
    # Helper jendela
    # ------------------------------------------------------------------

    @staticmethod
    def begin_fixed(
        name: str, rect: Rect, *, transparent: bool = False, padding: bool = True
    ) -> bool:
        """Buka jendela tanpa dekorasi yang terkunci pada sebuah rect.

        Args:
            name: ID jendela.
            rect: Posisi & ukuran.
            transparent: Jangan gambar latar (dipakai viewport kanvas).
            padding: Pakai padding standar ImGui.

        Returns:
            True bila isi jendela perlu digambar.
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
        """Gambar pegangan geser di tepi sidebar.

        Args:
            name: ID unik splitter.
            rect: Rect sidebar yang menempel pada splitter.
            is_left: True bila splitter berada di kanan sidebar kiri.
        """
        x = rect.x + rect.width if is_left else rect.x - SPLITTER_THICKNESS
        handle = Rect(x, rect.y, SPLITTER_THICKNESS, rect.height)

        imgui.set_next_window_pos(imgui.ImVec2(handle.x, handle.y))
        # Tanpa ``window_min_size`` 0, ImGui memaksa jendela ini selebar
        # ``style.window_min_size`` (32px) sehingga tampil sebagai kotak gelap
        # di tepi sidebar. ``no_background`` + border 0 membuat jendela tidak
        # terlihat; hanya rect sorotan di bawah yang tampak saat hover.
        flags: imgui.WindowFlags_ = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_bring_to_front_on_focus
            # | imgui.WindowFlags_.no_background
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
                # Clamp seketika, bukan menunggu compute() frame berikutnya,
                # agar pegangan tidak terlihat melewati batas lalu memantul.
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


MIN_SECTION_FRACTION = 0.15
"""Porsi minimum satu bagian pada pembagian vertikal di dalam sidebar.

Tanpa batas ini, menggeser pemisah sampai mentok membuat salah satu browser
hilang sepenuhnya dan tidak dapat dikembalikan tanpa mengedit ``editor.json``.
"""


def clamp_split(ratio: float) -> float:
    """Jaga rasio pembagian tetap di rentang yang dapat dipakai."""
    return min(max(ratio, MIN_SECTION_FRACTION), 1.0 - MIN_SECTION_FRACTION)


def draw_horizontal_splitter(
    name: str, ratio: float, *, height: float, thickness: float = SPLITTER_THICKNESS
) -> float:
    """Gambar pemisah horizontal yang dapat digeser di dalam sebuah panel.

    Berbeda dari :meth:`DockLayout.draw_splitter` yang memakai jendela ImGui
    tersendiri di koordinat layar, helper ini digambar inline di dalam layout
    induknya — dipakai untuk membagi satu sidebar menjadi dua bagian bertumpuk.

    Args:
        name: ID unik pemisah.
        ratio: Rasio tinggi bagian atas saat ini (0..1).
        height: Tinggi total area yang dibagi, dalam pixel.
        thickness: Tebal pegangan.

    Returns:
        Rasio baru setelah interaksi, sudah di-clamp.
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
