# plyunit Cheatsheet

## Bootstrap

```python
app = pu.init(MyApp(), pu.AppConfig(title="G", physics=..., imgui=..., audio=...))
app.run()
```

## App Hooks

```python
class MyApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)  # simulation (mandatory)
        self.scene_manager.apply_pending()  # scene transitions (mandatory)

    def update(self, dt: float) -> None:
        if self.camera is not None:
            self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()
```

`App.run()` owns frame timing and `step_fixed()` only — the render pipeline
belongs to `update(dt)`. Call `app.quit()` for a clean stop.

## Fixed Step

```text
begin_step
begin_update → EventBus EARLY
fixed_update (user) → SceneManager.update → transform sync → apply_pending (user)
on_after_update
end_update
on_fixed_update → Physics/Tween/Timers
EventBus LATE
end_step
```

## Stats

```python
renderer.profile_enabled = True
scene.profile_enabled = True
spatial = SpatialIndex(stats_enabled=True)
app.fixed_step_count
```

Details: [observability/stats.md](observability/stats.md).

## Queries

```python
self.one("@Physics", scope="global")
self.one("Player", scope="scene")
self.group("#enemy", scope="scene")
```

## Deferred Scene Transitions

```python
self.scene_manager.push(scene)
self.scene_manager.change(scene)
self.scene_manager.request_change(lambda: LevelScene())
```

## Rendering

```python
renderer.render_sprite(...)
renderer.render_batch(...)    # same texture, N positions
renderer.render_sprites(...)      # N textures, N positions
renderer.render_rect(...)       # deprecated → canvas.create_rect + render_sprite
renderer.render_custom(...)
```
