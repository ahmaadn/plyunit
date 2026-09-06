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

Implement `reset()` on pooled units/components to clear state for reuse.

## 2. SpatialIndex

Optional service (spatial hash) for area queries and off-screen culling.

```python
pu.SpatialIndex(cell_size=64.0)
# unique name: SpatialIndex → query "@SpatialIndex"
```

### Auto refresh (incremental, M5)

After transforms are synced each fixed update:

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

Bounds: `get_render_bounds()` **(x, y, w, h)** or a point at the world position.

Opt-in counters: `SpatialIndex(stats_enabled=True)` → `spatial.stats.last_dirty_count`
/ `last_full_count` / `last_update_ms`.

### Manual API

```python
spatial.set_bounds(key, min_x, min_y, max_x, max_y)
spatial.remove(key)
hits = spatial.query_aabb(min_x, min_y, max_x, max_y)
spatial.clear()
```

### Culling

When the service is registered + camera view:

- `candidates = query_aabb(view as min/max)`
- Nodes not in the set → skip **submit**, still **recurse** into children

Without the service: AABB fallback.
**Bunny / flat batch:** leave SpatialIndex off.

Details: [rendering/layers-sort-cull.md](rendering/layers-sort-cull.md).

## 3. Gotchas

| Issue | Fix |
| --- | --- |
| Stale handle | Always check `is_alive` / `get` |
| Spatial not removed | The service must be resolvable **before** detach (the pool already does this) |
| Weak unique registry tests | Keep a strong ref to the service in tests |
| cell_size | ~2–4× the average entity size |

## 4. See also

- [engine-core.md](engine-core.md)
- [frame-execution-order.md](frame-execution-order.md)
