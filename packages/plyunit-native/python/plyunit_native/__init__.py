"""Meta package for plyunit UBR C extension (required for sprite draw).

Compiled module: ``plyunit._plyunit_batch``
(``ubr_init`` / ``ubr_submit_frame`` / ``set_rlgl``).
"""

from __future__ import annotations

__version__ = "0.2.1"


def _load_ext():
    """Import the compiled UBR extension module, or return ``None``.

    Tries each known (package, module) pair in order; the first import
    that succeeds wins.
    """
    for pkg, name in (
        ("plyunit", "_plyunit_batch"),
    ):
        try:
            return __import__(f"{pkg}.{name}", fromlist=[name])
        except Exception:
            continue
    return None


def is_extension_available() -> bool:
    """True if a bulk sprite C extension can be imported."""
    return _load_ext() is not None


def extension_version() -> str | None:
    """Return the version reported by the C extension, if available.

    Returns:
        The extension version string, or ``None`` when the extension is
        missing or does not expose a ``version``.
    """
    ext = _load_ext()
    if ext is None:
        return None
    version = getattr(ext, "version", None)
    if callable(version):
        return str(version())
    return None
