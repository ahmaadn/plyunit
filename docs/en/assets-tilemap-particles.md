# Assets, tilemap, and particles

## 1. Assets

The service/bootstrap installs `Assets` on the app (`app.assets` after bootstrap).

**Example:** `plyunit-assets` · `examples/test_assets/`

```python
class MyApp(pu.App):
    def on_load(self) -> None:
        self.assets.set_assets_path(Path(__file__).parent / "data")
        self.assets.load_spritesheet("tile/tileset.json")
        self.assets.load_asset("sprites/player.png")
        tex = self.assets.get_asset("player")  # or self.assets["player"]
```

Common patterns:

- Assets root path → `set_assets_path`
- JSON sidecars for frames/spritesheets
- Animations via `plyunit.assets.animations` / player clip data

See the `test_assets` example for the JSON + PNG folder layout.
Complete image, spritesheet, and animation schema examples live in
[configuration-schemas.md](configuration-schemas.md).

### Texture atlas (optional, in-memory)

`Assets.build_texture_atlas()` merges every loaded asset into one (or a few)
texture atlas pages **in memory** — no files are written to disk. One line is
enough after loading assets:

```python
class MyApp(pu.App):
    def on_load(self) -> None:
        self.assets.load_spritesheet("tile/tileset.json")
        self.assets.load_asset("sprites/player.png")
        self.one("@Assets").build_texture_atlas()  # optional
        ...
```

Behavior:

- Asset IDs **do not change** — cache entries are redirected to atlas regions,
  so the game runs identically with or without the atlas.
- Spritesheet regions and `Animations` frames (both `asset_id` and direct
  `texture` references) are remapped automatically; old textures are unloaded
  from the GPU.
- Assets larger than `max_size` (default 2048) stay standalone textures; extra
  assets flow automatically into additional atlas pages.
- Benefit: sprites sharing a texture are batched by UBR into a single
  run/draw call — monitor via `renderer.profile_enabled` →
  `last_frame_profile["texture_run_count"]`.

Call it after loading assets and **before** other scenes/entities capture raw
texture references (`SpriteRenderer` with an `asset_key` is safe — resolution
is lazy per frame; tilemaps are safe when loaded in scene `on_load` as usual).

**Example:** `plyunit-example texture-atlas` · `examples/example_texture_atlas.py`

## 2. Tilemap

`TileMapNode` loads maps, culls chunks, renders baked chunks/individual tiles,
and optionally drives physics.

**Examples:** `plyunit-tilemap`, `plyunit-tilemap-physics`  
**Sample data:** `examples/tilemap/data/`  
**Full architecture:** [tilemap-system.md](tilemap-system.md)  
**JSON schema:** [configuration-schemas.md](configuration-schemas.md#tilemap-and-tileset-configuration)

```python
from plyunit import TileMapNode

class Level(pu.SceneUnit):
    def on_load(self) -> None:
        self.tilemap = TileMapNode("WorldMap", map_path)
        self.root.attach(self.tilemap)
        # on_ready: resolve GIDs, bake RTs, spawn statics if physics bridge
```

Related features:

| Module | Role |
| --- | --- |
| `AutotileProcessor` | Autotile rules (offline) |
| Chunk store | Streaming + LRU; bakes layer 1 → RenderTexture |
| Physics baker / bridge | Collision statics + one-way |

Hybrid rendering per layer metadata: `render_mode` (`auto`/`baked`/`tiles`,
default auto) + `y_sort_enabled` (default false; forces per-tile). Auto ≈ L1
bake, L>1 per-tile. Map type is orthogonal only. Details:
[tilemap-system.md](tilemap-system.md).

## 3. Particles

### Path A — explicit ParticlePool

```python
from plyunit.core.particles import Particle, ParticlePool

self.particles = ParticlePool(renderer=self.renderer)
self.particles.spawn(
    Particle(
        position=(x, y),
        velocity=(vx, vy),
        lifetime=0.5,
        size=4.0,
        tint=(255, 200, 50, 255),
    )
)
self.particles.update(dt)

# render_submit
self.particles.submit(layer=pu.Layer.EFFECTS)
```

**Example:** `plyunit-particles` · `examples/example_particles.py`

### Path B — component emitter

`ParticleEmitter` is currently only a spawn helper bound to a pool without a
renderer; the component does not update or submit automatically. Use an
explicit `ParticlePool` for the full lifecycle.

### Path C — flat batch (maximum performance)

For thousands of simple quads, the bunny pattern:

```python
renderer.render_batch(texture=tex, pos_xy=pos_xy, positions=pos_xy, ...)
```

[rendering/ubr.md](rendering/ubr.md).

## 4. Camera2D

Center-follow camera with optional easing, dead zone, and bounds. `App` updates
the active camera automatically once per render frame.

```python
self.camera = pu.Camera2D(size=(320, 240), position=(0, 0), slowness=0.3)
self.camera.setup(800, 600)
self.camera.set_target(player)   # or (x, y)
self.camera.set_dead_zone(64, 48)
self.camera.teleport(player)     # snap

```

| Field | Meaning |
| --- | --- |
| `pos` | Current focus (world center) |
| `slowness` | Easing; `<= 0` = snap (alias: `lerp_speed`) |
| `set_dead_zone` | Soft box before follow moves |
| `set_limits` | Optional clamp on `pos` |

Examples: `plyunit-example --tilemap`, `--scissor-camera`.

## 5. Shaders & render targets

| CLI | Topic |
| --- | --- |
| `plyunit-shader` | Shader example |
| `plyunit-render-target` | Offscreen RT |
| `plyunit-blend-modes` | Blend |
| `plyunit-stencil` | Stencil masks |
| `plyunit-streaming-texture` | PBO streaming |

Engine: `Shaders`, `ShaderHandle`, typed `render_*` + state shader.

## 6. Text / fonts

`plyunit-text-font` · `examples/test_text_font/`  
API: `Text`, `TemplateText`, `Text.push`, and `Renderer.render_shaped_text`.

## 7. Gotchas

| Issue | Fix |
| --- | --- |
| Wrong assets path | Use an absolute/resolved `set_assets_path` |
| Blank tilemap | Valid map path + tileset JSON |
| Particles not drawn | Call `submit` in `render_submit` every frame |
| Leftover physics tiles | Unload the scene / clear statics |
| Atlas: sprite shows the wrong region | Call `build_texture_atlas` before scenes/entities load |

## 8. See also

- [physics.md](physics.md) tilemap physics  
- [rendering/index.md](rendering/index.md)  
- [examples-and-cli.md](examples-and-cli.md)  
