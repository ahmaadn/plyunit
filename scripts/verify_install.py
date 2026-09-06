"""Verify the plyunit workspace install (deps + native C extensions).

Run from the monorepo root::

    uv run python scripts/verify_install.py   # or ./verify.sh

Checks that the Python env, raylib and both compiled extension modules
(``plyunit._plyunit_batch``, ``plyunit._fb_fast``) are importable, then
prints versions. Exits non-zero with actionable hints on failure.
"""

from __future__ import annotations

import importlib
import sys

_FIX_HINTS = """Fix:
  1) Install a C toolchain (MSVC Build Tools, or MinGW-w64 gcc on PATH).
  2) Rebuild the extension:
       uv sync --reinstall-package plyunit-native
     or (MinGW fallback):
       cd packages/plyunit-native && python setup.py build_ext --inplace \
--compiler=mingw32
  3) Re-run: ./verify.sh"""


def _ok(label: str, detail: str) -> None:
    print(f"  [ok]   {label:<18} {detail}")


def _fail(label: str, detail: str) -> None:
    print(f"  [FAIL] {label:<18} {detail}")


def _ext_version(module: object) -> str:
    version = getattr(module, "version", None)
    return str(version()) if callable(version) else "imported"


def main() -> int:
    failures: list[str] = []

    print("plyunit workspace check")
    _ok("python", f"{sys.version.split()[0]} ({sys.executable})")

    try:
        plyunit = importlib.import_module("plyunit")
        _ok("plyunit", f"{plyunit.__version__} ({plyunit.__file__})")
    except Exception as exc:  # pragma: no cover - env-dependent
        failures.append("plyunit")
        _fail("plyunit", f"import failed: {exc}")
        print(_FIX_HINTS)
        return 1

    try:
        import raylib  # noqa: F401

        _ok("raylib", "loaded")
    except Exception as exc:
        failures.append("raylib")
        _fail("raylib", f"import failed: {exc}")

    for name in ("_plyunit_batch", "_fb_fast"):
        try:
            ext = importlib.import_module(f"plyunit.{name}")
            _ok(name, _ext_version(ext))
        except Exception as exc:
            failures.append(name)
            _fail(name, f"import failed: {exc}")

    if "_plyunit_batch" in failures or "_fb_fast" in failures:
        print(_FIX_HINTS)
        return 1

    print("All checks passed. Try: uv run python examples/cli.py --shapes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
