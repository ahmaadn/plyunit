# plyunit rendering guide

Rendering guide for games built on **plyunit**. Start here, then follow the
relevant topics.

**All engine documents:** [../index.md](../index.md)

## Read first

| Document | Contents |
| --- | --- |
| [**ubr.md**](ubr.md) | **UBR (current):** FrameBuffer SoA → sort → `ubr_submit_frame` |
| [best-practices.md](best-practices.md) | Decision tree, do/don't, performance checklist |
| [queued-submit.md](queued-submit.md) | `render_sprite`, `render_batch`, `render_sprites`, primitives, text, sorting |
| [layers-sort-cull.md](layers-sort-cull.md) | Layers, z, y-sort, frustum cull, SpatialIndex |

## Related documents (docs root)

| Document | Contents |
| --- | --- |
| [../node-rendering-guide.md](../node-rendering-guide.md) | NodeUnit + SpriteRenderer patterns |
| [../batch-render.md](../batch-render.md) | Sprite batching, native C, bunny FPS targets |
| [../frame-execution-order.md](../frame-execution-order.md) | Sync → spatial → physics → render |
| [../architecture-plan-alignment.md](../architecture-plan-alignment.md) | PLAN ↔ implementation map |

## One-slide mental model

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
    ├─ sprites     → ONE ubr_submit_frame (expand + VBO + draw in C)
    ├─ primitives / text / custom  → Canvas (queued non-sprite)
```

Install: `./init.sh` or `uv sync --package plyunit --extra raylib --extra native` — see [ubr.md](ubr.md).


## Pick a path (quick)

| Situation | API |
| --- | --- |
| 1 sprite / actor | `SpriteRenderer` on `NodeUnit` |
| Hundreds–thousands of sprites, same texture | `renderer.render_batch(...)` |
| N sprites, N textures (e.g. `canvas.create_rects`) | `renderer.render_sprites(textures=..., positions=...)` |
| Hot path (particle / bunny-class) | `render_batch(..., pos_xy=float32_array)` → UBR |
| Shapes / debug | `render_rect` / `render_circle` / plural `render_*` methods — **deprecated**, use `canvas.create_*` + sprite path |
| Reusable shape sprites | `canvas.create_rect(...)` → `Assets.store_texture` → sprite path |
| UI | typed `render_*` with `Layer.UI`, plus `Text.push` |
| Custom Canvas | `render_custom` / `DrawScope` helper |

Details: [ubr.md](ubr.md), [best-practices.md](best-practices.md). Install: `plyunit[raylib,native]`.
