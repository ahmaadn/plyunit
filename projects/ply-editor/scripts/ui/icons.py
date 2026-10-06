from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from imgui_bundle import icons_fontawesome_6 as fa, imgui

from scripts.core.file_kind import FileKind
from scripts.state.document import DocumentKind
from scripts.ui.text_utils import text_width

DEFAULT_GAP = "  "
"""Spacing placed between an icon and its text label."""

TextWidth = Callable[[str], float]
"""Measures the rendered width of a string in pixels."""

FontKey = Callable[[], float]
"""Returns a value that changes when text metrics change (font size)."""

# Files
# ---------------------------------------------
FILE = fa.ICON_FA_FILE
FILE_CODE = fa.ICON_FA_FILE_CODE
FILE_TEXT = fa.ICON_FA_FILE_LINES
FILE_IMAGE = fa.ICON_FA_FILE_IMAGE
FILE_AUDIO = fa.ICON_FA_FILE_AUDIO
FILE_VIDEO = fa.ICON_FA_FILE_VIDEO
FILE_UNKNOWN = fa.ICON_FA_FILE_CIRCLE_QUESTION

# Assets
# ---------------------------------------------
MAP = fa.ICON_FA_MAP
IMAGE = fa.ICON_FA_IMAGE
FILM = fa.ICON_FA_FILM
FONT = fa.ICON_FA_FONT

# Folder
# ---------------------------------------------
FOLDER = fa.ICON_FA_FOLDER
FOLDER_OPEN = fa.ICON_FA_FOLDER_OPEN
FOLDER_EXPLORER = fa.ICON_FA_COPY

# Status
# ---------------------------------------------
ERROR = fa.ICON_FA_CIRCLE_XMARK
INFO = fa.ICON_FA_CIRCLE_INFO
SUCCESS = fa.ICON_FA_CIRCLE_CHECK
WARNING = fa.ICON_FA_TRIANGLE_EXCLAMATION

# Actions
# ---------------------------------------------
ADD = fa.ICON_FA_PLUS
CLOSE = fa.ICON_FA_XMARK
COPY = fa.ICON_FA_COPY
DELETE = fa.ICON_FA_TRASH
EDIT = fa.ICON_FA_PEN
PASTE = fa.ICON_FA_PASTE
REDO = fa.ICON_FA_ROTATE_RIGHT
REFRESH = fa.ICON_FA_ARROWS_ROTATE
SAVE = fa.ICON_FA_FLOPPY_DISK
SEARCH = fa.ICON_FA_MAGNIFYING_GLASS
SETTINGS = fa.ICON_FA_GEAR
UNDO = fa.ICON_FA_ROTATE_LEFT

ICON_PACKS = {
    "file": FILE,
    "file-code": FILE_CODE,
    "file-text": FILE_TEXT,
    "file-image": FILE_IMAGE,
    "file-audio": FILE_AUDIO,
    "file-video": FILE_VIDEO,
    "file-unknown": FILE_UNKNOWN,
    "map": MAP,
    "image": IMAGE,
    "film": FILM,
    "font": FONT,
    "folder": FOLDER,
    "folder-open": FOLDER_OPEN,
    "error": ERROR,
    "info": INFO,
    "success": SUCCESS,
    "warning": WARNING,
    "add": ADD,
    "close": CLOSE,
    "copy": COPY,
    "delete": DELETE,
    "edit": EDIT,
    "paste": PASTE,
    "redo": REDO,
    "refresh": REFRESH,
    "save": SAVE,
    "search": SEARCH,
    "settings": SETTINGS,
    "undo": UNDO,
}

DEFAULT_FILE_ICON = FILE_UNKNOWN
"""Used when a file has no known kind and an unknown extension."""

DEFAULT_DOCUMENT_ICON = FILE
"""Used when a document kind has no dedicated """

FILE_KIND_ICONS: Mapping[FileKind, str] = MappingProxyType({
    FileKind.IMAGE: FILE_IMAGE,
    FileKind.MAP: MAP,
    FileKind.ANIMATION: FILM,
    FileKind.SIDECAR: FILE_CODE,
    FileKind.OTHER: FILE_UNKNOWN,
    FileKind.FONT: FONT,
    FileKind.AUDIO: FILE_AUDIO,
})
"""Icon per explorer file kind. Must cover every :class:`FileKind`."""

DOCUMENT_KIND_ICONS: Mapping[DocumentKind, str] = MappingProxyType({
    DocumentKind.MAP: MAP,
    DocumentKind.IMAGE: IMAGE,
})
"""Icon per open-tab document type. Must cover every :class:`DocumentKind`."""

EXTENSION_ICONS: Mapping[str, str] = MappingProxyType({
    # Text and data
    "txt": FILE_TEXT,
    "md": FILE_TEXT,
    "log": FILE_TEXT,
    "csv": FILE_TEXT,
    "json": FILE_CODE,
    "xml": FILE_CODE,
    "yaml": FILE_CODE,
    "yml": FILE_CODE,
    "toml": FILE_CODE,
    "ini": FILE_CODE,
    "cfg": FILE_CODE,
    "py": FILE_CODE,
    # Images
    "png": FILE_IMAGE,
    "jpg": FILE_IMAGE,
    "jpeg": FILE_IMAGE,
    "bmp": FILE_IMAGE,
    "gif": FILE_IMAGE,
    "webp": FILE_IMAGE,
    # Audio and video
    "wav": FILE_AUDIO,
    "ogg": FILE_AUDIO,
    "mp3": FILE_AUDIO,
    "flac": FILE_AUDIO,
    "mp4": FILE_VIDEO,
    "webm": FILE_VIDEO,
    "avi": FILE_VIDEO,
    "mov": FILE_VIDEO,
    # Fonts, documents, archives
    "ttf": FONT,
    "otf": FONT,
    "woff": FONT,
    "woff2": FONT,
})
"""Fallback icon by lower-case extension, without the leading dot."""


class IconSlot:
    """Builds labels whose text always starts at the same x position.

    The measuring functions are injectable so the layout logic can be
    unit-tested without an ImGui context.

    Args:
        measure: Returns the rendered width of a string.
        font_key: Returns the current font size. Results are cached per
            value, so changing the font size recomputes automatically.
    """

    def __init__(self) -> None:
        self._slot_widths: dict[float, float] = {}
        self._paddings: dict[tuple[float, str | None], str] = {}

    def clear_cache(self) -> None:
        """Forget cached widths. Call after the font atlas/font changes."""
        self._slot_widths.clear()
        self._paddings.clear()

    def label(self, icon: str | None, text: str, *, gap: str = DEFAULT_GAP) -> str:
        """Build an aligned label.

        Args:
            icon: str to show, or ``None`` for an empty icon slot.
            text: Label text.
            gap: Spacing between the icon slot and the text.

        Returns:
            A string ready to pass to ImGui.
        """
        glyph = icon if icon is not None else ""
        text = text.strip()
        if not text:
            return glyph
        return f"{glyph}{self.padding(icon)}{gap}{text}"

    def padding(self, icon: str | None) -> str:
        """Return the spaces needed to fill the slot after ``icon``.

        For ``None`` this is a full slot of spaces.
        """
        font_key = imgui.get_font_size()
        cache_key = (font_key, icon)
        padding = self._paddings.get(cache_key)
        if padding is None:
            padding = self._compute_padding(font_key, icon)
            self._paddings[cache_key] = padding
        return padding

    def _slot_width(self, font_key: float) -> float:
        """Width of the widest icon at the current font size."""
        width = self._slot_widths.get(font_key)
        if width is None:
            width = max(text_width(_icon) for _icon in ICON_PACKS.values())
            self._slot_widths[font_key] = width
        return width

    def _compute_padding(self, font_key: float, icon: str | None) -> str:
        space_width = text_width(" ")
        if space_width <= 0:
            return ""
        used = text_width(icon) if icon is not None else 0.0
        missing = self._slot_width(font_key) - used
        return " " * max(0, round(missing / space_width))


_DEFAULT_SLOT = IconSlot()


def with_icon(icon: str | None, text: str, *, gap: str = DEFAULT_GAP) -> str:
    """Build a label with an icon in front of the text.

    Pass ``None`` for rows without an icon: the text still starts at the
    same x as rows that have one.

    Args:
        icon: str to show, or ``None``.
        text: Label text.
        gap: Spacing between the icon slot and the text.

    Returns:
        A string ready to pass to ImGui. Must be called while a frame is
        active, because it measures text with the current font.

    Example:
        >>> imgui.button(with_icon(Icon.SAVE, "Save"))
        >>> imgui.selectable(with_icon(None, "readme.txt"))
    """
    if icon is not None:
        icon = icon.strip()
    if not icon:
        icon = None
    return _DEFAULT_SLOT.label(icon, text, gap=gap)


def clear_icon_cache() -> None:
    """Reset cached widths used by :func:`with_icon`.

    Call this after loading a different font or rebuilding the atlas.
    """
    _DEFAULT_SLOT.clear_cache()


def icon_for_file_kind(kind: FileKind) -> str:
    """Return the explorer icon for a file kind."""
    return FILE_KIND_ICONS.get(kind, DEFAULT_FILE_ICON)


def icon_for_document_kind(kind: DocumentKind) -> str:
    """Return the tab icon for a document type."""
    return DOCUMENT_KIND_ICONS.get(kind, DEFAULT_DOCUMENT_ICON)


def icon_for_extension(extension: str) -> str:
    """Return an icon from a file extension.

    Args:
        extension: Extension with or without the dot, any case
            (``".PNG"``, ``"png"``).

    Returns:
        The matching icon, or :data:`DEFAULT_FILE_ICON` if unknown.
    """
    key = extension.lower().lstrip(".")
    return EXTENSION_ICONS.get(key, DEFAULT_FILE_ICON)


def icon_for_path(path: Path, kind: FileKind | None = None) -> str:
    """Pick the best icon for a file in the explorer.

    A specific ``kind`` wins. For ``None`` or :attr:`FileKind.OTHER` the
    extension decides, so unclassified files like ``notes.txt`` still get
    a meaningful icon instead of the generic "unknown" one.

    Args:
        path: File path (only the suffix is used).
        kind: Classified kind, if the scan already computed it.

    Returns:
        The icon to draw next to the file name.
    """
    if kind is not None and kind is not FileKind.OTHER:
        return icon_for_file_kind(kind)
    return icon_for_extension(path.suffix)


def folder_icon(*, is_open: bool) -> str:
    """Return the folder icon for an expanded or collapsed tree node."""
    return FOLDER_OPEN if is_open else FOLDER
