# Layers, sort, and culling

Draw order and culling determine visual correctness **and** how long texture
runs stay.

## 1. Layer vs z

| | Layer | z / `z_index` |
| --- | --- | --- |
| Meaning | Coarse group (background → entities → UI) | Order within a layer |
| Enum | `plyunit.rendering.enum.Layer` | float/int at submit / SpriteRenderer |
| Batching | Different layer = different run | Different z = different sort key → run breaks |

```python
from plyunit.rendering import Layer

SpriteRenderer(texture=tex, layer=int(Layer.ENTITIES), z_index=0)
renderer.render_batch(..., layer=int(Layer.EFFECTS), z=0)
```

**Best practice:** share the same `z` for objects that do not need a unique
order (crowds, particles, grass).

## 2. Sort order

Passes and layers always form the primary boundary. Within them, the renderer
chooses between depth/y sorting and texture grouping:

- Depth-sorted or y-sorted layers/items keep depth/y order.
- Ordinary sprite layers can regroup by texture within the same state; `z` is
  not a strict painter-order guarantee on this path.
- `Layer.EFFECTS` is depth-sorted by default.
- `Renderer.enable_y_sort_layer(layer, enabled=True)` changes the global y-sort
  set for a layer.

Use a depth/y-sort layer when overlapping sprites must have a deterministic
order.

## 3. Y-sort

Enable y-sort per node / layer when you need "lower on screen draws in front".

```python
node.y_sort_enabled = True
# submission uses y_sort_origin from world Y
```

Effect: sort key = Y → texture batches only within the same Y row.
**Do not** y-sort 8k particles when unnecessary — expensive and breaks runs.

## 4. Off-camera culling

At render submit:

1. Take the view rect from `@Camera2D.get_view_rect()` (+ margin).
2. If **`@SpatialIndex`** is registered:
   `candidates = set(spatial.query_aabb(...))`
   nodes not in candidates → **skip submit**, **still recurse** into children.
3. Without SpatialIndex: AABB fallback (`get_render_bounds` or a point at the
   world position).

```python
# Opt-in in the app
pu.SpatialIndex(cell_size=64.0)
```

After transform sync, the scene calls `spatial.refresh_scene(self)` automatically.

### Bounds

- `NodeUnit.get_render_bounds()` → world **`(x, y, w, h)`**
- `SpriteRenderer.get_render_bounds()` fills this in
- Without bounds: point AABB at `transform.world.position`

### Culling best practices

| Scene | SpatialIndex | Notes |
| --- | --- | --- |
| Open world, many bounded nodes | On | cell_size ~ 2–4× entity size |
| Bunny / flat batch list | **Off** | No per-bunny nodes |
| UI only | Off / no camera view | view_rect None → no cull |

Culling does **not** replace the physics broadphase (pymunk stays separate).

## 5. SpatialIndex manual vs auto

| Mode | API |
| --- | --- |
| Auto (recommended for gameplay) | register the service → `refresh_scene` every fixed update |
| Manual | `set_bounds(key, min_x, min_y, max_x, max_y)` / `remove` / `query_aabb` |

```python
spatial = app.one("@SpatialIndex")  # or scene.one_or_none
hits = spatial.query_aabb(0, 0, 100, 100)
```

Key = `NodeUnit` identity (or any object) — consistent with `remove` during
EntityPool release.

## 6. Render state inheritance

Scene DFS:

- parent scissor ∩ child scissor
- blend/shader inherited when the child is `None`
- culled nodes skip submission but children still receive parent state

Do not set scissor/shader per entity in large crowds.

## 7. Order & cull checklist

- [ ] Layers consistent with the design (BG / entities / FX / UI)
- [ ] z defaults to 0 unless manual sorting is needed
- [ ] y-sort only on layers that need it
- [ ] SpatialIndex only for large sets of bounded nodes
- [ ] `get_render_bounds` filled for sprites that should be culled
- [ ] Bunny / flat particle lists: no SpatialIndex

## 8. See also

- [best-practices.md](best-practices.md)
- [queued-submit.md](queued-submit.md)
- [../frame-execution-order.md](../frame-execution-order.md)
- [../batch-render.md](../batch-render.md)
