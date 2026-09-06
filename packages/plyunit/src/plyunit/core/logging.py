"""Logging helpers for plyunit applications."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(
    log_level: str,
    log_file_path: str,
) -> None:
    """Configures root logging for the application.

    Sets the root log level, adds a console handler (Rich when available,
    falling back to ``StreamHandler``) and a file handler for the given path.
    The parent directory of ``log_file_path`` is created if it does not
    exist yet.

    Args:
        log_level: Minimum level for recorded messages, e.g. ``"INFO"``,
            ``"DEBUG"``, ``"WARNING"``, ``"ERROR"``. Case-insensitive.
        log_file_path: Path to the destination log file. The parent
            directory is created automatically.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    console_formatter = logging.Formatter(
        "%(levelname)s: %(name)s: %(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console: prefer `rich` for colorful output, fall back to simple stream handler
    try:
        from rich.logging import RichHandler

        console_handler = RichHandler(
            rich_tracebacks=True,
            show_time=False,
            show_level=False,
        )
    except (Exception, ImportError):
        # Console log format matches pyray
        console_handler = logging.StreamHandler()

    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    # Add console handler (rich or fallback)
    root_logger.addHandler(console_handler)

    file_path = Path(log_file_path).expanduser()
    if file_path.parent != Path(""):
        file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Mark the file handler to identify it as a plyunit logging handler
    # setattr(file_handler, LOGGING_HANDLER_MARKER, True)
    root_logger.addHandler(file_handler)
