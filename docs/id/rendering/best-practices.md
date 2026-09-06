# Rendering best practices

Panduan praktis untuk game plyunit: pilih jalur render yang benar, jaga batch hidup, dan hindari pola mahal.

## 1. Decision tree

```
Perlu gambar apa?
│
├─ Satu sprite terikat actor/node
│     → NodeUnit + SpriteRenderer
│
├─ Banyak posisi, material sama (texture/tint/scale/rot)
│     → Satu system/node + render_batch
│     → Hot path: simpan pos sebagai float32 (n,2), pass pos_xy=
│
├─ Shape / line / circle
│     → canvas.create_rect / create_circle / ... (bake sekali)
│     → simpan via Assets.store_texture, render via render_sprite / render_sprites
│     → (immediate render_rect / render_circle / render_line deprecated)
│
├─ UI (screen space)
│     → typed render_* with Layer.UI / Text.push
│
└─ Benar-benar custom (shader procedural, multi-draw Canvas)
      → draw(canvas) + enable_custom_draw()  [terakhir]
```

## 2. Do

- **Submit di `render_submit`**, bukan di `update` (queue diisi per frame render).
- **Samakan material** dalam satu batch: texture, source, layer, z, tint, scale, rotation, origin, blend, shader, scissor.
- **Pakai `z` / `z_index` sama** untuk objek yang tidak butuh urutan unik (z unik memecah run).
- **Transform lewat setter**: `set_position` / `set_rotation` / `set_scale` agar SoA dirty tracking benar.
- **Cull opt-in**: `SpatialIndex` hanya jika perlu query gameplay / cull besar; **matikan** di bunny-style stress (flat list).
- **Hot path data-oriented**: array contiguous `numpy.float32` untuk posisi dan `pos_xy=` agar bulk append tanpa loop Python; data tetap disalin ke FrameBuffer.

## 3. Don't

| Anti-pattern | Kenapa mahal |
| --- | --- |
| Override `draw()` untuk sprite biasa | Melewati typed queue / batch |
| 8k `NodeUnit` + `SpriteRenderer` untuk particle | Overhead tree + component |
| `z_index` unik per particle | Sort key beda → batch pecah |
| Ganti texture/tint tiap submit dalam loop | State change → run pendek |
| `dest=` pada `render_sprite` jika `pos+scale` cukup | Fallback path lebih umum |
| Assign `transform.local.position = ...` di runtime | Dirty/SoA bisa meleset |
| Panggil `rl_*` / raw GL di luar `begin_drawing` | Crash / undefined (butuh GL context) |
| Load raylib kedua di native | Double context — **dilarang**; rlgl dari proses pyray |

## 4. Pola yang disarankan

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
        # list of (x, y) or Vector2 — OK untuk ratusan
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

### 4.3 Hot path (ribuan, 60 FPS)

Sim + draw share buffer float32; biarkan engine pack + C:

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

Detail: [ubr.md](ubr.md).

## 5. Entity density cheat sheet

Pilih pola sesuai jumlah objek — salah pilih adalah penyebab paling umum FPS
drop di Python.

| Pola | Direkomendasikan N | Kenapa |
| --- | --- | --- |
| `NodeUnit` + `SpriteRenderer` (actor) | < 500 | Tree + component overhead per node |
| `EntityPool` (bullets / enemies recycled) | 100s–low 1000s | Reuse hindari attach/destroy churn; `SpatialIndex` didukung |
| `render_batch` (particles / FX) | 1000s–10k+ | Satu call Python + native run; nol cost per-item NodeUnit |
| Bunny-class (8k+ sprite homogen) | 8000–10000 | Flat SoA + UBR; **jangan 8k NodeUnit** |

> **Don't 8k nodes.** Bunny = flat `render_batch` + UBR, **bukan**
> 8000 `NodeUnit` + `SpriteRenderer`. Satu NodeUnit per particle mengalahkan
> tujuan batch dan akan jauh di bawah target. Lihat
> [perf/regression-check.md](../perf/regression-check.md).

Jika butuh query area untuk ribuan entitas, aktifkan `SpatialIndex` (incremental
sejak M5 — hanya node yang bergerak di-upsert, bukan full rebuild).

### Catatan optimasi hot path (M5+)

Biaya per node per substep pernah mencapai ~19µs (400 node ≈ 7.7ms/substep di
mesin referensi Intel HD 520). Tiga optimasi menurunkannya ke ~8µs
(-59%):

1. **`TransformStore.sync`** — field int/bool (parent/child link, dirty,
   fresh) kini Python list; field float di-snapshot via `tolist()` sekali
   per sync lalu ditulis balik vectorized. Loop utama bebas numpy scalar
   boxing.
2. **`SpriteRenderer`** — service `Assets` di-cache per komponen via
   `weakref` (bukan query registry `one("Assets")` per sprite per frame);
   dict lookup per frame tetap dijaga agar remap texture atlas tetap
   transparan.
3. **`NodeUnit`** — flag `_any_updating_components` skip loop update untuk
   node render-only; `world_transform_lerp` cache `Window` via weakref;
   `lerp_world(1.0)` short-circuit (fast path render selalu alpha 1.0).

Dengan 400 `NodeUnit` aktif: fixed-step ~3–4ms/substep, render submit
~13ms/frame, flush UBR <1ms. Pedoman tetap: **>500 actor → pindah ke
`EntityPool`/`render_batch`** — optimasi di atas menurunkan konstanta,
bukan mengubah kompleksitas O(node).

## 6. Checklist sebelum ship

- [ ] Sprite actor → `SpriteRenderer`, bukan `draw()`
- [ ] N≫1 material homogen → `render_batch` (bukan N node)
- [ ] Hot path → `pos_xy` float32 + UBR (`plyunit-native`)
- [ ] Layer/z/state disamakan di mana urutan visual tidak butuh unik
- [ ] Tidak ada second raylib / manual `rl_*` di gameplay code
- [ ] Overlay/debug off saat mengukur FPS gate
- [ ] Report bench di `benchmarks/reports/*_<timestamp>.txt`

## 7. Lanjut baca

- [queued-submit.md](queued-submit.md) — API queue lengkap
- [ubr.md](ubr.md) — FrameBuffer + `ubr_submit_frame`
- [layers-sort-cull.md](layers-sort-cull.md) — urutan & cull
- [../node-rendering-guide.md](../node-rendering-guide.md) — NodeUnit mendalam  
