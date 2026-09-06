"""Plyunit benchmarks (bunny, node, physics, shapes).

Reports are written under ``benchmarks/report/`` with timestamps.
See ``report_paths.py``.
"""

from .report_paths import (
    REPORT_DIR,
    default_report_path,
    resolve_report_path,
    write_text_report,
)

__all__ = [
    "REPORT_DIR",
    "default_report_path",
    "resolve_report_path",
    "write_text_report",
]
