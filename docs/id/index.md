# plyunit documentation

Index panduan engine `plyunit` — mulai dari sini.

## Mulai di sini

| Dokumen | Isi |
| --- | --- |
| [getting-started.md](getting-started.md) | Install, bootstrap, scene pertama, struktur proyek |
| [engine-core.md](engine-core.md) | App, Unit/NodeUnit/SceneUnit, services, SceneManager, Window |
| [frame-execution-order.md](frame-execution-order.md) | Urutan fixed step + render per frame |
| [migration.md](migration.md) | **Breaking changes** — migrasi App flow (fixed_update/update) |
| [naming-convention.md](naming-convention.md) | Aturan penamaan API (hooks, mutators, queries) |
| [configuration-schemas.md](configuration-schemas.md) | Contoh JSON App, assets, spritesheet, animation, map, tileset, audio |

## Sistem gameplay

| Dokumen | Isi |
| --- | --- |
| [physics.md](physics.md) | Physics, body/area/static, filter, debug draw |
| [input-and-events.md](input-and-events.md) | Keyboard, Mouse, EventBus dual drain |
| [imgui.md](imgui.md) | ImGui debug/UI (immediate, post-render) |
| [audio.md](audio.md) | Audio, SFX/music, spatial, bank, AudioSource |
| [assets-tilemap-particles.md](assets-tilemap-particles.md) | Assets, TileMapNode, particles (ringkas) |
| [tilemap-system.md](tilemap-system.md) | **Arsitektur tilemap lengkap** (chunk, bake, physics, Y-sort) |
| [pooling-and-spatial.md](pooling-and-spatial.md) | EntityPool, SpatialIndex |
| [gameplay-utilities.md](gameplay-utilities.md) | Timer, TweenAnimation, animation.finished |

## Rendering

| Dokumen | Isi |
| --- | --- |
| [rendering/index.md](rendering/index.md) | **Index rendering** (batch, native, cull) |
| [immediate-rendering.md](immediate-rendering.md) | DrawScope and direct Canvas drawing |
| [node-rendering-guide.md](node-rendering-guide.md) | NodeUnit + SpriteRenderer patterns |
| [batch-render.md](batch-render.md) | Batch sprite, native C, target FPS bunny |

## Referensi

| Dokumen | Isi |
| --- | --- |
| [examples-and-cli.md](examples-and-cli.md) | Daftar CLI examples + kapan dipakai |
| [architecture-plan-alignment.md](architecture-plan-alignment.md) | PLAN ↔ implementasi |
| [cheatsheet.md](cheatsheet.md) | Satu halaman: loop, query, jangan lakukan |
| [configuration-schemas.md](configuration-schemas.md) | Referensi field/default semua format konfigurasi |

## Mental model (1 slide)

```
init(App, AppConfig)
  → window, Canvas, Renderer, SceneManager, Assets
  → optional Physics / ImGui / Audio

app.run()
  on_load  → push scene, map input, services
  loop:
    Window clock + fixed updates
      begin_update → user polls Input/Mouse/Touch → EventBus EARLY
      App.fixed_update (user) → SceneManager.update → TransformStore.sync → SpatialIndex?
      on_after_update
      on_end_update
      on_fixed_update → Physics.step
      EventBus LATE
    App.update(dt) (user hook — the render pipeline)
      camera.update → renderer.reset_frame → begin_drawing
      SceneManager.render → flush_all(camera)
      optional render_custom / controlled DrawScope calls
      ImGui.frame(dt) → end_drawing
```

## Install

plyunit **belum dipublikasikan ke PyPI** — pasang dari repositori:

```bash
git clone https://github.com/ahmaadn/plyunit.git
cd plyunit
./init.sh     # uv sync + build native + verify
```

Requirements: [uv](https://docs.astral.sh/uv/), Python ≥ 3.13, dan compiler
C (MSVC Build Tools atau MinGW-w64 `gcc` di `PATH`) untuk ekstensi native
sprite-batching.

Extra per-package (`uv sync --package plyunit` hanya mensinkronkan package tersebut):

```bash
uv sync --package plyunit --extra all
#   raylib   window/render (umumnya selalu untuk game)
#   physics  pymunk
#   imgui    imgui-bundle + OpenGL
#   native   C bulk sprite path
```

Scaffold proyek baru: `./new_project.sh my_project` → jalankan dengan
`uv run python projects/my_project/main.py`; `--isolated` menyematkan
salinan engine plyunit di `scripts/plyunit/` (lihat
[getting-started.md](getting-started.md)).
