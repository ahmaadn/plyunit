# Stats & instrumentation

Opt-in counters and timings for measuring plyunit hot paths. **All hooks are
off by default** — flip a flag to populate them, then read the snapshot.
Leave them off in shipping builds.

> Index: [index.md](../index.md)

## 1. Where the knobs live

| Stat | Owner | Units | Flag |
| --- | --- | --- | --- |
| `sprite_count`, `sprite_batch_count` | `Renderer.frame_profile` | items | `renderer.profile_enabled = True` |
| `primitive_item_count`, `custom_item_count` | `Renderer.frame_profile` | items | `renderer.profile_enabled = True` |
| `render_item_count`, `draw_call_count` | `Renderer.frame_profile` | count | `renderer.profile_enabled = True` |
| `render_total_ms`, `render_sort_ms`, `render_flush_ms` | `Renderer.frame_profile` | ms | `renderer.profile_enabled = True` |
| `update_nodes_ms`, `update_sync_ms`, `render_submit_ms` | `SceneUnit.frame_profile` | ms | `scene.profile_enabled = True` |
| `transform_dirty_count` | `SceneUnit.frame_profile` | count | `scene.profile_enabled = True` |
| `last_dirty_count`, `last_full_count`, `last_update_ms` | `SpatialIndex.stats` | count / ms | `SpatialIndex(stats_enabled=True)` |
| `fixed_step_count`, `_last_fixed_steps` | `App` | count | always (cheap int) |

## 2. Renderer profile

```python
renderer.profile_enabled = True
# ... run a frame ...
fp = renderer.last_frame_profile
print(fp["sprite_count"], fp["draw_call_count"], fp["render_total_ms"])
```

When `profile_enabled=False`, `frame_profile` stays empty and every counter
increment is skipped — zero cost.

## 3. SpatialIndex stats

```python
spatial = pu.SpatialIndex(cell_size=64.0, stats_enabled=True)
spatial = pu.SpatialIndex(cell_size=64.0, stats_enabled=True)
# ... run frames; spatial.mark_dirty / flush_dirty populate counters ...
print(spatial.stats.last_dirty_count)   # nodes upserted this flush
print(spatial.stats.last_full_count)    # nodes touched by last refresh_scene
```

Only use this for measurement (debug overlay / benchmark). It does not gate
the hot path, but the `SpatialIndexStats` object is extra state — leave
`stats_enabled=False` in release.

## 4. SceneUnit profile

```python
scene.profile_enabled = True
# ... run a frame ...
print(scene.last_frame_profile)
# {'update_nodes_ms': ..., 'update_sync_ms': ..., 'transform_dirty_count': N, ...}
```

`transform_dirty_count` is sampled **before** `sync()` runs, so it reflects how
many nodes were dirty entering the step — useful to confirm the incremental
SpatialIndex path actually moved few nodes.

## 5. ImGui overlay (example only)

plyunit ships no built-in overlay; an example app can read these dicts inside
an ImGui `add_draw` callback. Keep the overlay off when profiling the bunny
benchmark (it perturbs measurements).
