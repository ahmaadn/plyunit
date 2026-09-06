# Tilemap system

`TileMapNode` loads orthogonal map JSON, resolves tile GIDs through `Assets`,
culls by chunk, renders baked chunks or individual tiles, and can spawn static
collision through the optional `Physics` service.

**Current code:** `src/plyunit/tilemap/`

Copyable map, GID tileset, physics-shape, and baked-collision JSON examples:
[configuration-schemas.md](configuration-schemas.md#tilemap-and-tileset-configuration).

## Setup

```python
import plyunit as pu


class Level(pu.SceneUnit):
    def on_load(self) -> None:
        tilemap = pu.TileMapNode(
            name="WorldMap",
            config_path="data/maps/level.json",
            on_objects=self._load_objects,
        )
        self.root.attach(tilemap)

    def _load_objects(self, objects) -> None: ...
```

`Assets` is resolved from the global registry. If it is absent, map loading can
continue with a warning, but GID-backed tiles cannot display because the GID
texture map remains empty.

Enable collision through bootstrap:

```python
app = pu.init(
    GameApp(),
    pu.AppConfig(physics=pu.PhysicsConfig(enabled=True)),
)
```

The registry query name is `@Physics`.

## Data flow

```text
map JSON
  → map_data parsing / chunk store
  → Assets GID-to-texture/source mapping
  → optional render-target bake through Renderer.canvas
  → visible chunk selection from Camera2D view
  → Renderer.render_sprite submissions

collision metadata
  → physics_baker
  → BakedStaticBody records
  → physics_bridge
  → Physics.add_static_batch
```

Current modules:

| Path | Responsibility |
| --- | --- |
| `tilemap/tilemap.py` | `TileMapNode`, load, bake, cull, render, edits |
| `tilemap/map_data.py` | Parsed schema and runtime types |
| `tilemap/chunk_tile.py` | Chunk storage and visibility/LRU state |
| `tilemap/physics_baker.py` | Collision extraction and merge |
| `tilemap/physics_bridge.py` | Spawn/remove static physics bodies |
| `tilemap/encoding.py` | array, CSV, base64-zlib codecs |
| `tilemap/autotile.py` | Offline autotile processing |

There is no tilemap renderer facade or `RenderTargetOps` protocol in the
current implementation.

## Rendering modes

Each tile layer can define `render_mode`:

| Mode | Behavior |
| --- | --- |
| `auto` | Select baked or tiles behavior from layer/runtime requirements |
| `baked` | Bake a chunk/layer to a render texture, then submit one sprite |
| `tiles` | Submit one sprite per non-empty tile |

For layers other than `"1"`, `y_sort_enabled=True` forces the per-tile path
because individual tiles need separate y-order keys. Layer `"1"` does not apply
this override. Both paths use `Renderer.render_sprite` and eventually the common
FrameBuffer/native UBR sprite path.

Baked textures use **point filtering** to keep pixel tiles sharp. The current
tilemap bake path does not generate mipmaps or configure trilinear filtering.

## Layer fields

Common parsed layer fields include:

| Field | Parsed | Applied by current renderer |
| --- | --- | --- |
| `render_mode` | Yes | Yes |
| `y_sort_enabled` | Yes | Yes |
| `z_offset` | Yes | Yes |
| `visible` | Yes | No; currently metadata only |
| `opacity` | Yes | No; currently metadata only |
| `physics_enabled` | Yes | No; physics follows per-GID `tileset.physics` data |

Do not rely on `visible`, `opacity`, or `physics_enabled` to control current
runtime behavior until support is implemented.

## Oversized tile images

Images larger than one map cell have special handling:

- Native source dimensions are preserved.
- The tile is anchored from the bottom-left of its cell.
- Oversized images are excluded from baked render targets.
- They are submitted separately even when the layer uses baked mode.
- Chunk culling bounds account for image overhang.

This can add draw submissions to an otherwise one-sprite baked chunk.

## Camera culling and chunk lifetime

The active camera view determines visible chunk keys with a surrounding
margin. Loaded visible chunks submit render content; the chunk store maintains
streaming/LRU state. Tilemap culling is independent from pymunk broadphase and
from the optional `SpatialIndex` service.

## Runtime editing

```python
gid = tilemap.get_gid_at(world_x, world_y, layer_id="1")

tilemap.set_tile(world_x, world_y, gid=12, layer_id="1")
tilemap.remove_tile(world_x, world_y, layer_id="1")
tilemap.fill((x, y, width, height), gid=4, layer_id="1")

bodies = tilemap.get_physics_bodies_in_chunk(chunk_key, layer_id="1")
```

Edits update the chunk GID array and emit `tile_changed`. Current runtime
editing does not automatically invalidate/rebake render textures or collision;
`_invalidate_chunk` is a reserved no-op hook for editor integration.

## Physics lifecycle

`@Physics` is optional. Without it, static-body spawning is skipped. When it is
present, baked collision records are sent through `Physics.add_static_batch`.

Fallback physics baking may run on a daemon thread. `on_objects` is called after
map parsing and fallback initiation; it does not guarantee that asynchronous
physics baking has completed.

Scene unload must remove spawned statics through the bridge/service lifecycle
to avoid retaining collision from the previous map.

## Y-sort

Tile layers use `y_sort_enabled`. Other scene sprites can opt in through node
y-sort state or:

```python
pu.Renderer.enable_y_sort_layer(pu.Layer.ENTITIES, enabled=True)
```

This setting is process-global renderer state. Disable it explicitly when no
longer required.

## Limitations

- Orthogonal maps only.
- Missing `Assets` produces an empty visual GID map rather than a load error.
- `visible` and `opacity` are parsed but not applied by rendering.
- Baked textures use point filtering and no mipmaps.
- Oversized images remain separate submissions.
- Background physics bake completion has no documented completion signal.

## See also

- [assets-tilemap-particles.md](assets-tilemap-particles.md)
- [physics.md](physics.md)
- [rendering/queued-submit.md](rendering/queued-submit.md)
- [frame-execution-order.md](frame-execution-order.md)
