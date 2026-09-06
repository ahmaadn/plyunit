"""Build ``plyunit._plyunit_batch`` (UBR C extension).

**Default: always attempt to compile** when a C compiler is available.
No ``PLYUNIT_BUILD_NATIVE`` env is required for ``uv sync`` (or ``./init.sh``
in the monorepo; plyunit is not published to PyPI).

Opt-out (CI / docs-only meta package without toolchain)::

    PLYUNIT_SKIP_NATIVE_BUILD=1

If the compiler is missing or the build fails, install still succeeds as a
meta package, but the **engine fail-fast at Renderer init** (no Python draw
path). That is intentional — a successful sync without a ``.pyd`` must not
silently look "working" at game runtime.
"""

from __future__ import annotations

import os
import shutil
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext as _build_ext


def _env_truthy(name: str) -> bool:
    """Return True when the env var is set to an affirmative value."""
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def _env_falsey(name: str) -> bool:
    """Return True when the env var is set to a negative value."""
    return os.environ.get(name, "").lower() in {"0", "false", "no", "off"}


def _want_build() -> bool:
    """Decide whether the C extension should be compiled.

    Explicit skip (``PLYUNIT_SKIP_NATIVE_BUILD``) always wins; the legacy
    ``PLYUNIT_BUILD_NATIVE=0`` opt-out is still honored. When neither is
    set, the build is on by default.
    """
    # Explicit skip wins.
    if _env_truthy("PLYUNIT_SKIP_NATIVE_BUILD"):
        return False
    # Legacy opt-out still honored if set to 0/false; if unset → build.
    return not _env_falsey("PLYUNIT_BUILD_NATIVE")


def _msvc_looks_available() -> bool:
    """Heuristic: usable MSVC (``cl`` on PATH or a VS installer present)."""
    if shutil.which("cl"):
        return True
    if sys.platform == "win32":
        vswhere = os.path.expandvars(
            r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
        )
        return os.path.isfile(vswhere)
    return False


def _looks_like_compiler_available() -> bool:
    """Heuristically check for a C compiler (cl/gcc/clang or VS Build Tools)."""
    if shutil.which("gcc") or shutil.which("clang"):
        return True
    return _msvc_looks_available()


_HERE = os.path.dirname(os.path.abspath(__file__))
# Editable source tree of the sibling ``plyunit`` workspace member.
_MONOREPO_PLYUNIT_SRC = os.path.normpath(
    os.path.join(_HERE, os.pardir, "plyunit", "src", "plyunit")
)

_BUILD_HELP = (
    "  UBR requires this extension at runtime (no Python sprite draw path).\n"
    "  Install a C toolchain, then reinstall:\n"
    "    uv sync --reinstall-package plyunit-native\n"
    "  Windows MinGW example:\n"
    "    python setup.py build_ext --inplace --compiler=mingw32\n"
    "  Opt-out of compile attempts: PLYUNIT_SKIP_NATIVE_BUILD=1"
)


def _copy_exts_into_monorepo_plyunit(build_lib: str) -> None:
    """Copy built ``plyunit.*`` ext modules into the sibling editable tree.

    ``uv sync`` installs workspace members in editable
    mode, so ``plyunit`` resolves to ``packages/plyunit/src/plyunit``. Without
    this copy the freshly built ``.pyd``/``.so`` files stay stranded in
    ``build/lib.*`` and ``from plyunit import _plyunit_batch`` fails.

    No-op outside the monorepo (no sibling tree) or when nothing was built.
    """
    built = os.path.join(build_lib, "plyunit")
    if not os.path.isdir(built) or not os.path.isdir(_MONOREPO_PLYUNIT_SRC):
        return
    for name in sorted(os.listdir(built)):
        if name.endswith((".pyd", ".so")):
            shutil.copy2(
                os.path.join(built, name),
                os.path.join(_MONOREPO_PLYUNIT_SRC, name),
            )
            print(f"plyunit-native: installed {name} -> {_MONOREPO_PLYUNIT_SRC}")


class SoftFailBuildExt(_build_ext):
    """Install succeeds even if compile fails; runtime will fail-fast clearly."""

    def finalize_options(self) -> None:
        """Pick a compiler that actually exists.

        On Windows setuptools defaults to MSVC and fails with
        "Microsoft Visual C++ 14.0 or greater is required" even when a
        MinGW-w64 gcc is on PATH. Fall back to ``mingw32`` in that case;
        an explicit ``--compiler=...`` always wins.
        """
        super().finalize_options()
        if getattr(self, "compiler", None):
            return
        use_mingw = (
            sys.platform == "win32"
            and shutil.which("gcc")
            and not _msvc_looks_available()
        )
        if use_mingw:
            self.compiler = "mingw32"
            print("plyunit-native: MSVC not found, using MinGW-w64 (gcc).")

    def run(self) -> None:
        """Run the build, downgrading any failure to a stderr warning."""
        if not self.extensions:
            return
        try:
            super().run()
            if not self.inplace:
                # uv/pip editable (PEP 660) builds land in build/lib only.
                _copy_exts_into_monorepo_plyunit(self.build_lib)
        except Exception as exc:
            print(
                "WARNING: plyunit-native: C extension not built "
                f"({exc.__class__.__name__}: {exc}).\n{_BUILD_HELP}",
                file=sys.stderr,
            )
            self.extensions = []

    def copy_extensions_to_source(self) -> None:
        """Route ``--inplace`` artifacts into the monorepo plyunit tree."""
        if os.path.isdir(_MONOREPO_PLYUNIT_SRC):
            _copy_exts_into_monorepo_plyunit(self.build_lib)
            return
        super().copy_extensions_to_source()

    def build_extension(self, ext) -> None:
        """Build one extension, downgrading failure to a stderr warning."""
        try:
            super().build_extension(ext)
        except Exception as exc:
            print(
                f"WARNING: plyunit-native: failed to build {ext.name}: {exc}\n"
                f"{_BUILD_HELP}",
                file=sys.stderr,
            )


ext_modules: list[Extension] = []
if _want_build():
    if not _looks_like_compiler_available():
        print(
            "WARNING: plyunit-native: no C compiler on PATH (cl/gcc/clang).\n"
            "  Installing meta package only (no _plyunit_batch).\n"
            f"{_BUILD_HELP}",
            file=sys.stderr,
        )
    else:
        ext_modules = [
            Extension(
                "plyunit._plyunit_batch",
                sources=[
                    "src/ubr.c",
                    "src/module.c",
                ],
                include_dirs=["include"],
                define_macros=[("PLYUNIT_BATCH_EXPORTS", "1")],
            ),
            Extension(
                "plyunit._fb_fast",
                sources=["src/fb_fast.c"],
            ),
        ]
else:
    print(
        "plyunit-native: skipping C build (PLYUNIT_SKIP_NATIVE_BUILD or "
        "PLYUNIT_BUILD_NATIVE=0).",
        file=sys.stderr,
    )

setup(
    name="plyunit-native",
    ext_modules=ext_modules,
    cmdclass={"build_ext": SoftFailBuildExt},
    packages=["plyunit_native"],
    package_dir={"plyunit_native": "python/plyunit_native"},
    zip_safe=False,
)
