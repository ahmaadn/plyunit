"""Explorer panel: a VS Code-style project file tree.

Shows the project structure as it is — folders and files, all of them —
not only image assets. Click behavior follows the file kind computed by
:class:`~scripts.project.file_tree.FileTree`:

* Image — opens an asset document tab (image / spritesheet props).
* Map — opens a map tab.
* Sidecar ``.json`` — routes to its parent image, because a sidecar is
  the on-disk representation of the same asset document.
* Other files — cannot be opened; drawn as inactive text.

The "Hanya file editor" (editor files only) toggle hides the last group
together with the folders it empties. With the toggle off those files
still appear, but are not clickable, so no misleading action is offered.

This panel never touches the disk: the tree is filled from a background
scan via :meth:`ExplorerPanel.set_tree`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from imgui_bundle import icons_fontawesome_6 as icons_fa, imgui

from scripts.project.file_tree import DirEntry, FileEntry, FileKind, FileTree
from scripts.ui.panel import Panel

logger = logging.getLogger(__name__)


class ExplorerPanel(Panel):
    """The project file tree.

    Attributes:
        root: Project root path.
        tree: The active file tree; ``None`` before the first scan
            finishes.
        relevant_only: Hide files the editor does not know. Defaults
            to False so the whole project shows, VS Code-style; noise
            is already controlled by the scan excludes.
        search: File-name filter.
        selected: Relative path of the selected file.
        active_path: Absolute path of the open document, highlighted.
        scanning: True while a background scan is running.
    """

    def __init__(self) -> None:
        """Start with an empty tree and default toggles."""
        self.root = Path()
        self.tree: FileTree | None = None
        self.relevant_only: bool = False
        self.search: str = ""
        self.selected: str | None = None
        self.active_path: Path | None = None
        self.scanning: bool = False

    def set_tree(self, tree: FileTree) -> None:
        """Install a scan result tree and stop the scanning indicator."""
        self.tree = tree
        self.root = tree.root_path
        self.scanning = False

    def set_root(self, root: Path) -> None:
        """Point the panel at another project and drop the old tree."""
        self.root = root
        self.tree = None
        self.selected = None

    def draw(self) -> None:
        """Draw the whole panel."""
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
        """Draw the refresh button, toggles, and search field."""
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
            imgui.text_disabled(f"{shown} files - {self.root.name}")

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def _visible(self, entry: FileEntry) -> bool:
        """Return whether a file passes the relevance filter."""
        return not self.relevant_only or entry.kind.is_relevant

    def _draw_search_results(self, tree: FileTree) -> None:
        """Draw search results as a flat list (no hierarchy).

        While searching, the folder structure gets in the way: the user
        is looking for one specific file, not its location.
        """
        matches = tree.search(self.search, relevant_only=self.relevant_only)
        if not matches:
            imgui.text_disabled("(tidak ada file yang cocok)")
            return
        for entry in matches:
            self._draw_file(entry, label=entry.relative)

    def _draw_dir_children(self, node: DirEntry) -> None:
        """Draw the folders, then the files, directly inside a node."""
        for child in node.children.values():
            self._draw_dir(child)
        for entry in node.files:
            if self._visible(entry):
                self._draw_file(entry)

    def _draw_dir(self, node: DirEntry) -> None:
        """Draw one folder node, hiding fully filtered-out folders."""
        if self.relevant_only and not node.has_relevant():
            return

        flags = int(
            imgui.TreeNodeFlags_.open_on_arrow
            | imgui.TreeNodeFlags_.open_on_double_click
            | imgui.TreeNodeFlags_.span_avail_width
        )
        if not node.children and not any(self._visible(f) for f in node.files):
            flags |= int(imgui.TreeNodeFlags_.leaf)

        icon = icons_fa.ICON_FA_FOLDER_OPEN if node.is_open else icons_fa.ICON_FA_FOLDER
        opened = imgui.tree_node_ex(f"{icon} {node.name}###dir_{node.relative}", flags)
        if opened != node.is_open:
            node.is_open = opened

        self._draw_dir_context_menu(node)
        if opened:
            self._draw_dir_children(node)
            imgui.tree_pop()

    def _draw_file_row(
        self, entry: FileEntry, text: str, *, selected: bool, enabled: bool
    ) -> bool:
        """Draw one file row with its label aligned to folder labels.

        The row background/hit area comes from a selectable (or a dummy for
        read-only files); the label is drawn manually at the same X where a
        tree node would place its label, so files and folders line up.
        """
        style = imgui.get_style()
        # Same height as a tree node row
        height = imgui.get_text_line_height() + style.frame_padding.y * 2
        origin = imgui.get_cursor_screen_pos()

        clicked = False
        if enabled:
            clicked, _ = imgui.selectable(
                f"##file_{entry.relative}", selected, 0, imgui.ImVec2(0, height)
            )
        else:
            imgui.dummy(imgui.ImVec2(imgui.get_content_region_avail().x, height))

        color = imgui.get_color_u32(
            imgui.Col_.text if enabled else imgui.Col_.text_disabled
        )
        label_pos = imgui.ImVec2(
            origin.x + imgui.get_tree_node_to_label_spacing(),
            origin.y + style.frame_padding.y,
        )
        imgui.get_window_draw_list().add_text(label_pos, color, text)
        return clicked

    def _draw_file(self, entry: FileEntry, *, label: str | None = None) -> None:
        """Draw one file row as a read-only row or a selectable."""
        text = f"{entry.icon} {label or entry.name}"

        if not entry.is_openable:
            # Read-only: shown for a complete structure, but not interactive.
            self._draw_file_row(entry, text, selected=False, enabled=False)
            imgui.set_item_tooltip(f"{entry.relative}\n(tidak dapat dibuka editor)")
            self._draw_file_context_menu(entry)
            return

        is_active = self.active_path is not None and entry.path == self.active_path
        selected = self.selected == entry.relative or is_active

        clicked = self._draw_file_row(entry, text, selected=selected, enabled=True)
        imgui.set_item_tooltip(entry.relative)
        if clicked:
            self.selected = entry.relative
            self._activate(entry)
        self._draw_file_context_menu(entry)

    def _activate(self, entry: FileEntry) -> None:
        """Open a file according to its kind."""
        if entry.kind is FileKind.MAP:
            # ctx.bus.publish(MAP_OPEN_REQUESTED, entry.path)
            return
        # Images and sidecars lead to the same asset document.
        if entry.asset_id is not None:
            # ctx.bus.publish(ASSET_OPEN_REQUESTED, entry.asset_id)
            ...

    def _draw_file_context_menu(self, entry: FileEntry) -> None:
        """Draw the right-click menu for a file row."""
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
        """Draw the right-click menu for a folder node."""
        if not imgui.begin_popup_context_item(f"##dirctx_{node.relative}"):
            return
        imgui.text_disabled(node.relative or "(root)")
        imgui.separator()
        # ctx.bus.publish(MAP_NEW_REQUESTED, self.root / node.relative)
        if imgui.menu_item("Map Baru di sini...", "", False)[0]:
            ...
        # ctx.bus.publish(FILE_REVEAL_REQUESTED, self.root / node.relative)
        if imgui.menu_item("Buka di File Explorer", "", False)[0]:
            ...
        imgui.end_popup()

    def _draw_background_context_menu(self) -> None:
        """Draw the right-click menu for the empty area of the panel."""
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
