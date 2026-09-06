# Audio

Optional SFX + music + 2D spatial audio via service `Audio` (raylib/pyray backend).

## Enable

```python
import plyunit as pu

cfg = pu.AppConfig(
    title="Game",
    audio=pu.AudioConfig(
        enabled=True,
        master_volume=1.0,
        sfx_volume=1.0,
        music_volume=0.8,
        assets_path="./data/audio",
    ),
)
pu.init(App(), cfg).run()
```

Query: `one("@Audio")` / `one("Audio")`.

## Load & play

```python
audio = self.one("@Audio", scope="global")
audio.load_sound("sfx/jump.wav", sound_id="jump")
audio.load_music("music/title.ogg", music_id="bgm")

audio.play_sound("jump", volume=0.9)
audio.play_music("bgm", loop=True)

# 2D spatial — listener (ear) vs source
# Prefer: bind a NodeUnit once (auto-follows world pos each frame)
audio.set_listener(player_node)

# Or fixed coords (must re-call when the ear moves)
audio.set_listener(player_x, player_y)

audio.play_sound_at("jump", enemy_x, enemy_y, track=True)
```

| API | Behavior |
| --- | --- |
| `set_listener(node)` | Auto-follow `node.transform.world.position` from `on_start_frame` |
| `set_listener(x, y)` | Fixed position; clears node follow |
| `clear_listener_follow()` | Stop following; keep last `(x, y)` |
| `listener` | Current ear position `(x, y)` (from node or fixed) |
| `listener_node` | Bound node or `None` |

Music streams are updated once per **wall-clock** frame (`on_start_frame`). Do not call backend stream update from fixed substeps.

## Sound bank JSON

See also the field/default reference in
[configuration-schemas.md](configuration-schemas.md#audio-bank-configuration).

```json
{
  "id": "main_bank",
  "base_path": ".",
  "entries": [
    {"id": "jump", "path": "sfx/jump.wav", "kind": "sound", "volume": 0.9},
    {"id": "bgm_title", "path": "music/title.ogg", "kind": "music", "volume": 0.6, "loop": true}
  ]
}
```

```python
audio.load_bank("bank.json")  # paths sandboxed under assets_path
```

`base_path` di bank relatif terhadap `AudioConfig.assets_path`; resolved paths
tetap harus berada di bawah direktori tersebut.

Supported formats depend on the raylib build (commonly `.wav`, `.ogg`; `.mp3` may be available).

## Volume buses

Effective SFX volume = `master * sfx * instance * spatial_attenuation`
Effective music volume = `master * music * instance`

```python
audio.set_master_volume(0.8)
audio.set_sfx_volume(1.0)
audio.set_music_volume(0.5)
```

## AudioSource component

```python
from plyunit.core.components.builtin import AudioSource

node = pu.NodeUnit(name="Enemy")
node.add_component(AudioSource("jump", auto_play=True, spatial=True, volume=0.9))
```

| Field | Notes |
| --- | --- |
| `kind` | `"sound"` or `"music"` |
| `spatial` | SFX only; follows `transform.world.position` |
| `loop` | Music uses stream loop; SFX re-triggers when finished |
| `auto_play` | Starts in `on_start` |
| destroy | Stops owned voice / music if still owner |

Requires `Audio` registered (enable `AppConfig.audio` or construct it while the App is active).

## Manual wiring

```python
audio = pu.Audio.from_config(pu.AudioConfig(enabled=True))
```

## Lifecycle

1. `init` after window init → `Audio.from_config` → registry retention
2. `on_attach` → `InitAudioDevice`, connect `on_start_frame`
3. Frame → update music stream + tracked voice pan/volume
4. `on_detach` → stop/unload/`CloseAudioDevice` (before window close)

## Limits

- One active music stream
- One global listener (`set_listener` node **or** x/y; not multi-ear)
- No Camera2D auto-bind (pass the camera target / player node yourself)
- Bank `group` is metadata only (no extra buses)
- Concurrent same-SFX prefers raylib sound aliases when available
