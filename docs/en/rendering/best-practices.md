# Rendering best practices

A practical guide for plyunit games: pick the right render path, keep batches
alive, and avoid expensive patterns.

## 1. Decision tree

```
What do you need to draw?
│
├─ One sprite bound to an actor/node
│     → NodeUnit + SpriteRenderer
│
├─ Many positions, same material (texture/tint/scale/rot)
│     → One system/node + render_batch
│     → Hot path: store positions as float32 (n,2), pass pos_xy=
│
├─ Shapes / lines / circles
│     → canvas.create_rect / create_circle / ... (bake once)
│     → store via Assets.store_texture, render via render_sprite / render_sprites
│     → (immediate render_rect / render_circle / render_line are deprecated)
│
├─ UI (screen space)
│     → typed render_* with Layer.UI / Text.push
│
└─ Truly custom (procedural shaders, multi-draw Canvas)
      → draw(canvas) + enable_custom_draw()  [last resort]
```

## 2. Do

- **Submit in `render_submit`**, not in `update` (the queue is filled per render frame).
- **Share material** within a batch: texture, source, layer, z, tint, scale, rotation, origin, blend, shader, scissor.
- **Use the same `z` / `z_index`** for objects that do not need a unique order (unique z breaks runs).
- **Transforms via setters**: `set_position` / `set_rotation` / `set_scale` so SoA dirty tracking stays correct.
- **Opt-in culling**: `SpatialIndex` only for large gameplay queries / culling; **turn it off** for bunny-style stress (flat lists).
- **Data-oriented hot path**: contiguous `numpy.float32` arrays for positions and `pos_xy=` for a bulk append without a Python loop; data is still copied into the FrameBuffer.

## 3. Don't

| Anti-pattern | Why it is expensive |
| --- | --- |
| Overriding `draw()` for an ordinary sprite | Bypasses the typed queue / batch |
| 8k `NodeUnit` + `SpriteRenderer` for particles | Tree + component overhead |
| Unique `z_index` per particle | Different sort keys → batch breaks |
| Changing texture/tint every submit in a loop | State changes → short runs |
| `dest=` on `render_sprite` when `pos+scale` suffices | More common fallback path |
| Assigning `transform.local.position = ...` at runtime | Dirty/SoA tracking can drift |
| Calling `rl_*` / raw GL outside `begin_drawing` | Crash / undefined (needs a GL context) |
| Loading a second raylib inside native | Double context — **forbidden**; rlgl comes from the pyray process |

## 4. Recommended patterns

### 4.1 Actor (1 sprite)

```python
import plyunit as pu
from plyunit.core.components.builtin import SpriteRenderer


class Player(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="Player")
        self.transform.set_position(100.0, 120.0)
        self.add_component(
            SpriteRenderer(
                texture=texture,
                layer=int(pu.Layer.PLAYER),
                z_index=0,
                scale=1.0,
            )
        )

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        self.transform.set_position(x + 80.0 * dt, y)
```

### 4.2 Crowd / bullets (batch queue)

```python
class BulletField(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="BulletField")
        self.texture = texture
        # list of (x, y) or Vector2 — OK for hundreds
        self.positions: list[tuple[float, float]] = []

    def render_submit(self, renderer, context=None) -> None:
        if not self.positions:
            return
        renderer.render_batch(
            texture=self.texture,
            positions=self.positions,
            layer=int(pu.Layer.EFFECTS),
            z=0,
            scale=1.0,
            tint=(255, 255, 255, 255),
        )
```

### 4.3 Hot path (thousands, 60 FPS)

Sim + draw share a float32 buffer; let the engine pack + C:

```python
import numpy as np


class BunnyLikeField(pu.NodeUnit):
    def __init__(self, texture, n: int = 8000) -> None:
        super().__init__(name="HotField")
        self.texture = texture
        self.pos_xy = np.zeros((n, 2), dtype=np.float32)
        self.vel_xy = np.zeros((n, 2), dtype=np.float32)

    def update(self, dt: float) -> None:
        self.pos_xy += self.vel_xy  # vectorized sim
        # bounce / wrap ...

    def render_submit(self, renderer, context=None) -> None:
        renderer.render_batch(
            texture=self.texture,
            positions=self.pos_xy,   # optional if pos_xy set
            pos_xy=self.pos_xy,      # vectorized copy → FrameBuffer → UBR
            layer=int(pu.Layer.ENTITIES),
            z=0,
            tint=(255, 255, 255, 255),
        )
```

Details: [ubr.md](ubr.md).

## 5. Entity density cheat sheet

Pick a pattern based on object count — the wrong pick is the most common cause
of FPS drops in Python.

| Pattern | Recommended N | Why |
| --- | --- | --- |
| `NodeUnit` + `SpriteRenderer` (actor) | < 500 | Per-node tree + component overhead |
| `EntityPool` (recycled bullets / enemies) | 100s–low 1000s | Reuse avoids attach/destroy churn; `SpatialIndex` supported |
| `render_batch` (particles / FX) | 1000s–10k+ | One Python call + native runs; zero per-item NodeUnit cost |
| Bunny-class (8k+ homogeneous sprites) | 8000–10000 | Flat SoA + UBR; **not 8k NodeUnits** |

> **Don't do 8k nodes.** Bunny = flat `render_batch` + UBR, **not** 8000
> `NodeUnit` + `SpriteRenderer`. One NodeUnit per particle defeats the purpose
> of batching and will land far below target. See
> [perf/regression-check.md](../perf/regression-check.md).

If you need area queries over thousands of entities, enable `SpatialIndex`
(incremental since M5 — only moving nodes are upserted, no full rebuild).

### Hot path optimization notes (M5+)

Per-node per-substep cost once reached ~19µs (400 nodes ≈ 7.7ms/substep on the
Intel HD 520 reference machine). Three optimizations brought it down to ~8µs
(-59%):

1. **`TransformStore.sync`** — int/bool fields (parent/child links, dirty,
   fresh) are now Python lists; float fields are snapshotted via `tolist()`
   once per sync and written back vectorized. The main loop is free of numpy
   scalar boxing.
2. **`SpriteRenderer`** — the `Assets` service is cached per component via
   `weakref` (instead of a `one("Assets")` registry query per sprite per
   frame); the per-frame dict lookup is kept so texture atlas remapping stays
   transparent.
3. **`NodeUnit`** — the `_any_updating_components` flag skips the update loop
   for render-only nodes; `world_transform_lerp` caches `Window` via weakref;
   `lerp_world(1.0)` short-circuits (the render fast path always uses alpha
   1.0).

With 400 active `NodeUnit`s: fixed-step ~3–4ms/substep, render submit
~13ms/frame, UBR flush <1ms. The rule of thumb stays: **>500 actors → move to
`EntityPool`/`render_batch`** — the optimizations above lower the constant,
not the O(node) complexity.

## 6. Pre-ship checklist

- [ ] Actor sprites → `SpriteRenderer`, not `draw()`
- [ ] N≫1 homogeneous material → `render_batch` (not N nodes)
- [ ] Hot path → `pos_xy` float32 + UBR (`plyunit-native`)
- [ ] Layer/z/state shared where visual order does not need to be unique
- [ ] No second raylib / manual `rl_*` in gameplay code
- [ ] Overlay/debug off when measuring the FPS gate
- [ ] Bench report saved in `benchmarks/reports/*_<timestamp>.txt`

## 7. Further reading

- [queued-submit.md](queued-submit.md) — full queue API
- [ubr.md](ubr.md) — FrameBuffer + `ubr_submit_frame`
- [layers-sort-cull.md](layers-sort-cull.md) — ordering & culling
- [../node-rendering-guide.md](../node-rendering-guide.md) — NodeUnit in depth  
