"""Panel: Folder Explorer bergaya VS Code.

Menampilkan struktur project apa adanya — folder dan file, seluruhnya — bukan
hanya aset gambar seperti
:class:`~editor.ui.panels.asset_browser.AssetBrowserPanel`. Panel ini
menggantikan browser map lama, yang hanya menampilkan file map.

Perilaku klik mengikuti jenis file yang dihitung
:class:`~editor.core.file_tree.FileTree`:

* Gambar → membuka tab dokumen aset (properti image / spritesheet).
* Map → membuka tab map.
* Sidecar ``.json`` → diarahkan ke gambar induknya, karena sidecar adalah
  representasi disk dari dokumen aset yang sama.
* File lain → tidak dapat dibuka; ditampilkan sebagai teks nonaktif.

Toggle "Hanya file editor" menyembunyikan jenis terakhir beserta folder yang
menjadi kosong karenanya. Saat toggle dimatikan file tersebut tetap muncul,
tetapi tidak dapat diklik agar tidak ada aksi yang menyesatkan.

Panel ini tidak pernah menelusuri disk: pohonnya diisi dari hasil pemindaian
latar belakang lewat :meth:`FileExplorerPanel.set_tree`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from imgui_bundle import imgui

from scripts.panel import Element
from scripts.project.file_tree import DirEntry, FileEntry, FileKind, FileTree

logger = logging.getLogger(__name__)


class ExplorerPanel(Element):
    """Pohon file project.

    Attributes:
        tree: Pohon file aktif; ``None`` sebelum pemindaian pertama selesai.
        relevant_only: Sembunyikan file yang tidak dikenal editor.
        search: Filter nama file.
        selected: Path relatif file yang sedang dipilih.
        active_path: Path absolut dokumen yang sedang dibuka, untuk disorot.
        scanning: True selama pemindaian latar belakang berjalan.
    """

    def __init__(self) -> None:
        self.root = Path()
        self.tree: FileTree | None = None
        self.relevant_only: bool = True
        self.search: str = ""
        self.selected: str | None = None
        self.active_path: Path | None = None
        self.scanning: bool = False

    def set_tree(self, tree: FileTree) -> None:
        """Pasang pohon hasil pemindaian dan hentikan indikator scanning."""
        self.tree = tree
        self.root = tree.root_path
        self.scanning = False

    def set_root(self, root: Path) -> None:
        """Arahkan panel ke project lain dan kosongkan pohon lama."""
        self.root = root
        self.tree = None
        self.selected = None

    def draw(self) -> None:
        """Gambar seluruh panel."""
        self._draw_toolbar()
        imgui.separator()

        imgui.begin_child(
            "##explorer_tree", imgui.ImVec2(0, 0), int(imgui.ChildFlags_.borders)
        )
        tree = self.tree
        if tree is None:
            imgui.text_disabled(
                "Memindai project..." if self.scanning else "(project belum dipindai)"
            )
        elif tree.is_empty:
            imgui.text_disabled("(project kosong)")
        elif self.search.strip():
            self._draw_search_results(tree)
        else:
            self._draw_dir_children(tree.root)

        self._draw_background_context_menu()
        imgui.end_child()

    def _draw_toolbar(self) -> None:
        if imgui.button("Refresh##explorer"):
            ...
        imgui.same_line()
        changed, value = imgui.checkbox("Hanya file editor", self.relevant_only)
        if changed:
            self.relevant_only = value
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Tampilkan hanya gambar, map, dan konfigurasi aset.\n"
                "Bila dimatikan, file lain ikut terlihat namun tidak dapat dibuka."
            )

        imgui.set_next_item_width(-1)
        changed, text = imgui.input_text_with_hint(
            "##explorer_search", "Cari file...", self.search
        )
        if changed:
            self.search = text

        tree = self.tree
        if tree is not None:
            shown = tree.root.total_files(relevant_only=self.relevant_only)
            imgui.text_disabled(f"{shown} file - {self.root.name}")

    # ------------------------------------------------------------------
    # Pohon
    # ------------------------------------------------------------------

    def _visible(self, entry: FileEntry) -> bool:
        return not self.relevant_only or entry.kind.is_relevant

    def _draw_search_results(self, tree: FileTree) -> None:
        """Hasil pencarian ditampilkan rata (tanpa hierarki).

        Saat mencari, struktur folder justru menghalangi: yang dicari adalah
        satu file tertentu, bukan lokasinya.
        """
        matches = tree.search(self.search, relevant_only=self.relevant_only)
        if not matches:
            imgui.text_disabled("(tidak ada file yang cocok)")
            return
        for entry in matches:
            self._draw_file(entry, label=entry.relative)

    def _draw_dir_children(self, node: DirEntry) -> None:
        for child in node.children.values():
            self._draw_dir(child)
        for entry in node.files:
            if self._visible(entry):
                self._draw_file(entry)

    def _draw_dir(self, node: DirEntry) -> None:
        # Folder yang seluruh isinya tersembunyi tidak perlu ditampilkan.
        if self.relevant_only and not node.has_relevant():
            return

        count = node.total_files(relevant_only=self.relevant_only)
        flags = int(
            imgui.TreeNodeFlags_.open_on_arrow
            | imgui.TreeNodeFlags_.open_on_double_click
            | imgui.TreeNodeFlags_.span_avail_width
        )
        if not node.children and not any(self._visible(f) for f in node.files):
            flags |= int(imgui.TreeNodeFlags_.leaf)

        opened = imgui.tree_node_ex(
            f"{node.name}  ({count})##dir_{node.relative}", flags
        )
        self._draw_dir_context_menu(node)
        if opened:
            self._draw_dir_children(node)
            imgui.tree_pop()

    def _draw_file(self, entry: FileEntry, *, label: str | None = None) -> None:
        text = f"{entry.icon} {label or entry.name}"

        if not entry.is_openable:
            # File read-only: ditampilkan agar struktur project utuh, tetapi
            # tidak interaktif supaya tidak menjanjikan aksi yang tidak ada.
            imgui.tree_node_ex(
                f"{text}##file_{entry.relative}",
                int(
                    imgui.TreeNodeFlags_.leaf
                    | imgui.TreeNodeFlags_.no_tree_push_on_open
                    | imgui.TreeNodeFlags_.span_avail_width
                ),
            )
            imgui.set_item_tooltip(f"{entry.relative}\n(tidak dapat dibuka editor)")
            self._draw_file_context_menu(entry)
            return

        is_active = self.active_path is not None and entry.path == self.active_path
        selected = self.selected == entry.relative or is_active

        clicked, _ = imgui.selectable(f"{text}##file_{entry.relative}", selected)
        imgui.set_item_tooltip(entry.relative)
        if clicked:
            self.selected = entry.relative
            self._activate(entry)
        self._draw_file_context_menu(entry)

    # ------------------------------------------------------------------
    # Aksi
    # ------------------------------------------------------------------

    def _activate(self, entry: FileEntry) -> None:
        """Buka file sesuai jenisnya."""
        if entry.kind is FileKind.MAP:
            # ctx.bus.publish(MAP_OPEN_REQUESTED, entry.path)
            return
        # Gambar dan sidecar bermuara ke dokumen aset yang sama.
        if entry.asset_id is not None:
            # ctx.bus.publish(ASSET_OPEN_REQUESTED, entry.asset_id)
            ...

    def _draw_file_context_menu(self, entry: FileEntry) -> None:
        if not imgui.begin_popup_context_item(f"##filectx_{entry.relative}"):
            return
        imgui.text_disabled(entry.relative)
        imgui.separator()

        if entry.is_openable and imgui.menu_item("Buka", "", False)[0]:
            self.selected = entry.relative
            self._activate(entry)
        if imgui.menu_item("Buka di File Explorer", "", False)[0]:
            # ctx.bus.publish(FILE_REVEAL_REQUESTED, entry.path.parent)
            ...
        if imgui.menu_item("Map Baru di sini...", "", False)[0]:
            # ctx.bus.publish(MAP_NEW_REQUESTED, entry.path.parent)
            ...
        if entry.kind is FileKind.MAP:
            imgui.separator()
            if imgui.menu_item("Hapus Map", "", False)[0]:
                # ctx.bus.publish(MAP_DELETE_REQUESTED, entry.path)
                ...
        imgui.end_popup()

    def _draw_dir_context_menu(self, node: DirEntry) -> None:
        if not imgui.begin_popup_context_item(f"##dirctx_{node.relative}"):
            return
        imgui.text_disabled(node.relative or "(root)")
        imgui.separator()
        target = self.root / node.relative if node.relative else self.root
        if imgui.menu_item("Map Baru di sini...", "", False)[0]:
            # ctx.bus.publish(MAP_NEW_REQUESTED, target)
            ...
        if imgui.menu_item("Buka di File Explorer", "", False)[0]:
            # ctx.bus.publish(FILE_REVEAL_REQUESTED, target)
            ...
        imgui.end_popup()

    def _draw_background_context_menu(self) -> None:
        flags = int(
            imgui.PopupFlags_.mouse_button_right | imgui.PopupFlags_.no_open_over_items
        )
        if not imgui.begin_popup_context_window("##explorer_bg_ctx", flags):
            return
        imgui.text_disabled(self.root.name or "(root project)")
        imgui.separator()
        if imgui.menu_item("Map Baru...", "", False)[0]:
            # ctx.bus.publish(MAP_NEW_REQUESTED, self.root)
            ...
        if imgui.menu_item("Refresh", "F5", False)[0]:
            # ctx.bus.publish(APP_REFRESH_ASSETS)
            ...
        imgui.end_popup()


__all__ = ["ExplorerPanel"]
