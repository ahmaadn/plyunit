from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from imgui_bundle import icons_fontawesome_6 as fa

from scripts.core.file_kind import FileKind
from scripts.state.document import DocumentKind

DEFAULT_GAP = " "
"""Spacing placed between an icon and its text label."""


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


def with_icon(icon: str, text: str, *, gap: str = DEFAULT_GAP) -> str:
    """Build a label with an icon in front of the text.

    Args:
        icon: Icon to show.
        text: Label text.
        gap: Spacing between icon and text.

    Returns:
        ``"<glyph><gap><text>"``, ready to pass to ImGui.

    Example:
        >>> label = with_icon(SAVE, "Save")
    """
    return f"{icon}{gap}{text}"


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
