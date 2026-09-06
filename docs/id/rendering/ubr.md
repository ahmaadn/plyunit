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

`init` → `get_batching_backend()` → `Renderer(ubr=…)` →
`Renderer` requires a configured native UBR backend and its constructor calls
`ubr.init()`. In the current composition root, `Renderer` is constructed before
`app.init(cfg)` initializes the window. Backends that require a live GL context
must account for this ordering; initialization is not deferred to a frame hook.

Kalau `.pyd` load → dipakai. Kalau tidak → error jelas, bukan silent Python path.

## Layers

| Layer | Peran |
|--------|--------|
| Port | `IUnifiedBufferBatch.submit_frame` |
| Domain | `FrameBuffer` SoA + sort/runs (tanpa trig/UV expand) |
| Adapter | `raylib/batching/ubr.py` bind rlgl → native |
| Native | `plyunit._plyunit_batch`: `ubr_init` / `ubr_submit_frame` |

## Flow

```
submit_*  → FrameBuffer in-place (UV resolved)
render    → sort texture (opaque) / sort_key (EFFECTS)
          → ONE ubr_submit_frame(...)  # expand+upload+draw in C
```

## API native

- `set_rlgl(dict)` — pointer rlgl dari proses pyray
- `ubr_init(max_sprites)`
- `ubr_submit_frame(pos, size, origin, rot, rgba, uv, starts, counts, tex, n, n_runs)`
- `ubr_shutdown()`

`MAX_SPRITES` default **16384** (satu konstanta, parameter `max_sprites`).
