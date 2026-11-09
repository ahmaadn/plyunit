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

`plyunit._bootstrap.init` selects `Canvas2D()` and `UnifiedBufferBatch`, then
injects them into `Renderer(canvas=…, ubr=…)`. Construction only prepares
neutral CPU buffers. `app.init(cfg)` opens the window, sets up the default
camera, and then calls `Renderer.init()` → `ubr.init(max_sprites)` with a live
GL context. Optional GPU services are constructed afterward, before `on_load`.

The batch contract lives at `plyunit.backends.ports.renderer.IUnifiedBufferBatch`.
Neutral renderer code never imports raylib or accesses raw texture fields.

If the `.pyd` loads → it is used. Otherwise → a clear error, not a silent
Python path.

## Layers

| Layer | Role |
|--------|--------|
| Port | `IUnifiedBufferBatch.texture_id(handle)` / `submit_frame` |
| Domain | `FrameBuffer` SoA + sort/runs (no trig/UV expansion) |
| Adapter | `backends/integrations/raylib/renderer/ubr.py` binds rlgl → native |
| Native | `plyunit._plyunit_batch`: `ubr_init` / `ubr_submit_frame` |

## Flow

```
render_sprite / render_batch / render_sprites / render_shaped_text
           → FrameBuffer in-place (UV resolved)
flush_all  → sort by texture (ordinary layers) / depth/y-sort
           → ubr_submit_frame(...) per flush group (expand+upload+draw in C)
```

`Texture2DHandle.texture_id` is a logical string asset ID.
`batch.texture_id(handle)` resolves the numeric GPU ID used by `tex_id` and
native run arrays; regions share their parent's GPU ID. Core must not read
`raw_texture.id` or use a logical ID as the numeric batch key.
Shaped text carries a borrowed font-atlas handle and enters the same SoA path.

If a compiler was installed after an earlier sync left the extension missing:

```bash
uv sync --reinstall-package plyunit-native
./verify.sh
```

## Native API

- `set_rlgl(dict)` — rlgl pointers from the pyray process
- `ubr_init(max_sprites)`
- `ubr_submit_frame(pos, size, origin, rot, rgba, uv, starts, counts, tex, n, n_runs)`
- `ubr_shutdown()`

`MAX_SPRITES` defaults to **16384** (a single constant, `max_sprites` parameter).
