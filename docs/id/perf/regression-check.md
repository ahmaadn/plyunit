# Performance regression check

How to confirm plyunit's locked bunny targets still pass after a change.

> Index: [../index.md](../index.md)

## 1. Strict bunny targets (PLAN §6)

Two profiles must stay green on the reference machine:

```bash
# 8000 sprites @ ≥60 FPS
uv run --package plyunit plyunit-bunny-benchmark \
  --bunnies 8000 --target-bunnies 8000 --target-fps 60 \
  --fps-mode capped --duration-seconds 10 \
  --report-file bunny_8k_60.txt

# 10000 sprites @ ≥30 FPS
uv run --package plyunit plyunit-bunny-benchmark \
  --bunnies 10000 --target-bunnies 10000 --target-fps 30 \
  --fps-mode capped --duration-seconds 10 \
  --report-file bunny_10k_30.txt
```

Each command exits non-zero if the average FPS falls below target.

## 2. Rules

- **SpatialIndex OFF** during bunny runs. The bunny hot path is the flat
  `render_batch` → FrameBuffer → `ubr_submit_frame`; there are no
  per-bunny bounds nodes to index. Enabling SpatialIndex here would measure
  the wrong thing and add cost. (See [pooling-and-spatial.md](../pooling-and-spatial.md).)
- Ensure `plyunit-native` is installed (`uv sync --package plyunit --extra native`).
  Without the extension, `Renderer` fails at init (no Python draw fallback).
- Run on the same machine / power profile for comparability.

## 3. Bisecting an M5 regression

The incremental SpatialIndex path is opt-in; it never runs during bunny.
If a bunny regression appears after the M5 changes:

1. Toggle `SpatialIndex(stats_enabled=True)` and compare
   `spatial.stats.last_update_ms` against a baseline (separate from bunny).
2. Confirm `TransformStore.sync()` still returns the recomputed indices and
   the per-frame allocation is negligible (`scene.frame_profile[
   "transform_dirty_count"]` should be small for a steady scene).
3. `git bisect` across the M5 commits with the two commands above as the
   pass/fail script.

## 4. Related

- [rendering/ubr.md](../rendering/ubr.md)
- [batch-render.md](../batch-render.md)
- [observability/stats.md](../observability/stats.md)
