"""File role classification for the project explorer.

Every file found by a project scan is classified into a
:class:`FileKind` value. This decides the icon shown in the tree,
whether the file can be opened as a document tab, and whether it
survives the "editor files only" toggle.
"""

from __future__ import annotations

from enum import Enum


class FileKind(Enum):
    """The role of a file inside the editor.

    Values double as sort keys in the UI, so do not change them without
    updating the icon mapping in ``scripts.ui.panels.explorer``.
    """

    IMAGE = "image"
    MAP = "map"
    ANIMATION = "animation"
    SIDECAR = "sidecar"
    OTHER = "other"
    FONT = "font"
    AUDIO = "audio"

    @property
    def is_openable(self) -> bool:
        """True when clicking this file opens a document tab."""
        return self not in (
            FileKind.OTHER,
            FileKind.ANIMATION,
            FileKind.AUDIO,
            FileKind.FONT,
        )

    @property
    def is_relevant(self) -> bool:
        """True when the file shows in "editor files only" mode."""
        return self is not FileKind.OTHER
