# Frame Execution Order

`App` owns frame timing and fixed-step scheduling only. Application subclasses
implement two mandatory hooks — `fixed_update(dt, step)` for deterministic
simulation and `update(dt)` for per-frame work (typically the whole render
pipeline). The engine guarantees when a hook or signal fires, never what
happens inside it.

> Index: [index.md](index.md) | Core: [engine-core.md](engine-core.md)
> | Migration: [migration.md](migration.md)

## Wall-Clock Frame

```text
_start_frame()       # window clock and on_start_frame
step_fixed()         # zero or more fixed simulation steps
update(dt)           # USER HOOK — once per frame, render pipeline lives here
_end_frame()         # on_end_frame
```

`App.update(dt)` receives the scaled frame delta (`window.dt`). There is no
engine-owned render pass: if the user's `update()` does not draw, nothing is
drawn.

## Fixed Step

```text
SceneManager.begin_step()
on_begin_update(dt)
EventBus.dispatch()              # early input events
App.fixed_update(dt, step)       # USER HOOK — mandatory
  SceneManager.update(dt)        # called by the USER
  SceneManager.apply_pending()   # called by the USER (scene transitions)
on_after_update(dt)
on_end_update(dt)
on_fixed_update(dt)              # physics, tween, and timer services
EventBus.dispatch()              # late gameplay events
SceneManager.end_step()
```

`SceneManager.update(dt)` and `SceneManager.apply_pending()` are never called
by the engine. If the user never calls `apply_pending()`, queued scene
transitions (`push`/`pop`) are simply never applied.

### Tree Mutation Rules

| Rule | Behavior |
| --- | --- |
| Attach during a step | Immediate hierarchy/registry entry, but first update is the next fixed step |
| Attach during scene load | No gate; updates on the first fixed step |
| Detach/destroy during scene update | Hidden immediately and structurally removed by the end-of-update flush |
| Pending housekeeping | `_flush_pending()` and `_clear_spawn_gates()` run after transform/spatial synchronization |

## Render Frame (user-owned)

The canonical `update(dt)` implementation:

```text
camera.update(window.unscaled_dt)
renderer.reset_frame()
window.begin_drawing()
window.clear_background(config.background_color)
SceneManager.render(renderer)     # scene tree submission
...app-level submissions...
renderer.flush_all(camera)        # single owner of camera start_frame/end_frame
ImGui.frame(dt)                   # optional, when imgui is enabled
window.end_drawing()
```

`Renderer.flush_all()` exclusively owns camera `start_frame()` and
`end_frame()` calls.

## Input and Event Drains

`step_fixed()` may run zero to `max_substeps_per_frame` times. One-shot input
is gated by `App.is_first_fixed_step`. Poll input from `on_begin_update` when
deferred input events must be available to the early EventBus drain.
