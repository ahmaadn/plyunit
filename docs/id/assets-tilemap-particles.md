# Assets, tilemap, and particles

## 1. Assets

Service/bootstrap memasang `Assets` di app (`app.assets` setelah bootstrap).

**Contoh:** `plyunit-assets` · `examples/test_assets/`

```python
class MyApp(pu.App):
    def on_load(self) -> None:
        self.assets.set_assets_path(Path(__file__).parent / "data")
        self.assets.load_spritesheet("tile/tileset.json")
        self.assets.load_asset("sprites/player.png")
        tex = self.assets.get_asset("player")  # or self.assets["player"]
```

Pola umum:

- Path root assets → `set_assets_path`
- JSON sidecar untuk frame/spritesheet
- Animations lewat `plyunit.assets.animations` / player clip data

Lihat example `test_assets` untuk struktur folder JSON + PNG.
Contoh lengkap schema image, spritesheet, dan animation ada di
[configuration-schemas.md](configuration-schemas.md).

### Texture atlas (opsional, in-memory)

`Assets.build_texture_atlas()` menggabungkan semua aset yang sudah dimuat
menjadi satu (atau beberapa) texture atlas **di memori** — tidak ada file
yang ditulis ke disk. Cukup satu baris setelah memuat aset:

```python
class MyApp(pu.App):
    def on_load(self) -> None:
        self.assets.load_spritesheet("tile/tileset.json")
        self.assets.load_asset("sprites/player.png")
        self.one("@Assets").build_texture_atlas()  # opsional
        ...
```

Perilaku:

- ID aset **tidak berubah** — entry cache diarahkan ulang ke region atlas,
  jadi game berjalan identik dengan atau tanpa atlas.
- Region spritesheet dan frame `Animations` (baik `asset_id` maupun
  `texture` langsung) otomatis diremap; texture lama di-unload dari GPU.
- Aset > `max_size` (default 2048) dibiarkan sebagai texture mandiri;
  lebih banyak aset otomatis mengalir ke halaman atlas berikutnya.
- Manfaat: sprite yang berbagi texture di-batch UBR jadi satu run/draw
  call — pantau lewat `renderer.profile_enabled` →
  `last_frame_profile["texture_run_count"]`.

Panggil setelah memuat aset dan **sebelum** scene/entity lain menyimpan
referensi texture langsung (`SpriteRenderer` ber-`asset_key` aman —
resolusinya lazy tiap frame; tilemap aman jika dimuat di scene
`on_load` seperti biasa).

**Contoh:** `plyunit-example texture-atlas` · `examples/example_texture_atlas.py`

## 2. Tilemap

`TileMapNode` memuat map, cull chunk, render baked chunk/individual tile, dan
optional physics.

**Contoh:** `plyunit-tilemap`, `plyunit-tilemap-physics`  
**Data sample:** `examples/tilemap/data/`  
**Arsitektur lengkap:** [tilemap-system.md](tilemap-system.md)
**Schema JSON:** [configuration-schemas.md](configuration-schemas.md#tilemap-and-tileset-configuration)

```python
from plyunit import TileMapNode

class Level(pu.SceneUnit):
    def on_load(self) -> None:
        self.tilemap = TileMapNode("WorldMap", map_path)
        self.root.attach(self.tilemap)
        # on_ready: resolve GIDs, bake RTs, spawn statics if physics bridge
```

Fitur terkait:

| Modul | Peran |
| --- | --- |
| `AutotileProcessor` | Autotile rules (offline) |
| Chunk store | Streaming + LRU; bake layer 1 → RenderTexture |
| Physics baker / bridge | Collision statics + one-way |

Hybrid render per layer meta: `render_mode` (`auto`/`baked`/`tiles`, default auto) + `y_sort_enabled` (default false; memaksa tiles). Auto ≈ L1 bake, L>1 per-tile. Map type hanya orthogonal. Detail: [tilemap-system.md](tilemap-system.md).

## 3. Particles

### Path A — Explicit ParticlePool

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

**Contoh:** `plyunit-particles` · `examples/example_particles.py`

### Path B — Component emitter

`ParticleEmitter` saat ini hanya helper spawn dengan pool yang belum terikat
renderer; component ini tidak otomatis update atau submit. Gunakan explicit
`ParticlePool` untuk lifecycle lengkap.

### Path C — Flat batch (maks performa)

Untuk ribuan quad sederhana, pola bunny:

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
| `slowness` | Ease; `<= 0` = snap (alias: `lerp_speed`) |
| `set_dead_zone` | Soft box before follow moves |
| `set_limits` | Optional clamp on `pos` |

Contoh: `plyunit-example --tilemap`, `--scissor-camera`.

## 5. Shaders & render targets

| CLI | Topik |
| --- | --- |
| `plyunit-shader` | Shader example |
| `plyunit-render-target` | Offscreen RT |
| `plyunit-blend-modes` | Blend |
| `plyunit-stencil` | Stencil masks |
| `plyunit-streaming-texture` | PBO streaming |

Engine: `Shaders`, `ShaderHandle`, typed `render_*` + state shader.

## 6. Text / fonts

`plyunit-text-font` · `examples/test_text_font/`  
API: `Text`, `TemplateText`, `Text.push`, dan `Renderer.render_shaped_text`.

## 7. Gotchas

| Issue | Fix |
| --- | --- |
| Assets path wrong | `set_assets_path` absolute/resolved |
| Tilemap blank | map path + tileset JSON valid |
| Particles not drawn | `submit` di `render_submit` setiap frame |
| Physics tiles leftover | unload scene / clear statics |
| Atlas: sprite salah region | panggil `build_texture_atlas` sebelum scene/entity load |

## 8. Lihat juga

- [physics.md](physics.md) tilemap physics  
- [rendering/index.md](rendering/index.md)  
- [examples-and-cli.md](examples-and-cli.md)  
