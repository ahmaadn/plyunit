# plyunit rendering guide

Panduan rendering untuk game yang dibangun di atas **plyunit**. Mulai dari sini, lalu ikuti topik yang relevan.

**Semua dokumen engine:** [../index.md](../index.md)

## Baca dulu

| Dokumen | Isi |
| --- | --- |
| [**ubr.md**](ubr.md) | **UBR (current):** FrameBuffer SoA → sort → `ubr_submit_frame` |
| [best-practices.md](best-practices.md) | Decision tree, do/don't, checklist performa |
| [queued-submit.md](queued-submit.md) | `render_sprite`, `render_batch`, `render_sprites`, baked shapes, dynamic Canvas geometry, text, sorting |
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
Game logic (App.fixed_update / node.update)
    │
    ▼
TransformStore.sync()  (+ optional incremental SpatialIndex updates)
    │
    ▼
Scene DFS NodeUnit/component render_submit(renderer, context)
    │  SpriteRenderer / render_sprite / render_batch / render_shaped_text
    ▼
FrameBuffer SoA  →  sort (tex_id / depth)  →  runs
    │
    ├─ sprites / shaped glyphs → ubr_submit_frame (expand + VBO + draw in C)
    └─ render_custom          → queued Canvas drawing (not sprite-batched)
```

Install: `./init.sh` atau `uv sync --package plyunit --extra raylib --extra native` — lihat [ubr.md](ubr.md).


## Pilih jalur (cepat)

| Situasi | API |
| --- | --- |
| 1 sprite / actor | `SpriteRenderer` on `NodeUnit` |
| Ratusan–ribuan sprite, texture sama | `renderer.render_batch(...)` |
| N sprite, N texture (mis. `canvas.create_rects`) | `renderer.render_sprites(textures=..., positions=...)` |
| Hot path (particle / bunny-class) | `render_batch(..., pos_xy=float32_array)` → UBR |
| Dynamic geometry / debug | `render_custom(draw_func=lambda canvas: canvas.draw_*())` |
| Reusable shape sprites | Cache `canvas.create_*` textures in `Assets`, then `render_sprite` / `render_sprites` |
| UI | Sprite submissions and `Text.push` with `Layer.UI` |
| Custom Canvas | `render_custom` / `DrawScope` helper |

`SceneUnit` only dispatches its tree; it has no `render_submit` hook.
`App.update(dt)` owns reset, drawing, scene submission, and flush each frame.
Use `ICanvas2D` and resource handles from `plyunit.backends.ports` in neutral
code. `Canvas2D()` is a factory returning the module-backed canvas, not a class.

The former rectangle/circle/line/triangle submit methods and their plural
variants are removed with no compatibility path. Bake reusable shapes once
in load hooks after bootstrap; use queued Canvas callbacks for changing
geometry. Render-target, font-atlas, and streaming attachments are borrowed,
so never transfer them into `Assets` or free them separately.

Details: [ubr.md](ubr.md), [best-practices.md](best-practices.md). Install: `plyunit[raylib,native]`.
