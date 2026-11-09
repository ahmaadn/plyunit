# Unified Buffer Renderer (UBR) — C-only

**Tidak ada fallback Python** untuk draw sprite. Satu FFI per flush grup:
`ubr_submit_frame` (expand + VBO upload + draw runs di native).

## Install (native builds by default)

plyunit belum ada di PyPI — gunakan workspace monorepo:

```bash
./init.sh   # setup penuh setelah clone, atau:
uv sync --package plyunit --extra raylib --extra native
```

`plyunit-native` **mencoba compile otomatis** saat install jika `cl`/`gcc`/`clang`
ada di PATH. **Tidak perlu** `PLYUNIT_BUILD_NATIVE=1`. Di Windows, `gcc`
MinGW-w64 dipilih otomatis saat MSVC tidak ada.

| Situasi | Perilaku |
|---------|----------|
| Compiler ada, build OK | `.pyd` terpasang → UBR aktif lewat bootstrap |
| Compiler tidak ada / build gagal | sync bisa sukses (meta only) → **fail-fast di `Renderer` init** |
| Skip compile sengaja | `PLYUNIT_SKIP_NATIVE_BUILD=1` |

Fallback MinGW manual (jarang diperlukan):

```powershell
cd packages/plyunit-native
python setup.py build_ext --inplace --compiler=mingw32
```

Tanpa ekstensi → `RuntimeError` fatal di `Renderer` / `ubr.init()`.

### Runtime: tidak ada toggle

**Jangan** `app.use_native_rendering()`. Native bukan opsi — sudah di-wire:

`plyunit._bootstrap.init` selects `Canvas2D()` and `UnifiedBufferBatch`, then
injects them into `Renderer(canvas=…, ubr=…)`. Construction only prepares
neutral CPU buffers. `app.init(cfg)` opens the window, sets up the default
camera, and then calls `Renderer.init()` → `ubr.init(max_sprites)` with a live
GL context. Optional GPU services are constructed afterward, before `on_load`.

The batch contract lives at `plyunit.backends.ports.renderer.IUnifiedBufferBatch`.
Neutral renderer code never imports raylib or accesses raw texture fields.

Kalau `.pyd` load → dipakai. Kalau tidak → error jelas, bukan silent Python path.

## Layers

| Layer | Peran |
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

## API native

- `set_rlgl(dict)` — pointer rlgl dari proses pyray
- `ubr_init(max_sprites)`
- `ubr_submit_frame(pos, size, origin, rot, rgba, uv, starts, counts, tex, n, n_runs)`
- `ubr_shutdown()`

`MAX_SPRITES` default **16384** (satu konstanta, parameter `max_sprites`).
