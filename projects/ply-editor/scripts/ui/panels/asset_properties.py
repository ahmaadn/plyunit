"""Panel: properti aset gambar dan spritesheet.

Panel ini menempati sidebar kanan saat tab yang aktif berisi dokumen aset. Isinya
mengikuti tipe aset:

* **image** — nama tampilan dan tombol untuk menjadikannya spritesheet.
* **spritesheet** — tambahan pengaturan grid (ukuran, offset, spacing, margin,
  snap) beserta daftar region.

Grid di sini murni alat bantu seleksi: mengubahnya tidak pernah membuat atau
menggeser region yang sudah ada. Region dibuat dengan mengklik petak di kanvas.

Beralih dari spritesheet kembali ke image meminta konfirmasi lebih dulu, lalu
menyimpan region sebagai cadangan alih-alih membuangnya.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from imgui_bundle import imgui

from scripts.app import events
from scripts.ui.panel import Panel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from scripts.state.documents.asset_document import ImageDocument


class AssetProperties(Panel):
    """Properti dokumen aset yang sedang dibuka.

    Attributes:
        selected_region: Index region yang sedang dipilih (-1 bila tidak ada).
    """

    def __init__(self) -> None:
        self.status: str = ""
        self._rename_index: int = -1
        self._rename_text: str = ""
        self._confirm_to_image: bool = False

    def _notify(self) -> None:
        self.bus.publish(events.ASSET_CHANGED)

    def _select_region(self, index: int) -> None:
        """Ubah region terpilih lalu beri tahu pemilik panel (mis. kanvas)."""
        self.bus.publish(events.REGION_SELECTED, index)

    @property
    def selected_region(self):
        # pyrefly: ignore [missing-attribute]
        return self.ctx.workspace.active.selected_region

    def draw(self) -> None:
        """Gambar seluruh panel properti."""
        doc = cast("ImageDocument" | None, self.ctx.workspace.active)
        if doc is None:
            imgui.text_disabled("Tidak ada aset terbuka.")
            return

        self._draw_header(doc)
        imgui.separator()
        self._draw_type_switch(doc)

        if doc.is_spritesheet:
            imgui.separator()
            self._draw_grid(doc)
            imgui.separator()
            self._draw_region_list(doc)

        if self.status:
            imgui.separator()
            imgui.text_wrapped(self.status)

        self._draw_confirm_popup(doc)

    def _draw_header(self, doc: ImageDocument) -> None:
        imgui.text(doc.image_path.name)
        imgui.text_disabled(doc.asset_id)

        changed, text = imgui.input_text(
            "Nama", doc.title, int(imgui.InputTextFlags_.enter_returns_true)
        )
        if (changed or imgui.is_item_deactivated_after_edit()) and doc.set_display_name(
            text
        ):
            self._notify()

        if imgui.button("Fit"):
            self.bus.publish(events.ASSET_FIT_REQUESTED)
        imgui.same_line()
        if imgui.button("1:1"):
            self.bus.publish(events.ASSET_ZOOM_ACTUAL_REQUESTED)
        imgui.same_line()
        imgui.text_disabled("(scroll = zoom)")

    def _draw_type_switch(self, doc: ImageDocument) -> None:
        imgui.text("Tipe aset")
        is_sheet = doc.is_spritesheet

        if imgui.radio_button("Image standalone", not is_sheet) and is_sheet:
            # Region yang sudah ada berisiko hilang; minta konfirmasi dulu.
            if doc.regions:
                self._confirm_to_image = True
            elif doc.set_asset_type("image"):
                self._notify()

        imgui.same_line()
        if imgui.radio_button("Spritesheet", is_sheet) and not is_sheet:
            if doc.set_asset_type("spritesheet"):
                restored = len(doc.regions)
                self.status = (
                    f"{restored} region dipulihkan dari cadangan."
                    if restored
                    else "Klik petak grid di kanvas untuk membuat region."
                )
                self._notify()

        # if not is_sheet and doc.backup_region_count:
        #     imgui.text_disabled(
        #         f"{doc.backup_region_count} region tersimpan sebagai cadangan."
        #     )

    def _draw_grid(self, doc: ImageDocument) -> None:
        grid = doc.grid
        imgui.text("Grid (alat bantu seleksi)")
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Grid tidak membuat region otomatis.\n"
                "Klik petak di kanvas untuk membuat region."
            )

        update_grid = {}
        changed, values = imgui.input_int2(
            "Ukuran petak", [grid.cell_width, grid.cell_height]
        )
        if changed:
            update_grid.update({
                "cell_width": max(1, values[0]),
                "cell_height": max(1, values[1]),
            })

        changed, values = imgui.input_int2("Offset", [grid.offset_x, grid.offset_y])
        if changed:
            update_grid.update({
                "offset_x": max(0, values[0]),
                "offset_y": max(0, values[1]),
            })

        changed, values = imgui.input_int2("Spacing", [grid.spacing_x, grid.spacing_y])
        if changed:
            update_grid.update({
                "spacing_x": max(0, values[0]),
                "spacing_y": max(0, values[1]),
            })

        changed, values = imgui.input_int2("Margin", [grid.margin_x, grid.margin_y])
        if changed:
            update_grid.update({
                "margin_x": max(0, values[0]),
                "margin_y": max(0, values[1]),
            })

        changed, value = imgui.checkbox("Snap ke grid", grid.snap)
        if changed:
            update_grid.update({"snap": value})

        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Aktif: ubah ukuran region mengikuti petak grid.\n"
                "Nonaktif: bebas per pixel."
            )

        if update_grid:
            self.bus.publish(events.ASSET_GRID_CHANGE_REQUESTED, update_grid)

    def _draw_region_list(self, doc: ImageDocument) -> None:
        imgui.text(f"Region ({len(doc.regions)})")
        if not doc.regions:
            imgui.text_disabled("(klik petak grid di kanvas untuk menambah)")
            return

        imgui.begin_child(
            "##asset_regions", imgui.ImVec2(0, 200), int(imgui.ChildFlags_.borders)
        )
        remove_index = -1
        for i, region in enumerate(doc.regions):
            imgui.push_id(i)
            if self._rename_index == i:
                imgui.set_next_item_width(-70)
                changed, text = imgui.input_text(
                    "##rename",
                    self._rename_text,
                    int(imgui.InputTextFlags_.enter_returns_true),
                )
                # if changed:
                #     if doc.rename_region(i, text):
                #         self._notify()
                #     self._rename_index = -1
                imgui.same_line()
                if imgui.small_button("OK"):
                    self._rename_index = -1
            else:
                x, y, w, h = region.source_rect
                # allow_overlap: tombol N/X digambar menimpa selectable
                # selebar baris; tanpa flag ini selectable menelan semua klik
                # sehingga rename/hapus tidak pernah terpicu.
                clicked, _ = imgui.selectable(
                    f"{region.id}##sel",
                    self.selected_region == i,
                    imgui.SelectableFlags_.allow_overlap,
                )
                if clicked:
                    self._select_region(i)
                if imgui.is_item_hovered():
                    imgui.set_tooltip(f"({int(x)}, {int(y)}) {int(w)}x{int(h)}")
                imgui.same_line(imgui.get_window_width() - 76)
                if imgui.small_button("N"):
                    self._rename_index = i
                    self._rename_text = region.id
                imgui.same_line()
                if imgui.small_button("X"):
                    remove_index = i
            imgui.pop_id()
        imgui.end_child()

        if remove_index >= 0:
            ...
            # removed = doc.remove_region(remove_index)
            # if removed is not None:
            #     self._select_region(-1)
            #     # Data map sengaja tidak disentuh; tile yang memakai region ini
            #     # ditandai hilang di kanvas map.
            #     self.status = (
            #         f"Region '{removed.name}' dihapus. "
            #         "Tile di map yang memakainya ditandai hilang."
            #     )
            #     self._notify()

    def _draw_confirm_popup(self, doc: ImageDocument) -> None:
        """Konfirmasi sebelum spritesheet dikembalikan menjadi image."""
        if not self._confirm_to_image:
            return

        popup_id = "Ubah ke image standalone?"
        imgui.open_popup(popup_id)
        opened, _ = imgui.begin_popup_modal(
            popup_id, None, int(imgui.WindowFlags_.always_auto_resize)
        )
        if not opened:
            return

        imgui.text_wrapped(
            f"Aset ini punya {len(doc.regions)} region.\n"
            "Region akan disimpan sebagai cadangan dan dapat dipulihkan "
            "bila tipe dikembalikan ke spritesheet."
        )
        imgui.separator()

        if imgui.button("Lanjutkan", imgui.ImVec2(120, 0)):
            if doc.set_asset_type("image"):
                self._select_region(-1)
                # self.status = (
                #     f"{doc.backup_region_count} region disimpan sebagai cadangan."
                # )
                self._notify()
            self._confirm_to_image = False
            imgui.close_current_popup()
        imgui.same_line()
        if imgui.button("Batal", imgui.ImVec2(120, 0)):
            self._confirm_to_image = False
            imgui.close_current_popup()

        imgui.end_popup()


__all__ = ["AssetProperties"]
