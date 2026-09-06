# plyunit rendering guide

Panduan rendering untuk game yang dibangun di atas **plyunit**. Mulai dari sini, lalu ikuti topik yang relevan.

**Semua dokumen engine:** [../index.md](../index.md)

## Baca dulu

| Dokumen | Isi |
| --- | --- |
| [**ubr.md**](ubr.md) | **UBR (current):** FrameBuffer SoA → sort → `ubr_submit_frame` |
| [best-practices.md](best-practices.md) | Decision tree, do/don't, checklist performa |
| [queued-submit.md](queued-submit.md) | `render_sprite`, `render_batch`, `render_sprites`, primitives, text, sorting |
| [layers-sort-cull.md](layers-sort-cull.md) | Layer, z, y-sort, frustum cull, SpatialIndex |

## Dokumen terkait (root `docs/`)

| Dokumen | Isi |
| --- | --- |
| [../node-rendering-guide.md](../node-rendering-guide.md) | NodeUnit + SpriteRenderer patterns |
| [../batch-render.md](../batch-render.md) | Batch sprite, native C, target FPS bunny |
| [../frame-execution-order.md](../frame-execution-order.md) | Sync → spatial → physics → render |
| [../architecture-plan-alignment.md](../architecture-plan-alignment.md) | PLAN ↔ implementation map |

## Satu slide mental model

```
Game logic (update)
    │
    ▼
TransformStore.sync()  (+ optional SpatialIndex.refresh_scene)
    │
    ▼
Scene DFS render_submit  (optional frustum cull)
    │  SpriteRenderer / render_* / render_batch
    ▼
FrameBuffer SoA  →  sort (tex_id / depth)  →  runs
    │
    ├─ sprites     → ONE ubr_submit_frame (expand + VBO + draw di C)
    ├─ primitives / text / custom  → Canvas (queued non-sprite)
```

Install: `./init.sh` atau `uv sync --package plyunit --extra raylib --extra native` — lihat [ubr.md](ubr.md).


## Pilih jalur (cepat)

| Situasi | API |
| --- | --- |
| 1 sprite / actor | `SpriteRenderer` on `NodeUnit` |
| Ratusan–ribuan sprite, texture sama | `renderer.render_batch(...)` |
| N sprite, N texture (mis. `canvas.create_rects`) | `renderer.render_sprites(textures=..., positions=...)` |
| Hot path (particle / bunny-class) | `render_batch(..., pos_xy=float32_array)` → UBR |
| Shape / debug | `render_rect` / `render_circle` / plural `render_*` methods — **deprecated**, pakai `canvas.create_*` + jalur sprite |
| Shape sprite reusable | `canvas.create_rect(...)` → `Assets.store_texture` → jalur sprite |
| UI | typed `render_*` with `Layer.UI`, plus `Text.push` |
| Custom Canvas | `render_custom` / `DrawScope` helper |

Detail: [ubr.md](ubr.md), [best-practices.md](best-practices.md). Install: `plyunit[raylib,native]`.
