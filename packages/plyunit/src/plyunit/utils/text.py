"""Text-formatting helpers."""

from __future__ import annotations


def bstr(s: str | bytes) -> bytes:
    """Convert a string to bytes for raylib's ``DrawText``.

    The raylib C API takes ``const char*`` — the Python binding needs
    ``bytes``. ``bstr()`` ensures Python strings are converted automatically.

    Args:
        s: Python string or bytes.

    Returns:
        bytes: Bytes representation ready for the raylib binding.

    Example:
        >>> DrawText(bstr("Score: 100"), 14, 14, 20, WHITE)
        >>> DrawText(bstr(f"HP: {self.hp}"), 14, 40, 16, RED)
    """
    return s.encode() if isinstance(s, str) else s
