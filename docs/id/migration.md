# Migration: App flow optimization (breaking)

> **Breaking change — no compatibility path.** This migration removes
> `late_update` at every level and removes the engine-owned render pipeline
> from `App`. There is no deprecation period, no shim, and no dual-path
> support. Code that relied on the old orchestration must be rewritten, not
> patched.

## What was removed

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

`App` owns frame timing and fixed-step scheduling only. It never touches
`Camera2D`, `Renderer`, or the window drawing API. Two hooks are mandatory:

```python
class GameApp(pu.App):
    def on_load(self) -> None:
        self.camera = pu.Camera2D((320, 180), (0, 0))
        self.camera.setup(1280, 720)
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
        self.window.clear_background(self.config.background_color)
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

- [frame-execution-order.md](frame-execution-order.md)
- [engine-core.md](engine-core.md)
- [imgui.md](imgui.md)
