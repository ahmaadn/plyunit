"""Native file dialogs (tkinter), isolated and headless-safe.

The editor runs inside a GLFW window, so dialogs open a short-lived
hidden Tk root on top of it. Any failure (no tkinter, no display) turns
into ``None`` instead of crashing the editor.

Usage::

    from scripts import dialogs

    path = dialogs.ask_open_file("Open map", filetypes=(("Map", "*.map"),))
    target = dialogs.ask_save_file("Save map", default_name="untitled.map")
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def ask_open_file(
    title: str = "Open File",
    filetypes: tuple[tuple[str, str], ...] = (("All files", "*.*"),),
) -> str | None:
    """Ask the user for an existing file.

    Args:
        title: Dialog window title.
        filetypes: ``(label, pattern)`` pairs for the filter dropdown.

    Returns:
        The chosen path, or ``None`` when cancelled/unavailable.
    """
    return _run_dialog("askopenfilename", title, filetypes=filetypes)


def ask_save_file(
    title: str = "Save File",
    default_name: str = "",
    filetypes: tuple[tuple[str, str], ...] = (("All files", "*.*"),),
) -> str | None:
    """Ask the user for a save destination.

    Args:
        title: Dialog window title.
        default_name: Pre-filled file name.
        filetypes: ``(label, pattern)`` pairs for the filter dropdown.

    Returns:
        The chosen path, or ``None`` when cancelled/unavailable.
    """
    return _run_dialog(
        "asksaveasfilename",
        title,
        filetypes=filetypes,
        initialfile=default_name,
    )


def ask_project_folder(title: str = "Open Project") -> str | None:
    """Ask the user for an existing project folder.

    Args:
        title: Dialog window title.

    Returns:
        The chosen path, or ``None`` when cancelled/unavailable.
    """
    return _run_dialog("askdirectory", title)


def _run_dialog(action: str, title: str, **kwargs: Any) -> str | None:
    """Create a hidden Tk root, run one dialog, and always tear it down.

    Args:
        action: ``tkinter.filedialog`` function name.
        title: Dialog window title.
        **kwargs: Forwarded to the dialog function.

    Returns:
        The chosen path, or ``None`` when cancelled/unavailable.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        logger.warning("tkinter is unavailable; cannot show '%s' dialog", title)
        return None

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        run: Callable[..., str] = getattr(filedialog, action)
        chosen = run(title=title, **kwargs)
        return str(chosen) or None
    except Exception:
        logger.exception("File dialog '%s' failed", title)
        return None
    finally:
        if root is not None:
            with contextlib.suppress(Exception):
                root.destroy()
