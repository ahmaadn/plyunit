from __future__ import annotations

import logging
from pathlib import Path

from imgui_bundle import icons_fontawesome_6 as icons_fa, imgui

from scripts.core.file_kind import FileKind
from scripts.core.file_tree import DirEntry, FileEntry
from scripts.services.file_tree import FileTree
from scripts.ui.panel import Panel

logger = logging.getLogger(__name__)

KIND_ICONS: dict[FileKind, str] = {
    FileKind.IMAGE: icons_fa.ICON_FA_FILE_IMAGE,
    FileKind.MAP: icons_fa.ICON_FA_MAP,
    FileKind.SIDECAR: icons_fa.ICON_FA_FILE_CODE,
    FileKind.OTHER: icons_fa.ICON_FA_FILE_CIRCLE_QUESTION,
    FileKind.ANIMATION: icons_fa.ICON_FA_FILM,
    FileKind.AUDIO: icons_fa.ICON_FA_FILE_AUDIO,
    FileKind.FONT: icons_fa.ICON_FA_FONT,
}
"""Font Awesome glyph shown per file kind."""


class ExplorerPanel(Panel):
    """The project file tree.

    Attributes:
        relevant_only: Hide files the editor does not know. Defaults
            to False so the whole project shows, VS Code-style; noise
            is already controlled by the scan excludes. Restored from
            the per-project editor config on project open.
        search: File-name filter.
        selected: Relative path of the selected file.
        active_path: Absolute path of the open document, highlighted.
    """

    def __init__(self) -> None:
        """Create the panel.

        The shared app context and event bus are auto-attached by
        :meth:`Panel.__new__`; the file-tree service is handed to
        :meth:`sync_project` once the project scan has produced one.
        """
        super().__init__()

        self._synced_root: Path | None = None
        self.relevant_only: bool = False
        self.search: str = ""
        self.selected: str | None = None
        self.active_path: Path | None = None

    def sync_project(self, file_tree: FileTree):
        self._file_tree = file_tree
        self._sync_persisted_state()

    def draw(self) -> None:
        """Draw the whole panel."""
        self._sync_persisted_state()
        self._draw_toolbar()
        imgui.separator()

        imgui.begin_child(
            "##explorer_tree", imgui.ImVec2(0, 0), int(imgui.ChildFlags_.borders)
        )
        scanning = self.ctx.workspace.scanning
        if scanning:
            imgui.text_disabled("Scanning Project...")

        tree = self._file_tree
        if tree.is_empty:
            if not scanning:
                imgui.text_disabled("(Empty Project)")
        elif self.search.strip():
            self._draw_search_results(tree)
        else:
            self._draw_dir_children(tree.root)

        self._draw_background_context_menu()
        imgui.end_child()

    def _sync_persisted_state(self) -> None:
        """Pull per-project persisted settings when the project changes.

        Runs once per opened project (not per frame): when the project
        root changes, the explorer toggle is restored from the
        project's ``editor.json``.
        """
        if not self.ctx.project_active:
            return
        root = self.ctx.project_root
        if root == self._synced_root:
            return
        self._synced_root = root
        self.relevant_only = self.ctx.editor.explorer_relevant_only

    def _draw_toolbar(self) -> None:
        """Draw the refresh button, toggles, and search field."""
        if imgui.button("Refresh##explorer"):
            ...
        imgui.same_line()
        changed, value = imgui.checkbox("Only Editor File", self.relevant_only)
        if changed:
            self.relevant_only = value
            self.ctx.editor.explorer_relevant_only = value
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Only show image, map and configurate files.\n"
                "If turn on, You can see other file but cannot open."
            )

        imgui.set_next_item_width(-1)
        changed, text = imgui.input_text_with_hint(
            "##explorer_search", "Search File...", self.search
        )
        if changed:
            self.search = text

        tree = self._file_tree
        if tree.root_path != Path():
            shown = tree.root.total_files(relevant_only=self.relevant_only)
            imgui.text_disabled(f"{shown} files - {tree.root_path.name}")

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
            imgui.text_disabled("(File dont match)")
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
        text = f"{KIND_ICONS[entry.kind]} {label or entry.name}"

        if not entry.is_openable:
            # Read-only: shown for a complete structure, but not interactive.
            self._draw_file_row(entry, text, selected=False, enabled=False)
            imgui.set_item_tooltip(
                f"{entry.relative}\n(Cannot be opened in this editor)"
            )
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
            # self.bus.publish(MAP_OPEN_REQUESTED, entry.path)
            return
        # Images and sidecars lead to the same asset document.
        if entry.asset_id is not None:
            # self.bus.publish(ASSET_OPEN_REQUESTED, entry.asset_id)
            ...

    def _draw_file_context_menu(self, entry: FileEntry) -> None:
        """Draw the right-click menu for a file row."""
        if not imgui.begin_popup_context_item(f"##filectx_{entry.relative}"):
            return
        imgui.text_disabled(entry.relative)
        imgui.separator()

        if entry.is_openable and imgui.menu_item("Open", "", False)[0]:
            self.selected = entry.relative
            self._activate(entry)
        if imgui.menu_item("Reveal in File Explorer", "", False)[0]:
            # self.bus.publish(FILE_REVEAL_REQUESTED, entry.path.parent)
            ...
        if imgui.menu_item("New Map in Here...", "", False)[0]:
            # self.bus.publish(MAP_NEW_REQUESTED, entry.path.parent)
            ...
        if entry.kind is FileKind.MAP:
            imgui.separator()
            if imgui.menu_item("Delete Map", "", False)[0]:
                # self.bus.publish(MAP_DELETE_REQUESTED, entry.path)
                ...
        imgui.end_popup()

    def _draw_dir_context_menu(self, node: DirEntry) -> None:
        """Draw the right-click menu for a folder node."""
        if not imgui.begin_popup_context_item(f"##dirctx_{node.relative}"):
            return
        imgui.text_disabled(node.relative or "(root)")
        imgui.separator()
        # self.bus.publish(MAP_NEW_REQUESTED, root / node.relative)
        if imgui.menu_item("New Map in Here...", "", False)[0]:
            ...
        # self.bus.publish(FILE_REVEAL_REQUESTED, root / node.relative)
        if imgui.menu_item("Reveal in File Explorer", "", False)[0]:
            ...
        imgui.end_popup()

    def _draw_background_context_menu(self) -> None:
        """Draw the right-click menu for the empty area of the panel."""
        flags = int(
            imgui.PopupFlags_.mouse_button_right | imgui.PopupFlags_.no_open_over_items
        )
        if not imgui.begin_popup_context_window("##explorer_bg_ctx", flags):
            return
        imgui.text_disabled(self._file_tree.root_path.name or "(root project)")
        imgui.separator()
        if imgui.menu_item("New Map...", "", False)[0]:
            # self.bus.publish(MAP_NEW_REQUESTED, root)
            ...
        if imgui.menu_item("Refresh", "F5", False)[0]:
            # self.bus.publish(APP_REFRESH_ASSETS)
            ...
        imgui.end_popup()


__all__ = ["ExplorerPanel"]
