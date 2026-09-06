# Batch render

> Panduan game: [rendering/index.md](rendering/index.md)
> Arsitektur UBR: [rendering/ubr.md](rendering/ubr.md)

## Ringkas

Banyak sprite dengan texture yang sama di-antri lewat `render_batch`
(atau `render_sprite` per item) ke **FrameBuffer SoA**, di-sort by `tex_id`,
lalu digambar dengan **satu** panggilan native `ubr_submit_frame` per flush grup.

**Tidak ada fallback Python** untuk draw sprite produksi. Extensi
`plyunit-native` wajib; tanpa itu `Renderer` fail-fast saat init.

## Aturan sort

```
FrameBuffer → sort by tex_id (opaque) / sort_key (depth/y-sort layers)
           → runs (start, count, tex_id)
           → ubr_submit_frame(...)
```

Pass dan layer diurutkan lebih dulu. Layer depth/y-sort menjaga urutan depth;
layer sprite biasa dapat dikelompokkan ulang berdasarkan texture untuk run GPU
yang panjang, sehingga `z` bukan jaminan painter order yang ketat pada layer itu.

## SoA layout (FrameBuffer)

| Buffer | dtype | shape |
| --- | --- | --- |
| `pos_xy` | float32 | `(n, 2)` |
| `size_wh` | float32 | `(n, 2)` |
| `origin_xy` | float32 | `(n, 2)` |
| `rotation_deg` | float32 | `(n,)` |
| `rgba` | uint8 | `(n, 4)` |
| `uv_rect` | float32 | `(n, 4)` UV 0–1 |
| `tex_id` | int32 | `(n,)` |
| runs | int32 | `(run_count, 3)` → `(start, count, tex_id)` |

Kapasitas default: **16384** (`MAX_SPRITES` / `max_sprites`).

## C / plyunit-native

- Package: **`plyunit-native`**
- Module: `plyunit._plyunit_batch`
- API: `ubr_init` / `ubr_submit_frame` / `ubr_shutdown` / `set_rlgl`
- Wire: `init` → `get_batching_backend()` → `Renderer(ubr=…)`

```bash
uv sync --package plyunit --extra raylib --extra native
```

| Condition | Path |
| --- | --- |
| Extension + binding OK | `ubr_submit_frame` (satu-satunya path) |
| Extension hilang / gagal load | `RuntimeError` di `Renderer` init — **bukan** silent Python |

## Bunny performance targets

Primary acceptance: flat `render_batch` (not 8k NodeUnits).

```bash
# 8000 @ 60 FPS strict (≥57 avg) → benchmarks/reports/bunny_8k_60_<ts>.txt
uv run --package plyunit plyunit-bunny-benchmark \
  --initial-bunnies 8000 --target-bunnies 8000 --max-bunnies 8000 \
  --target-fps 60 --fps-mode capped \
  --warmup-seconds 1 --stability-seconds 10 --duration-seconds 0 \
  --auto-stop-on-target --profile strict \
  --report-file bunny_8k_60.txt --no-overlay

# 10000 @ 30 FPS strict (≥28.5 avg)
uv run --package plyunit plyunit-bunny-benchmark \
  --initial-bunnies 10000 --target-bunnies 10000 --max-bunnies 10000 \
  --target-fps 30 --fps-mode capped \
  --warmup-seconds 1 --stability-seconds 10 --duration-seconds 0 \
  --auto-stop-on-target --profile strict \
  --report-file bunny_10k_30.txt --no-overlay
```

All benchmark reports: `benchmarks/reports/*_<YYYYMMDD_HHMMSS>.txt`.

Catat CPU/GPU/OS saat menyimpan hasil benchmark.

## Hot path recipe

```python
# sim: float32 (n,2)
renderer.render_batch(
    texture=tex,
    positions=pos_xy,
    pos_xy=pos_xy,
    layer=int(Layer.ENTITIES),
    z=0,
)
```

## See also

- [rendering/ubr.md](rendering/ubr.md)
- [architecture-plan-alignment.md](architecture-plan-alignment.md)
