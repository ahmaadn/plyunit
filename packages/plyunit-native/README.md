# plyunit-native

C extension for [plyunit](../plyunit) **UBR** sprite rendering (`plyunit._plyunit_batch`).

Sprite draw is **C-only**. Installing this package should produce the extension
whenever a compiler is present — **no env var required**.

## Install (builds by default)

plyunit is **not published to PyPI** — use the monorepo workspace:

```bash
# one-liner from a fresh clone (setup + native build + verify):
./init.sh
# or target the plyunit package + extras directly:
uv sync --package plyunit --extra raylib --extra native
```

On install, `setup.py` **attempts to compile** `plyunit._plyunit_batch` if
`cl` / `gcc` / `clang` (or VS Build Tools) is available.

**Compiler selection (Windows):** setuptools defaults to MSVC; when MSVC is
absent but a MinGW-w64 `gcc` is on `PATH`, the build automatically uses
`--compiler=mingw32` instead (no manual flags needed).

**Editable installs (uv workspace):** after a successful build, `setup.py`
copies the built `plyunit/*.pyd`/`*.so` into the sibling editable tree
`../plyunit/src/plyunit/`, where `from plyunit import _plyunit_batch`
resolves. Without this step the artifacts would stay in `build/lib.*` and
never be importable.

| Result | Meaning |
|--------|---------|
| `.pyd` / `.so` present | Runtime UBR works after `bootstrap_app` |
| Meta-only (no compiler / build error) | `pip` may still succeed; **engine raises at Renderer init** |

### Opt-out of compile (rare)

```bash
export PLYUNIT_SKIP_NATIVE_BUILD=1
uv sync --reinstall-package plyunit-native
```

Legacy: `PLYUNIT_BUILD_NATIVE=0` also skips.  
`PLYUNIT_BUILD_NATIVE=1` is **no longer required** (build is default).

### Windows MinGW (manual fallback)

Usually not needed — the build auto-selects `mingw32` when MSVC is missing
and `gcc` is on `PATH`. If you need to force it:

```powershell
cd packages/plyunit-native
python setup.py build_ext --inplace --compiler=mingw32
# artifacts are copied into ../plyunit/src/plyunit/ automatically
```

## Runtime — no `app.use_native_rendering()`

Native is **not** an optional toggle. Composition root already wires UBR:

```text
bootstrap_app → get_batching_backend() → Renderer(ubr=…) → ubr.init()
```

- Extension missing → **fail-fast** `RuntimeError` at init (clear message).
- Extension present → used automatically; game code only calls `submit_*`.

Do **not** add a public `use_native_rendering()` API — it would imply Python
draw is still available.

## Verify

From the monorepo root: `./verify.sh` (or `uv run python scripts/verify_install.py`).
Minimal manual check:

```python
import plyunit_native
assert plyunit_native.is_extension_available(), "rebuild plyunit-native"
print(plyunit_native.extension_version())

from plyunit import _plyunit_batch
print(_plyunit_batch.version())  # e.g. 0.2.0-ubr
```

## Layout

```
include/plyunit_batch.h
src/ubr.c                 # expand + VBO + draw
src/module.c              # Python module
python/plyunit_native/    # meta helpers
setup.py                  # build-by-default Extension
```

Never links a second raylib — rlgl function pointers are bound from the
same pyray process at `ubr.init()`.
