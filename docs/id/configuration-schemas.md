# Configuration schema examples

Halaman ini mendokumentasikan struktur JSON yang saat ini diterima oleh `plyunit`. Contoh-contoh ini didasarkan pada implementasi parser dan bukan merupakan dokumen JSON Schema formal. Kecuali dinyatakan lain, kunci yang tidak dikenal mungkin diabaikan oleh parser aset/peta yang bersifat permisif, sedangkan `AppConfig` akan menolak kolom konstruktor yang tidak dikenal.

## Format overview

| File | Loaded by | Purpose |
| --- | --- | --- |
| App config | `AppConfig.from_file`, `init` | Window, timing, physics, ImGui, audio |
| Image asset | `Assets.load_asset` | One texture plus texture options |
| Spritesheet asset | `Assets.load_spritesheet` | One texture split into named regions |
| Animation config | `Animations.load` | Clips composed from asset/region IDs |
| Font config | `Font.load` | Font files and named text templates |
| Tilemap | `TileMapNode` | Layers, GID mappings, chunks, objects, collision |
| Audio bank | `Audio.load_bank` | SFX and music entries |
| Autotile config | `AutotileProcessor` | Offline/editor bitmask rules |

Tidak ada format JSON untuk shader. Shader dimuat melalui `Shaders.load` atau
`Shaders.load_from_memory`.

## App configuration

Muat file JSON secara langsung melalui bootstrap:

```python
app = pu.init(GameApp(), "data/app.json")
app.run()
```

Contoh komplit:

```json
{
  "title": "My Game",
  "window_width": 1280,
  "window_height": 720,
  "target_fps": 60,
  "fixed_update_hz": 60,
  "max_frame_delta_time": 0.25,
  "max_substeps_per_frame": 5,
  "background_color": [24, 32, 48, 255],
  "log_level": "INFO",
  "log_file_path": null,
  "physics": {
    "enabled": true,
    "gravity": [0.0, 900.0],
    "world_bounds": [-10000.0, -10000.0, 10000.0, 10000.0],
    "spatial_hash_dim": 100.0,
    "spatial_hash_count": 1000,
    "sleep_time_threshold": 0.5,
    "idle_speed_threshold": 10.0,
    "iterations": 10,
    "damping": 1.0,
    "enable_spatial_hash": true
  },
  "imgui": {
    "enabled": false,
    "dark_style": true,
    "no_ini": true
  },
  "audio": {
    "enabled": true,
    "master_volume": 1.0,
    "sfx_volume": 1.0,
    "music_volume": 0.8,
    "assets_path": "./data/audio",
    "max_voices": 32,
    "spatial_min_distance": 50.0,
    "spatial_max_distance": 800.0,
    "spatial_rolloff": 1.0
  }
}
```

Contoh minimal:

```json
{
  "title": "My Game",
  "window_width": 800,
  "window_height": 600
}
```

Aturan validasi penting:

- Dimensi jendela, `fixed_update_hz`, `max_frame_delta_time`, dan
`max_substeps_per_frame` harus lebih besar dari nol.
- `target_fps` boleh bernilai nol untuk *frame rate* tanpa batas.
- Volume audio harus berada di antara `0,0` dan `1,0`.
- `spatial_max_distance` harus lebih besar daripada `spatial_min_distance`.
- *Field* akar atau *field* bersarang yang tidak dikenal akan ditolak.

## Image asset configuration

Konfigurasikan basis aset sekali saja, lalu muat jalur yang relatif terhadapnya:

```python
self.assets.set_assets_path("data/assets")
self.assets.load_asset("characters/hero.json")
hero_texture = self.assets["hero"]
```

`data/assets/characters/hero.json`:

```json
{
  "id": "hero",
  "type": "image",
  "image_path": "characters/hero.png",
  "texture": {
    "filter": "nearest",
    "wrap": "clamp",
    "mipmap": false,
    "srgb": true,
    "premultiply_alpha": false,
    "color_key": [0, 0, 0, 255]
  }
}
```

Asset fields:

| Field | Required | Default |
| --- | --- | --- |
| `id` | No | JSON filename stem |
| `type` | No | `"image"` |
| `image_path` | Yes | None |
| `texture` | No | Loader defaults |

Texture fields:

| Field | Values | Default |
| --- | --- | --- |
| `filter` | `"nearest"`, `"linear"` | `"nearest"` |
| `wrap` | `"repeat"`, `"clamp"`, `"mirror"` | `"clamp"` |
| `mipmap` | boolean | `false` |
| `srgb` | boolean | `true`; parsed/stored but currently ignored by raylib |
| `premultiply_alpha` | boolean | `false` |
| `color_key` | `[r, g, b, a]` | `[0, 0, 0, 255]` |

Saat diload melalui `load_asset`, `load_spritesheet`, atau `load_folder`,
`image_path` pertama-tama diselesaikan (resolved) relatif terhadap basis aset. Jika tidak
ditemukan, loader juga akan memeriksa keberadaan gambar di lokasi yang sama dengan file JSON pendampingnya.
Path yang telah diselesaikan harus tetap berada di dalam direktori basis aset.

File gambar langsung tidak memerlukan JSON:

```python
self.assets.load_asset("ui/icon.png")  # cache ID: icon
```

## Spritesheet asset configuration

Spritesheet adalah aset gambar dengan `type: "spritesheet"`.
Baik region berupa array ringkas maupun region berupa objek dapat diterima:

```json
{
  "id": "hero_sheet",
  "type": "spritesheet",
  "image_path": "characters/hero.png",
  "texture": {
    "filter": "nearest",
    "wrap": "clamp",
    "mipmap": false,
    "premultiply_alpha": false
  },
  "regions": {
    "hero_idle_0": [0, 0, 32, 32],
    "hero_idle_1": {
      "rect": [32, 0, 32, 32]
    },
    "hero_run_0": [0, 32, 32, 32],
    "hero_run_1": [32, 32, 32, 32]
  }
}
```

Load and query it:

```python
self.assets.load_spritesheet("characters/hero-sheet.json")

texture_data = self.assets.get_texture_data("hero_run_0")
texture = texture_data.texture
source = texture_data.source_rect
parent_id = texture_data.parent_id  # hero_sheet
```

List regions must contain exactly four values. Object regions use the first
four values of `rect`; a missing `rect` defaults to `[0, 0, 0, 0]`, and region
dimensions are not validated. Region IDs enter the same asset cache as ordinary
image IDs, so they should be globally unique.

The supported root ID field is `id`. Some old example/editor files contain
`asset_id`, but the current spritesheet parser does not use that key as the
spritesheet ID.

## Animation configuration

Animations are no longer embedded in spritesheet JSON (`animation_groups`
was removed); load them from standalone files instead. Standalone
animation files use these group and clip shapes:

```json
{
  "group": "hero",
  "animations": {
    "hero.run": {
      "default": {
        "duration": 0.1,
        "source_rect": null
      },
      "frames": [
        {"asset_id": "hero_run_0"},
        {"asset_id": "hero_run_1", "duration": 0.12}
      ],
      "loop": true,
      "speed": 1.0,
      "paused": false
    }
  }
}
```

```python
self.animations.set_base_path(Path("data/animations"))
self.animations.load("hero.json")
run = self.animations.get_clip("hero.run")
```

Animation fields:

| Field | Required | Default |
| --- | --- | --- |
| `group` | No | No group |
| `animations` | For useful output | `{}` |
| clip `frames` | For clip creation | Empty clips are skipped |
| clip `default.duration` | No | `0.1` |
| clip `default.source_rect` | No | `null` |
| clip `loop` | No | `true` |
| clip `speed` | No | `1.0` |
| clip `paused` | No | `false` |
| frame `asset_id` | Yes in JSON | None |
| frame `duration` | No | Clip default or `0.1` |
| frame `source_rect` | No | Clip default or `null` |

Every frame duration and clip speed must be greater than zero.

## Font and text configuration

Font config maps logical font names to resources and creates named text
templates:

```json
{
  "fonts": {
    "main": {
      "path": "fonts/main.ttf"
    },
    "pixel": {
      "path": "fonts/pixel.png",
      "color_key": [255, 0, 255, 255],
      "first_char": 32
    }
  },
  "templates": {
    "title": {
      "font": "main",
      "spacing": 1,
      "size": 32
    },
    "hud": {
      "font": "pixel",
      "spacing": 0,
      "size": 16
    }
  }
}
```

Font entry fields:

| Field | Required | Default |
| --- | --- | --- |
| `path` | Yes | Missing entries are skipped |
| `color_key` | Bitmap font only | `[255, 0, 255, 255]` |
| `first_char` | Bitmap font only | `32` |

Template fields default to `font: "default"`, `spacing: 0`, and `size: 16`.
The logical font name `default` is reserved for the backend default font.

## Tilemap and tileset configuration

Two different files are involved in a typical tilemap project:

1. A spritesheet asset JSON defines texture regions such as `tile_grass`.
2. The map JSON embeds a `tilesets` mapping from numeric GIDs to those asset IDs.

The tilemap does not currently load a separate runtime tileset schema.

Minimal complete map using uncompressed arrays:

```json
{
  "version": "2.0",
  "map_type": "orthogonal",
  "settings": {
    "tile_size": [16, 16],
    "chunk_size": 2,
    "encoding": "array",
    "background_color": [24, 32, 48, 255]
  },
  "tilesets": {
    "1": {
      "gid": 1,
      "asset_id": "tile_grass"
    },
    "2": {
      "gid": 2,
      "asset_id": "tile_wall",
      "physics": {
        "layer": 1,
        "mask": 65535,
        "shape": {
          "kind": "box",
          "offset": [0, 0],
          "size": [16, 16]
        },
        "is_one_way": false,
        "friction": 0.5,
        "restitution": 0.0
      }
    }
  },
  "layers": {
    "1": {
      "name": "Ground",
      "visible": true,
      "opacity": 1.0,
      "z_offset": 0,
      "physics_enabled": true,
      "y_sort_enabled": false,
      "render_mode": "baked"
    },
    "2": {
      "name": "Props",
      "visible": true,
      "opacity": 1.0,
      "z_offset": 10,
      "physics_enabled": false,
      "y_sort_enabled": true,
      "render_mode": "tiles"
    }
  },
  "objects": [
    {
      "type": "player_spawn",
      "world_x": 16,
      "world_y": 16,
      "properties": {
        "facing": "right"
      }
    }
  ],
  "chunks": {
    "0,0": {
      "chunk_x": 0,
      "chunk_y": 0,
      "encoding": "array",
      "layers": {
        "1": [1, 1, 2, 2],
        "2": [0, 0, 0, 1]
      },
      "baked_physics": {}
    }
  }
}
```

For `chunk_size: 2`, each complete layer array contains four row-major GIDs.
GID `0` means an empty tile.

Map fields and defaults:

| Field | Default |
| --- | --- |
| `version` | `"1"` |
| `map_type` | `"orthogonal"`; other values normalize to orthogonal |
| `settings.tile_size` | `[16, 16]` |
| `settings.chunk_size` | `16` |
| `settings.encoding` | `"csv"` |
| `settings.background_color` | `[0, 0, 0, 255]` |
| `tilesets` | `{}` |
| `layers` | `{}` |
| `objects` | `[]` |
| `chunks` | `{}` |

Supported layer encodings:

```json
{
  "array": [1, 0, 2, 3],
  "csv": "1,0,2,3",
  "base64_zlib": "base64-encoded zlib-compressed little-endian uint32 data"
}
```

The sample object above demonstrates the shapes; actual chunk `layers` values
must use the encoding selected by the map or chunk.

`render_mode` has explicit behavior for `"baked"` and `"tiles"`; `"auto"` and
unknown values use automatic behavior because unknown values are not rejected.
For layers other than `"1"`, `y_sort_enabled: true` forces per-tile rendering;
layer `"1"` does not apply this override. `visible`, `opacity`, and
`physics_enabled` are currently parsed metadata but are not applied. Physics is
generated for any chunk layer containing GIDs with `tileset.physics` data.

### Tile physics shapes

Box:

```json
{
  "kind": "box",
  "offset": [0, 0],
  "size": [16, 16]
}
```

Circle:

```json
{
  "kind": "circle",
  "offset": [8, 8],
  "radius": 6
}
```

Convex polygon:

```json
{
  "kind": "polygon",
  "vertices": [[0, 16], [8, 0], [16, 16]]
}
```

### Pre-baked chunk collision

Editors may persist merged static bodies per chunk and layer:

```json
{
  "baked_physics": {
    "1": {
      "bodies": [
        {
          "shape": {
            "kind": "box",
            "offset": [0, 0],
            "size": [32, 16]
          },
          "world_pos": [0, 0],
          "physics_layer": 1,
          "physics_mask": 65535,
          "is_one_way": false,
          "friction": 0.5,
          "restitution": 0.0
        }
      ]
    }
  }
}
```

Place this object in a chunk alongside `chunk_x`, `chunk_y`, and `layers`.

## Audio bank configuration

`Audio.load_bank` loads every entry eagerly:

```json
{
  "id": "main_bank",
  "base_path": ".",
  "entries": [
    {
      "id": "jump",
      "path": "sfx/jump.wav",
      "kind": "sound",
      "volume": 0.9,
      "group": "gameplay"
    },
    {
      "id": "title_music",
      "path": "music/title.ogg",
      "kind": "music",
      "volume": 0.6,
      "loop": true,
      "group": "music"
    }
  ]
}
```

```python
audio = self.one("@Audio", scope="global")
bank_id = audio.load_bank("main-bank.json")
```

Bank defaults:

| Field | Default |
| --- | --- |
| Root `id` | JSON filename stem |
| `base_path` | `"."` |
| `entries` | `[]` |
| Entry `kind` | `"sound"` |
| Entry `volume` | `1.0` |
| Entry `loop` | `true` |
| Entry `group` | `null` |

Every entry requires non-empty `id` and `path`. `kind` accepts only `"sound"`
or `"music"`. Paths are resolved under `AudioConfig.assets_path`; traversal
outside that directory is rejected.

## Autotile configuration

`AutotileProcessor` accepts a dictionary or JSON file path. It is intended for
offline/editor processing rather than frame-time work:

```json
{
  "autotiles": {
    "grass": {
      "fallback_region": "grass_fallback",
      "bitmasks": {
        "15": "grass_sides",
        "255": [16, 0, 16, 16],
        "240": {
          "random": [
            {"id": "grass_corner_a", "weight": 1.0},
            {"id": "grass_corner_b", "weight": 2.0},
            {"rect": [32, 0, 16, 16], "weight": 0.5}
          ]
        }
      }
    }
  }
}
```

```python
processor = pu.AutotileProcessor("data/autotiles.json", seed=1234)
mask = processor.calculate_bitmask(
    grid,
    x,
    y,
    target_type="grass",
    mode="match_corners_and_sides",
)
region, weight = processor.resolve_tile("grass", mask)
```

Supported matching modes are `"match_sides"`, `"match_corners"`, and
`"match_corners_and_sides"`. `calculate_bitmask` produces values from `0` to
`255`, but configuration keys are not format/range validated; lookup uses
`str(bitmask)`. Random choices default to weight `1.0`.

## Existing examples

Repository examples using these formats:

| Format | Example |
| --- | --- |
| Spritesheet | `examples/tilemap/data/tileset.json` |
| Standalone animation | `examples/test_assets/data/player/animations.json` |
| Tilemap | `examples/tilemap/data/map_lake.json` |
| Image sidecars | `examples/test_assets/data/images/` |

See [assets-tilemap-particles.md](assets-tilemap-particles.md),
[tilemap-system.md](tilemap-system.md), and [audio.md](audio.md) for runtime
behavior around these files.
