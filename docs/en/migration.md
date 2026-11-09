# Migration: hexagonal architecture and App flow (breaking)

> **Breaking change — no compatibility path.** Backend-neutral code now
> depends on `plyunit.backends.ports`, and concrete services/resources belong
> to adapters. Removed imports, loaders, resource accessors, and primitive
> submit methods have no aliases or shims. The App flow change also removes
> `late_update` and the engine-owned render pipeline. Rewrite callers to the
> current contracts; do not add a parallel legacy path.

## Hexagonal migration

| Removed usage | Current contract |
| --- | --- |
| `plyunit.backends.interfaces` | `plyunit.backends.ports` |
| Neutral code importing concrete backends or backend selectors | Inject ports; select implementations only at composition/facade boundaries |
| Old top-level asset/audio packages or service loader folders | Neutral data in `plyunit.services`; concrete services in `plyunit.backends.integrations.raylib` |
| Raw native resources or `from_raw` constructors in ports/core | Opaque handle contracts; concrete resources stay inside adapters |
| `get_texture_data(id).texture` | `Assets.get_asset(id)` / `Assets[id]`, which returns the handle directly |
| Treating `Texture2D.texture_id` as a GPU integer | Logical string asset ID; `IUnifiedBufferBatch.texture_id(handle)` resolves the numeric batch ID |
| Adopting a render-target/font/stream attachment into `Assets` | Borrow the attachment and release its owner, never the attachment separately |
| `Canvas` class usage or subclassing `Canvas2D` | `Canvas2D()` factory; annotate with `ICanvas2D` from ports |
| `Input(gamepad=...)`, `map(..., buttons=...)`, pad fields in `map_axis` | Separate `Input` keyboard action map and `Gamepad` device service |
| Implicit keyboard EventBus emission | Create `EventBus` first, then `Input(emit_to_bus=True)` and poll explicitly |
| `Input.load` / `Input.save` | Application-owned binding serialization plus `map` / `map_axis` |
| `build_physics_service` | Enable `PhysicsConfig` through `pu.init`, or inject a `PhysicsBackend` into `Physics` at the application boundary |
| `AppConfig.background_color` | Pass the application's clear color to `window.clear_background` in `App.update` |
| `SceneUnit.render_submit` | Attach a `NodeUnit` with `render_submit(renderer, context)` to the scene root |
| `Renderer.render_rect/circle/line/triangle` and their plural variants | Cached `canvas.create_*` textures + sprite submits, or queued custom Canvas drawing |

Neutral services/data now include `services/animations.py`,
`services/assets/schemas.py`, `services/spatial_index.py`, `services/text.py`,
and `services/shaders.py`. Concrete raylib services live under
`backends/integrations/raylib`; its `handler.py` defines `Image`, `Texture2D`,
`RenderTexture`, `Shader`, `Font`, and `StreamingTexture`. Game/core code uses
handle contracts from `backends.ports.handler`, not those classes' raw fields.

### Initialization and ownership

`plyunit._bootstrap.init` injects adapters and services, then calls
`app.init(cfg)` before constructing optional physics, ImGui, or audio services.
`App.init` opens the window, sets up the injected default camera, and calls
`Renderer.init()` only after a graphics context exists. The renderer
constructor does not call `ubr.init()`.

Load GPU assets and bake shapes in `on_load` / `on_ready`, after bootstrap.
`Assets.store_texture` takes ownership only of standalone root textures;
resolve the assigned asset ID again afterward. Previously captured asset
handles become stale after reload, unload, or atlas packing.
`render_target.texture`, `font.texture`, and `stream.texture` are borrowed
and must remain with their owning render target, text service, or stream.
Release owners after queued draws finish and before the window closes.

### Reusable shapes

Bake once, transfer ownership to `Assets`, then submit the cached handle each
render frame:

```python
# App.on_load, after bootstrap.
self.assets.store_texture(
    "disc",
    self.canvas.create_circle(radius=12.0, color=(255, 255, 255, 255)),
)

# App.update, after reset_frame and before flush_all.
self.renderer.render_sprite(
    texture=self.assets["disc"],
    pos=(100.0, 100.0),
    tint=(80, 200, 120, 255),
    layer=pu.Layer.ENTITIES,
)
```

For geometry whose outline changes every frame, or a debug overlay, queue a
Canvas callback instead of baking a new texture each frame:

```python
self.renderer.render_custom(
    draw_func=lambda canvas: canvas.draw_rectangle(
        rect=(20.0, 20.0, 200.0 * self.hp_ratio, 16.0),
        color=(220, 50, 50, 255),
    ),
    layer=pu.Layer.UI,
)
```

The callback draws during flush; it must not submit more renderer work.
Custom geometry does not participate in native sprite batching.

## App flow APIs removed

| Removed API | Replacement |
| --- | --- |
| `App._render_frame()` / engine-owned render pipeline | The user's `update(dt)` hook owns the whole render pipeline |
| `App.on_render(dt)` | Inline the work into `update(dt)` |
| `App.render_submit(renderer)` | Inline the submissions into `update(dt)` (after `SceneManager.render`) |
| `App.on_begin_render` / `App.on_end_render` signals | Removed — render orchestration is user-owned |
| `App.update(dt)` as a per-substep hook | `App.fixed_update(dt, step)` (per substep) + `App.update(dt)` (per frame) |
| `App.late_update`, `on_begin_late_update`, `on_end_late_update` | Removed in an earlier pass; stays removed — use `on_after_update` |
| `Component.late_update()` / `Component.late_updates` | Removed — connect to `App.on_after_update` if a component needs a post-update hook |
| `NodeUnit.late_update()` / `SceneUnit._dispatch_late_update()` | Removed |
| `SceneManager.begin_fixed_step` / `end_fixed_step` / `late_update` | `SceneManager.begin_step()` / `end_step()` (engine-owned bookkeeping) |
| ImGui auto-draw via `on_end_render` | Manual `ImGui.frame(dt)` call inside `update(dt)` |

## The new contract

During the main loop, `App` owns frame timing and fixed-step scheduling,
not drawing. Initialization still opens the window and configures the injected
camera and renderer through their ports. Two hooks define user-owned work:

```python
class GameApp(pu.App):
    def on_load(self) -> None:
        # Bootstrap already injected and set up the default camera.
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        # Deterministic simulation, once per fixed substep.
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        # Per-frame render pipeline, entirely user-owned.
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((24, 32, 48, 255))
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()
```

Frame order inside `App.run()`:

```text
_start_frame()      # window clock + on_start_frame
step_fixed()        # 0..N substeps (SceneManager.begin_step/end_step + signals)
update(dt)          # USER HOOK — once per frame
_end_frame()        # on_end_frame
```

Substep order inside `_fixed_step(dt, step)`:

```text
SceneManager.begin_step()
on_begin_update(dt)
EventBus.dispatch()
fixed_update(dt, step)          # USER HOOK — SceneManager.update/apply_pending
on_after_update(dt)
on_end_update(dt)
on_fixed_update(dt)
EventBus.dispatch()
SceneManager.end_step()
```

## Migration notes

- **`SceneManager.update`/`apply_pending` are no longer automatic.** If you
  never call `apply_pending()` inside `fixed_update`, queued scene transitions
  (`push`/`pop`/`change`) are never applied.
- **One traversal per substep.** `late_update` dispatch, its signals, and the
  second tree traversal are gone. `_flush_pending()` and
  `_clear_spawn_gates()` now run at the end of `SceneUnit._dispatch_update()`.
- **`on_after_update`** fires once per substep after `fixed_update` returns.
  Services that need a post-update hook should
  `app.on_after_update.connect(...)` in `on_attach` and disconnect in
  `on_destroy` — do not reintroduce per-node lifecycle methods.
- **Camera ownership:** `Renderer.flush_all(camera=...)` is the single owner
  of `Camera2D.start_frame()`/`end_frame()`. Never call those manually.
- **Ordering between services** is controlled either by direct calls inside
  `fixed_update`/`update` (static, load-bearing dependencies) or by
  `connect()` order on `on_after_update` (optional, plugin-style systems).

## ImGui

The service no longer wires itself to `App.on_end_render`. Call it manually
from `update(dt)`, after `flush_all` and before `end_drawing`:

```python
def update(self, dt: float) -> None:
    ...
    self.renderer.flush_all(camera=self.camera)
    imgui = self.one_or_none("@ImGui", scope="global")
    if imgui is not None:
        imgui.frame(dt)
    self.window.end_drawing()
```

## Reference

- [architecture-layers.md](architecture-layers.md)
- [architecture-hexagonal-audit.md](architecture-hexagonal-audit.md)
- [input-and-events.md](input-and-events.md)
- [rendering/queued-submit.md](rendering/queued-submit.md)
- [frame-execution-order.md](frame-execution-order.md)
- [engine-core.md](engine-core.md)
- [imgui.md](imgui.md)
