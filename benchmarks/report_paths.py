"""Central report path helpers for all plyunit benchmarks.

All benchmark reports land under ``benchmarks/reports/`` (monorepo root)
with a timestamp suffix, unless the user passes an absolute path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def report_timestamp(when: datetime | None = None) -> str:
    """Local timestamp suitable for filenames: ``YYYYMMDD_HHMMSS``."""
    return (when or datetime.now()).strftime("%Y%m%d_%H%M%S")


def default_report_path(
    stem: str,
    *,
    suffix: str = ".txt",
    when: datetime | None = None,
) -> Path:
    """``benchmarks/report/<stem>_<timestamp><suffix>``."""
    clean = stem.strip().removesuffix(suffix).removesuffix(".txt").removesuffix(".json")
    if not clean:
        clean = "benchmark"
    ts = report_timestamp(when)
    return REPORT_DIR / f"{clean}_{ts}{suffix}"


def resolve_report_path(
    report_file: str | None,
    *,
    default_stem: str,
    suffix: str = ".txt",
    when: datetime | None = None,
) -> Path:
    """Resolve CLI ``--report-file`` into a concrete path under report/.

    Rules:
    - ``None`` / empty → ``report/<default_stem>_<ts>.txt``
    - relative name → ``report/<stem>_<ts>.ext`` (forced under report/)
    - absolute path → used as-is (parent dirs created; no forced timestamp)

    Timestamp is always appended for non-absolute names so re-runs never
    overwrite previous artifacts (unless the stem already ends with
    ``_YYYYMMDD_HHMMSS``).
    """
    ts = report_timestamp(when)
    raw = (report_file or "").strip()

    if not raw:
        path = default_report_path(default_stem, suffix=suffix, when=when)
    else:
        candidate = Path(raw)
        if candidate.is_absolute():
            path = candidate
        else:
            name = candidate.name
            if not name:
                path = default_report_path(default_stem, suffix=suffix, when=when)
            else:
                p = Path(name)
                ext = p.suffix if p.suffix else suffix
                stem = p.stem if p.stem else default_stem
                if _looks_timestamped(stem):
                    path = REPORT_DIR / f"{stem}{ext}"
                else:
                    path = REPORT_DIR / f"{stem}_{ts}{ext}"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_report_json_path(
    report_json: str | None,
    *,
    text_report: Path,
) -> Path | None:
    """Optional JSON report path.

    - empty → None
    - absolute → as-is
    - relative bare name → under report/, timestamped or sibling of text report
    """
    raw = (report_json or "").strip()
    if not raw:
        return None

    candidate = Path(raw)
    if candidate.is_absolute():
        path = candidate
    else:
        name = candidate.name or "report.json"
        p = Path(name)
        ext = p.suffix if p.suffix else ".json"
        # Prefer sibling of text report when user only wants "also json"
        if not p.stem or p.stem in {"reports", "json", "node_benchmark"}:
            path = text_report.with_suffix(ext)
        elif _looks_timestamped(p.stem):
            path = REPORT_DIR / f"{p.stem}{ext}"
        else:
            # Match text report timestamp if present
            text_stem = text_report.stem
            if _looks_timestamped(text_stem) and text_stem.startswith(p.stem):
                path = text_report.with_suffix(ext)
            else:
                path = REPORT_DIR / f"{p.stem}_{report_timestamp()}{ext}"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_text_report(path: Path | str, body: str) -> Path:
    """Write report body (adds trailing newline) and return resolved path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = body if body.endswith("\n") else body + "\n"
    out.write_text(text, encoding="utf-8")
    return out


def _looks_timestamped(stem: str) -> bool:
    """True if stem ends with ``_YYYYMMDD_HHMMSS``."""
    parts = stem.rsplit("_", 2)
    if len(parts) < 3:
        return False
    date_part, time_part = parts[-2], parts[-1]
    return (
        len(date_part) == 8
        and date_part.isdigit()
        and len(time_part) == 6
        and time_part.isdigit()
    )
