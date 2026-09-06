# Engine core

Cara kerja inti plyunit: App, unit hierarchy, services, scene stack, time.

## 1. Composition root

```python
import plyunit as pu

app = pu.init(pu.App(), pu.AppConfig(...))
# or
app = pu.create_app(pu.AppConfig(...))  # App() + bootstrap

app.run()
```

`init` memasang (minimal):

- Window (raylib)
- `Canvas`, `Renderer`, `SceneManager`
- `Assets`, animations helpers
- `Window` (raylib window and frame clock via App loop)
- Optional: `Physics`, `ImGui`, dan `Audio` dari config

**Query service** (unique name, prefix `@`):

```python
physics = app.one("@Physics")
bus = scene.one_or_none("@EventBus", scope="global")
```

## 2. App lifecycle

```
init
app.run()
  on_load
  on_load_complete
  while running:
    on_start_frame
    fixed updates (0..max_substeps)
    update(dt)          # user hook — render pipeline
    on_end_frame
  SceneManager.shutdown
  on_unload
  service on_detach (reverse)
  animations/assets/renderer cleanup
  close window
```

### Signals / hooks App (event-style `on_*`)

| Signal / hook | Kapan |
| --- | --- |
| `on_load` | Sekali sebelum loop |
| `on_load_complete` | Setelah load |
| `on_unload` | Sekali saat shutdown, sebelum service detach |
| `on_start_frame` / `on_end_frame` | Tiap frame wall-clock |
| `on_begin_update` / `on_end_update` | Each fixed step, around the user's `fixed_update` |
| `on_after_update` | Once per substep, after `fixed_update` returns |
| `on_fixed_update` | Setelah sync transform (physics step di sini) |

Subclass:

```python
class GameApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(
        self, dt: float
    ) -> None: ...  # per-frame render pipeline (camera, renderer, window)

    def on_unload(self) -> None: ...  # cleanup resource milik aplikasi
```

Gunakan `self.quit()` untuk meminta loop berhenti. `App.run()` selalu
memanggil `shutdown()` tepat satu kali, termasuk scene unload, service detach,
renderer/UBR cleanup, dan penutupan window.

## 3. Unit hierarchy

| Class | Peran |
| --- | --- |
| `Unit` | Base registry: name, tags, query (`one`, `group`, …) |
| `ServiceUnit` | Service global unique (`is_unique=True`) |
| `NodeUnit` | Scene graph: parent/children, transform, components |
| `SceneUnit` | Root scene: `root`, `TransformStore`, load/unload, dispatch |

```
App (ServiceUnit)
  services: SceneManager, Renderer, Physics?, ImGui?, Input?, EventBus?
  SceneManager stack
    SceneUnit
      root: NodeUnit
        children NodeUnit…
          components…
```

### Query scope

```python
unit.one("@Camera2D", scope="global")  # global registry
unit.one("Player", scope="scene")  # scene registry
unit.one_or_none("@EventBus", scope="mixed")  # scene then global
```

- ServiceUnit query memaksa **global**.
- Unique name: string `"@Name"`.
- Tag: `find_by_tag("enemy")`.

## 4. NodeUnit

```python
node = pu.NodeUnit(name="Hero", tags={"player"})
parent.attach(node)
parent.detach(node)
node.destroy()
```

### Lifecycle

| Hook | Kapan |
| --- | --- |
| `on_enter_tree` | Masuk scene tree (setelah **seluruh subtree** terdaftar di registry) |
| `on_ready` | Sekali setelah attach + parents ready |
| `on_exit_tree` | Keluar tree (children-first) |
| `update(dt)` | Fixed update (jika override / aktif) |
| `render_submit(renderer, context)` | Antri draw |
| `draw(canvas)` | Hanya jika custom draw enabled |

**Attach order (Opsi A):** register + TransformStore bind untuk seluruh subtree, baru `on_enter_tree` preorder. Query sibling/name valid di `on_enter_tree` dan `on_ready`.

**Tree mutation policy:**

| Op | Saat traversal / fixed step | Perilaku |
| --- | --- | --- |
| `attach` | Any time | Immediate hierarchy/registry entry. The spawn gate skips the current fixed step; first update is the next step. Same-frame rendering is allowed. |
| `detach` / `destroy` | During `is_traversing` / flush | Mark and hide immediately; structural removal and lifecycle cleanup occur in the end-of-update flush. |
| `detach` / `destroy` | Di luar traversal | Immediate seperti biasa. |

Node attach selama `scene.load()` **tidak** di-gate (update normal di fixed step pertama setelah load).

### Transform

```python
node.transform.set_position(x, y)
node.transform.set_rotation(deg)
node.transform.set_scale(sx, sy)
world = node.world_transform_lerp()  # interpolasi render
```

Source of truth in-scene: **`TransformStore`** (SoA) per `SceneUnit`.
In-scene reparent memakai `TransformStore.reparent` (tanpa unbind penuh).

### Components

```python
node.add_component(MyComponent())  # satu tipe per node
node[MyComponent]
node.has_component(MyComponent)
node.destroy_component(comp)
```

Component hooks: `on_attach`, `on_start`, `update`, `render_submit`, `on_destroy`.

### Flags & render state

```python
node.set_active(True)
node.set_visible(True)
node.set_scissor(world_rect)  # world AABB
node.set_blend_mode(pu.BlendMode.ADDITIVE)
node.set_shader(shader)
node.layer = int(pu.Layer.ENTITIES)
node.z_index = 0
node.y_sort_enabled = False
```

## 5. SceneUnit

```python
class Level(pu.SceneUnit):
    def on_load(self) -> None: ...
    def on_unload(self) -> None: ...
    def update(self, dt: float) -> None: ...
    def render_submit(self, renderer) -> None: ...  # scene-level draws
```

Internal dispatch (jangan dipanggil manual di game code):

- `_dispatch_update` → one tree update pass → **sync transforms** → SpatialIndex refresh → housekeeping
- `dispatch_render` → frustum cull + DFS submit

`load()` / `unload()` dikelola SceneManager.

## 6. SceneManager

```python
sm = app.scene_manager  # or one("@SceneManager")

# Deferred until `App.on_after_update` has completed
sm.push(scene)
sm.pop()
sm.change(scene)
sm.replace_all(scene)

# Behavior / fade helpers (factories)
sm.request_push(lambda: MenuScene())
sm.request_change(lambda: Level1())
```

- Stack depth max (lihat `MAX_STACK_DEPTH`).
- `push`/`change` never load synchronously during update; `App` applies them at the post-update boundary.

## 7. ServiceUnit

```python
# Optional audio (flag-gated)
cfg = pu.AppConfig(audio=pu.AudioConfig(enabled=True))
pu.init(app, cfg)

audio = one("@Audio")  # or one("Audio")
audio.load_sound("sfx/jump.wav", sound_id="jump")
audio.play_sound("jump")
```

`on_attach` dipanggil saat service selesai dibuat ketika App aktif. Detach saat app shutdown (reverse order).
Lihat [audio.md](audio.md) untuk SFX, music stream, spatial, bank JSON, dan `AudioSource`.

## 8. Window Clock

```python
window = app.one("@Window")
# Clock fields used by engine:
# dt, unscaled_dt, fixed_delta_time, alpha, accumulator, time_scale
```

- **Fixed step**: gameplay + physics
- **alpha**: interpolasi render (`world_transform_lerp`)
- Spiral-of-death: sisa accumulator dibuang setelah `max_substeps_per_frame`

## 9. TransformStore (ringkas)

- Per-scene SoA local/world + hierarchy links
- `bind` on enter tree, `unbind` swap-with-last
- `sync()` linear scan parent_index < child_index
- Physics dynamic write-back lewat `apply_physics_state` (tanpa dirty cascade penuh)

Detail frame: [frame-execution-order.md](frame-execution-order.md).

## 10. EntityPool & SpatialIndex

Lihat [pooling-and-spatial.md](pooling-and-spatial.md).

## 11. Gotchas

| Issue | Mitigation |
| --- | --- |
| `run()` tanpa bootstrap | Window/renderer None |
| Double physics step | Hanya biarkan `on_fixed_update` |
| One-shot spawn/jump multi-fires under lag | `Mouse`/`Keyboard` edges or `app.is_first_fixed_step` ([input-and-events.md](input-and-events.md)) |
| Query service dari node tanpa global | `scope="global"` + `@Name` |
| Attach mid-update | OK — struktur immediate; first `update` next fixed step |
| Detach/destroy mid-walk | OK — mark+hide now, flush end of phase |
| Assign `local.position =` runtime | Pakai `set_position` |
| 8k NodeUnit untuk particle | Pakai flat `render_batch` batch |

## 12. Lihat juga

- [getting-started.md](getting-started.md)
- [frame-execution-order.md](frame-execution-order.md)
- [naming-convention.md](naming-convention.md)
- [cheatsheet.md](cheatsheet.md)
