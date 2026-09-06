# Layers, sort, and culling

Urutan gambar dan culling menentukan kebenaran visual **dan** seberapa panjang texture run.

## 1. Layer vs z

| | Layer | z / `z_index` |
| --- | --- | --- |
| Arti | Kelompok kasar (background → entities → UI) | Urutan dalam layer |
| Enum | `plyunit.rendering.enum.Layer` | float/int di submit / SpriteRenderer |
| Batch | Beda layer = beda run | Beda z = beda sort key → run pecah |

```python
from plyunit.rendering import Layer

SpriteRenderer(texture=tex, layer=int(Layer.ENTITIES), z_index=0)
renderer.render_batch(..., layer=int(Layer.EFFECTS), z=0)
```

**Best practice:** samakan `z` untuk objek yang tidak butuh urutan unik (crowd, particle, grass).

## 2. Sort order

Pass dan layer selalu membentuk batas utama. Di dalamnya, renderer memilih
antara depth/y sorting dan texture grouping:

- Layer depth-sorted atau item y-sorted mempertahankan depth/y order.
- Layer sprite biasa dapat regroup berdasarkan texture di dalam state yang
  sama; `z` bukan painter-order guarantee yang ketat pada jalur ini.
- `Layer.EFFECTS` depth-sorted secara default.
- `Renderer.enable_y_sort_layer(layer, enabled=True)` mengubah set y-sort
  global untuk layer.

Gunakan layer depth/y-sort saat sprite overlap harus memiliki urutan pasti.

## 3. Y-sort

Aktifkan y-sort per node / layer bila butuh “lebih bawah di layar digambar di depan”.

```python
node.y_sort_enabled = True
# submit memakai y_sort_origin dari world Y
```

Efek: sort key = Y → batch texture hanya dalam baris Y yang sama.
**Jangan** y-sort 8k particle jika tidak perlu — mahal dan memecah run.

## 4. Culling di luar kamera

Saat render submit:

1. Ambil view rect dari `@Camera2D.get_view_rect()` (+ margin).
2. Jika **`@SpatialIndex`** terdaftar:
   `candidates = set(spatial.query_aabb(...))`
   node tidak di candidates → **skip submit**, **tetap recurse** children.
3. Tanpa SpatialIndex: AABB fallback (`get_render_bounds` atau point di world pos).

```python
# Opt-in di app
pu.SpatialIndex(cell_size=64.0)
```

Setelah transform sync, scene memanggil `spatial.refresh_scene(self)` otomatis.

### Bounds

- `NodeUnit.get_render_bounds()` → world **`(x, y, w, h)`**
- `SpriteRenderer.get_render_bounds()` mengisi ini
- Tanpa bounds: point AABB di `transform.world.position`

### Best practice cull

| Scene | SpatialIndex | Catatan |
| --- | --- | --- |
| Open world, banyak node bounded | On | cell_size ~ 2–4× entity |
| Bunny / flat batch list | **Off** | Tidak ada per-bunny node |
| UI only | Off / no camera view | view_rect None → no cull |

Cull **tidak** menggantikan physics broadphase (pymunk tetap terpisah).

## 5. SpatialIndex manual vs auto

| Mode | API |
| --- | --- |
| Auto (disarankan gameplay) | register service → `refresh_scene` tiap fixed update |
| Manual | `set_bounds(key, min_x, min_y, max_x, max_y)` / `remove` / `query_aabb` |

```python
spatial = app.one("@SpatialIndex")  # or scene.one_or_none
hits = spatial.query_aabb(0, 0, 100, 100)
```

Key = identity `NodeUnit` (atau objek apa pun) — konsisten dengan `remove` di EntityPool release.

## 6. Render state inheritance

DFS scene:

- parent scissor ∩ child scissor
- blend/shader inherit jika child `None`
- culled node skip submit tapi children tetap dapat state parent

Jangan set scissor/shader per-entity di crowd besar.

## 7. Checklist urutan & cull

- [ ] Layer konsisten dengan desain (BG / entities / FX / UI)
- [ ] z default 0 kecuali butuh sorting manual
- [ ] y-sort hanya layer yang butuh
- [ ] SpatialIndex hanya jika N node bounded besar
- [ ] `get_render_bounds` diisi untuk sprite yang ingin di-cull
- [ ] Bunny / particle flat list: tidak pakai SpatialIndex

## 8. Lihat juga

- [best-practices.md](best-practices.md)
- [queued-submit.md](queued-submit.md)
- [../frame-execution-order.md](../frame-execution-order.md)
- [../batch-render.md](../batch-render.md)
