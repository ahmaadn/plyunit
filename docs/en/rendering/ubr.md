# Unified Buffer Renderer (UBR) — C-only

**There is no Python fallback** for sprite drawing. One FFI call per flush
group: `ubr_submit_frame` (expand + VBO upload + draw runs in native code).

## Install (native builds by default)

plyunit is not published to PyPI — use the monorepo workspace:

```bash
./init.sh   # full setup after cloning, or:
uv sync --package plyunit --extra raylib --extra native
```

`plyunit-native` **attempts to compile automatically** at install time when
`cl`/`gcc`/`clang` is on PATH. `PLYUNIT_BUILD_NATIVE=1` is **not** needed.
On Windows, MinGW-w64 `gcc` is picked automatically when MSVC is absent.

| Situation | Behavior |
|---------|----------|
| Compiler present, build OK | `.pyd` installed → UBR active via bootstrap |
| Compiler missing / build fails | sync can still succeed (meta only) → **fail-fast at `Renderer` init** |
| Deliberately skipping compile | `PLYUNIT_SKIP_NATIVE_BUILD=1` |

Manual MinGW fallback (rarely needed):

```powershell
cd packages/plyunit-native
python setup.py build_ext --inplace --compiler=mingw32
```

Without the extension → fatal `RuntimeError` at `Renderer` / `ubr.init()`.

### Runtime: no toggle

**Do not** call `app.use_native_rendering()`. Native is not an option — it is
wired in:

`init` → `get_batching_backend()` → `Renderer(ubr=…)` →
`Renderer` requires a configured native UBR backend and its constructor calls
`ubr.init()`. In the current composition root, `Renderer` is constructed before
`app.init(cfg)` initializes the window. Backends that require a live GL context
must account for this ordering; initialization is not deferred to a frame hook.

If the `.pyd` loads → it is used. Otherwise → a clear error, not a silent
Python path.

## Layers

| Layer | Role |
|--------|--------|
| Port | `IUnifiedBufferBatch.submit_frame` |
| Domain | `FrameBuffer` SoA + sort/runs (no trig/UV expansion) |
| Adapter | `raylib/batching/ubr.py` binds rlgl → native |
| Native | `plyunit._plyunit_batch`: `ubr_init` / `ubr_submit_frame` |

## Flow

```
submit_*  → FrameBuffer in-place (UV resolved)
render    → sort by texture (opaque) / sort_key (EFFECTS)
           → ONE ubr_submit_frame(...)  # expand+upload+draw in C
```

## Native API

- `set_rlgl(dict)` — rlgl pointers from the pyray process
- `ubr_init(max_sprites)`
- `ubr_submit_frame(pos, size, origin, rot, rgba, uv, starts, counts, tex, n, n_runs)`
- `ubr_shutdown()`

`MAX_SPRITES` defaults to **16384** (a single constant, `max_sprites` parameter).
