# plyunit

Lightweight 2D game engine units for Python (raylib / pymunk integrations).

## Development

```bash
uv sync --all-packages
uv sync --package plyunit
uv run --package plyunit pytest
```

Optional extras: `raylib`, `physics`, `imgui`, `native`, `all`.

## Examples & benchmarks (dev-only)

At monorepo root (`examples/`, `benchmarks/`) — not in the published wheel.

```bash
uv run plyunit-example --list
uv run plyunit-example --shapes
uv run python benchmarks/bunny_benchmark.py
```

See [examples-and-cli.md](../../docs/id/examples-and-cli.md).

## Documentation

Docs live at the monorepo root: [`docs/id/`](../../docs/id/) (Bahasa Indonesia)
and [`docs/en/`](../../docs/en/) (English). Serve them with MkDocs:

```bash
uv run --group docs mkdocs serve
```

**Start here:** [docs/id/index.md](../../docs/id/index.md)

| Area | Link |
| --- | --- |
| Getting started | [docs/id/getting-started.md](../../docs/id/getting-started.md) |
| Engine core | [docs/id/engine-core.md](../../docs/id/engine-core.md) |
| Frame order | [docs/id/frame-execution-order.md](../../docs/id/frame-execution-order.md) |
| Physics | [docs/id/physics.md](../../docs/id/physics.md) |
| Input / EventBus | [docs/id/input-and-events.md](../../docs/id/input-and-events.md) |
| ImGui | [docs/id/imgui.md](../../docs/id/imgui.md) |
| Audio | [docs/id/audio.md](../../docs/id/audio.md) |
| DrawScope / custom render | [docs/id/immediate-rendering.md](../../docs/id/immediate-rendering.md) |
| Rendering best practices | [docs/id/rendering/index.md](../../docs/id/rendering/index.md) |
| Assets / tilemap / particles | [docs/id/assets-tilemap-particles.md](../../docs/id/assets-tilemap-particles.md) |
| Configuration schemas | [docs/id/configuration-schemas.md](../../docs/id/configuration-schemas.md) |
| Naming rules | [docs/id/naming-convention.md](../../docs/id/naming-convention.md) |
| Examples CLI | [docs/id/examples-and-cli.md](../../docs/id/examples-and-cli.md) |
| Cheatsheet | [docs/id/cheatsheet.md](../../docs/id/cheatsheet.md) |

## Performance (bunny)

- 8000 sprites @ ≥60 FPS (strict)
- 10000 sprites @ ≥30 FPS (strict)

Native bulk: package **`plyunit-native`** (`plyunit[native]`).
Reports: `benchmarks/reports/*_<timestamp>.txt`.

### Platform support

| Platform | plyunit (Python) | plyunit-native (C batch) |
| --- | --- | --- |
| Windows x64, Python 3.13 | CI green | CI green (MinGW gcc) |
| Linux x64, Python 3.13 | CI green | Source builds locally; not in CI |
| macOS | Community-tested | Source builds locally; not in CI |

Install the native extra with `uv sync --package plyunit --extra native`.
No `PLYUNIT_BUILD_NATIVE` flag is required. `Renderer` fails fast when the
native UBR extension cannot be loaded; there is no Python sprite fallback.
See [packages/plyunit-native/README.md](../plyunit-native/README.md).

## Quick start

```python
import plyunit as pu


class Main(pu.SceneUnit):
    def on_load(self) -> None:
        n = pu.NodeUnit(name="Hero")
        n.transform.set_position(100, 100)
        self.root.attach(n)


class App(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(Main())

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


pu.init(App(), pu.AppConfig(title="Game")).run()
```

The engine owns frame timing and fixed-step scheduling; the render pipeline
lives in the user's `update(dt)` hook. See
[migration.md](../../docs/id/migration.md) for the full hook contract.
