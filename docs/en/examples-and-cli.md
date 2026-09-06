# Examples and CLI entry points

`examples/` and `benchmarks/` live at the **monorepo root** (dev-only, not in the plyunit wheel).

## Run examples (CLI)

```bash
# List available examples
uv run plyunit-example --list
# or
uv run python examples/cli.py --list

# Run by short flag
uv run plyunit-example --shapes
uv run plyunit-example --physics
uv run plyunit-example --tilemap

# Equivalent forms
uv run plyunit-example --example shapes
uv run python examples/cli.py --shapes
```

## Available flags

| Flag | Topic |
| --- | --- |
| `--input` | Keyboard poll + NodeUnit |
| `--event-bus-input` | EventBus + key/mouse events |
| `--imgui` | ImGui debug UI |
| `--immediate-render` | DrawScope IMMEDIATE |
| `--shapes` | Primitive shapes |
| `--ysort` | Y-sort |
| `--blend-modes` | Blend modes |
| `--shader` | Shaders |
| `--scissor` | Scissor |
| `--scissor-camera` | Scissor + Camera2D |
| `--render-target` | Offscreen RT |
| `--stencil` | Stencil |
| `--streaming-texture` | Streaming / PBO texture |
| `--text-font` | Fonts / text |
| `--particles` | Particle facade |
| `--physics` | Full physics demo |
| `--tilemap` | TileMapNode |
| `--tilemap-physics` | Tilemap + collision |
| `--assets` | Assets loading |
| `--texture-atlas` | In-memory texture atlas (optional) |
| `--transition-scene` | Scene push/pop |
| `--tween` | Timer + TweenAnimation |

## Benchmarks

```bash
uv run python benchmarks/bunny_benchmark.py
uv run python benchmarks/node_benchmark/main.py
uv run python benchmarks/physics_benchmark.py
uv run python benchmarks/shapes_benchmark.py
```

Reports: `benchmarks/reports/*_<YYYYMMDD_HHMMSS>.txt`.

Bunny targets & UBR: [batch-render.md](batch-render.md), [rendering/ubr.md](rendering/ubr.md).

## Canonical example pattern

```python
class DemoApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(DemoScene())


def main() -> None:
    app = pu.init(DemoApp(), pu.AppConfig(...))
    app.run()
```

## Map to documents

| Want to learn | Open |
| --- | --- |
| Bootstrap | [getting-started.md](getting-started.md) |
| Physics | [physics.md](physics.md) + `--physics` |
| Input | [input-and-events.md](input-and-events.md) |
| ImGui | [imgui.md](imgui.md) |
| Immediate | [immediate-rendering.md](immediate-rendering.md) |
| Batch sprites | [rendering/index.md](rendering/index.md) |
