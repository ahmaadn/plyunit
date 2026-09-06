# plyunit documentation

Index of `plyunit` engine guides — start here.

## Start here

| Document | Contents |
| --- | --- |
| [getting-started.md](getting-started.md) | Install, bootstrap, first scene, project structure |
| [engine-core.md](engine-core.md) | App, Unit/NodeUnit/SceneUnit, services, SceneManager, Window |
| [frame-execution-order.md](frame-execution-order.md) | Per-frame fixed-step + render order |
| [migration.md](migration.md) | **Breaking changes** — App flow migration (fixed_update/update) |
| [naming-convention.md](naming-convention.md) | API naming rules (hooks, mutators, queries) |
| [configuration-schemas.md](configuration-schemas.md) | JSON examples for App, assets, spritesheet, animation, map, tileset, audio |

## Gameplay systems

| Document | Contents |
| --- | --- |
| [physics.md](physics.md) | Physics, body/area/static, filters, debug draw |
| [input-and-events.md](input-and-events.md) | Keyboard, Mouse, EventBus dual drain |
| [imgui.md](imgui.md) | ImGui debug/UI (immediate, post-render) |
| [audio.md](audio.md) | Audio, SFX/music, spatial, bank, AudioSource |
| [assets-tilemap-particles.md](assets-tilemap-particles.md) | Assets, TileMapNode, particles (concise) |
| [tilemap-system.md](tilemap-system.md) | **Complete tilemap architecture** (chunks, baking, physics, Y-sort) |
| [pooling-and-spatial.md](pooling-and-spatial.md) | EntityPool, SpatialIndex |
| [gameplay-utilities.md](gameplay-utilities.md) | Timer, TweenAnimation, animation.finished |

## Rendering

| Document | Contents |
| --- | --- |
| [rendering/index.md](rendering/index.md) | **Rendering index** (batch, native, cull) |
| [immediate-rendering.md](immediate-rendering.md) | DrawScope and direct Canvas drawing |
| [node-rendering-guide.md](node-rendering-guide.md) | NodeUnit + SpriteRenderer patterns |
| [batch-render.md](batch-render.md) | Sprite batching, native C, bunny FPS targets |

## Reference

| Document | Contents |
| --- | --- |
| [examples-and-cli.md](examples-and-cli.md) | CLI examples list + when to use each |
| [architecture-plan-alignment.md](architecture-plan-alignment.md) | PLAN ↔ implementation |
| [cheatsheet.md](cheatsheet.md) | One page: loop, queries, don'ts |
| [configuration-schemas.md](configuration-schemas.md) | Field/default reference for all configuration formats |

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

plyunit is **not published to PyPI** — install from the repository:

```bash
git clone https://github.com/ahmaadn/plyunit.git
cd plyunit
./init.sh     # uv sync + native build + verify
```

Requirements: [uv](https://docs.astral.sh/uv/), Python ≥ 3.13, and a C
compiler (MSVC Build Tools or MinGW-w64 `gcc` on `PATH`) for the native
sprite-batching extension.

Per-package extras (`uv sync --package plyunit` syncs only that package):

```bash
uv sync --package plyunit --extra all
#   raylib   window/render (typically always for games)
#   physics  pymunk
#   imgui    imgui-bundle + OpenGL
#   native   C bulk sprite path
```

New project scaffold: `./new_project.sh my_project` → run with
`uv run python projects/my_project/main.py`; `--isolated` embeds a plyunit
engine copy at `scripts/plyunit/` (see
[getting-started.md](getting-started.md)).
