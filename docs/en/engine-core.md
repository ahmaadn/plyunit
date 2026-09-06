# Engine core

How the plyunit core works: App, unit hierarchy, services, scene stack, time.

## 1. Composition root

```python
import plyunit as pu

app = pu.init(pu.App(), pu.AppConfig(...))
# or
app = pu.create_app(pu.AppConfig(...))  # App() + bootstrap

app.run()
```

`init` sets up (at minimum):

- Window (raylib)
- `Canvas`, `Renderer`, `SceneManager`
- `Assets`, animations helpers
- `Window` (raylib window and frame clock via App loop)
- Optional: `Physics`, `ImGui`, and `Audio` from config

**Service queries** (unique name, `@` prefix):

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

### App signals / hooks (event-style `on_*`)

| Signal / hook | When |
| --- | --- |
| `on_load` | Once, before the loop |
| `on_load_complete` | After loading |
| `on_unload` | Once at shutdown, before service detach |
| `on_start_frame` / `on_end_frame` | Every wall-clock frame |
| `on_begin_update` / `on_end_update` | Each fixed step, around the user's `fixed_update` |
| `on_after_update` | Once per substep, after `fixed_update` returns |
| `on_fixed_update` | After transform sync (physics steps here) |

Subclassing:

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

    def on_unload(self) -> None: ...  # cleanup of application-owned resources
```

Use `self.quit()` to request the loop to stop. `App.run()` always calls
`shutdown()` exactly once, including scene unload, service detach,
renderer/UBR cleanup, and closing the window.

## 3. Unit hierarchy

| Class | Role |
| --- | --- |
| `Unit` | Base registry: name, tags, query (`one`, `group`, …) |
| `ServiceUnit` | Unique global service (`is_unique=True`) |
| `NodeUnit` | Scene graph: parent/children, transform, components |
| `SceneUnit` | Scene root: `root`, `TransformStore`, load/unload, dispatch |

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

- ServiceUnit queries force **global**.
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

| Hook | When |
| --- | --- |
| `on_enter_tree` | Enters the scene tree (after the **entire subtree** is registered) |
| `on_ready` | Once, after attach + parents ready |
| `on_exit_tree` | Leaves the tree (children first) |
| `update(dt)` | Fixed update (when overridden / active) |
| `render_submit(renderer, context)` | Queues draws |
| `draw(canvas)` | Only when custom draw is enabled |

**Attach order (Option A):** register + TransformStore bind for the entire
subtree first, then `on_enter_tree` preorder. Sibling/name queries are valid in
`on_enter_tree` and `on_ready`.

**Tree mutation policy:**

| Operation | During traversal / fixed step | Behavior |
| --- | --- | --- |
| `attach` | Any time | Immediate hierarchy/registry entry. The spawn gate skips the current fixed step; first update is the next step. Same-frame rendering is allowed. |
| `detach` / `destroy` | During `is_traversing` / flush | Mark and hide immediately; structural removal and lifecycle cleanup occur in the end-of-update flush. |
| `detach` / `destroy` | Outside traversal | Immediate as usual. |

Nodes attached during `scene.load()` are **not** gated (normal updates on the
first fixed step after load).

### Transform

```python
node.transform.set_position(x, y)
node.transform.set_rotation(deg)
node.transform.set_scale(sx, sy)
world = node.world_transform_lerp()  # render interpolation
```

In-scene source of truth: per-`SceneUnit` **`TransformStore`** (SoA).
In-scene reparenting uses `TransformStore.reparent` (without a full unbind).

### Components

```python
node.add_component(MyComponent())  # one type per node
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

Internal dispatch (do not call manually in game code):

- `_dispatch_update` → one tree update pass → **sync transforms** → SpatialIndex refresh → housekeeping
- `dispatch_render` → frustum cull + DFS submit

`load()` / `unload()` are managed by SceneManager.

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

- Maximum stack depth (see `MAX_STACK_DEPTH`).
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

`on_attach` is called when the service is created while the App is active.
Detach happens at app shutdown (reverse order).
See [audio.md](audio.md) for SFX, music streams, spatial audio, JSON banks, and
`AudioSource`.

## 8. Window Clock

```python
window = app.one("@Window")
# Clock fields used by engine:
# dt, unscaled_dt, fixed_delta_time, alpha, accumulator, time_scale
```

- **Fixed step**: gameplay + physics
- **alpha**: render interpolation (`world_transform_lerp`)
- Spiral of death: leftover accumulator is discarded after `max_substeps_per_frame`

## 9. TransformStore (summary)

- Per-scene SoA local/world + hierarchy links
- `bind` on enter tree, `unbind` swaps with last
- `sync()` linear scan with parent_index < child_index
- Physics dynamic write-back via `apply_physics_state` (without a full dirty cascade)

Frame details: [frame-execution-order.md](frame-execution-order.md).

## 10. EntityPool & SpatialIndex

See [pooling-and-spatial.md](pooling-and-spatial.md).

## 11. Gotchas

| Issue | Mitigation |
| --- | --- |
| `run()` without bootstrap | Window/renderer are None |
| Double physics step | Let only `on_fixed_update` step |
| One-shot spawn/jump multi-fires under lag | `Mouse`/`Keyboard` edges or `app.is_first_fixed_step` ([input-and-events.md](input-and-events.md)) |
| Querying a service from a node without global | `scope="global"` + `@Name` |
| Attach mid-update | OK — structure immediate; first `update` next fixed step |
| Detach/destroy mid-walk | OK — mark+hide now, flush at end of phase |
| Assigning `local.position =` at runtime | Use `set_position` |
| 8k NodeUnits for particles | Use a flat `render_batch` batch |

## 12. See also

- [getting-started.md](getting-started.md)
- [frame-execution-order.md](frame-execution-order.md)
- [naming-convention.md](naming-convention.md)
- [cheatsheet.md](cheatsheet.md)
