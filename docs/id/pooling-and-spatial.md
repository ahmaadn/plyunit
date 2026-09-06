# EntityPool and SpatialIndex

## 1. EntityPool

Generation-checked reuse of `NodeUnit`s.

```python
from plyunit import EntityPool, EntityHandle

pool = EntityPool(factory=lambda: EnemyNode(), capacity=64)
handle = pool.acquire()
node = pool.get(handle)
scene.root.attach(node)

pool.release(handle)  # detach, spatial remove, reset unit+components, bump gen
assert not pool.is_alive(handle)
assert pool.get(handle) is None
```

### Release contract (order)

1. Generation / alive check (stale = no-op)
2. Resolve `@SpatialIndex` (before detach)
3. Detach from scene tree
4. `SpatialIndex.remove(entity)`
5. `entity.reset()` if present
6. Each component `reset()` if present
7. Free slot + bump generation

Implement `reset()` pada pooled unit/components untuk clear state reuse.

## 2. SpatialIndex

Service opsional (spatial hash) untuk query area dan culling di luar layar.

```python
pu.SpatialIndex(cell_size=64.0)
# unique name: SpatialIndex → query "@SpatialIndex"
```

### Auto refresh (incremental, M5)

Setelah transform di-sync tiap fixed update:

1. **Bootstrap** (first encounter): `spatial.refresh_scene(scene)` — full rebuild
   so the scene root + pre-existing nodes enter the index.
2. **Default path**: `spatial.mark_dirty_many(recomputed) + flush_dirty()` —
   only nodes whose world transform changed this step are upserted.
3. **Physics movers**: `Physics._post_step_sync` marks dynamic bodies
   dirty after `apply_physics_state` (which bypasses transform dirty).
4. **Full rebuild** remains available for debug / teleport-all:

```python
spatial.refresh_scene(scene)  # clear + rebuild all in-scene nodes
```

Bounds: `get_render_bounds()` **(x, y, w, h)** atau point di world position.

Opt-in counters: `SpatialIndex(stats_enabled=True)` → `spatial.stats.last_dirty_count`
/ `last_full_count` / `last_update_ms`.

### Manual API

```python
spatial.set_bounds(key, min_x, min_y, max_x, max_y)
spatial.remove(key)
hits = spatial.query_aabb(min_x, min_y, max_x, max_y)
spatial.clear()
```

### Cull

Jika service terdaftar + camera view:

- `candidates = query_aabb(view as min/max)`
- Node tidak di set → skip **submit**, tetap **recurse** children

Tanpa service: AABB fallback.
**Bunny / flat batch:** biarkan SpatialIndex off.

Detail: [rendering/layers-sort-cull.md](rendering/layers-sort-cull.md).

## 3. Gotchas

| Issue | Fix |
| --- | --- |
| Stale handle | Selalu cek `is_alive` / `get` |
| Spatial not removed | Service harus resolvable **sebelum** detach (pool sudah handle) |
| Weak unique registry tests | Simpan strong ref ke service di test |
| cell_size | ~2–4× ukuran entity rata-rata |

## 4. Lihat juga

- [engine-core.md](engine-core.md)
- [frame-execution-order.md](frame-execution-order.md)
