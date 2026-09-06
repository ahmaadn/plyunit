# ImGui (debug / tool UI)

Immediate-mode UI via **imgui-bundle**, rendered **after** the game pass, still
inside `begin_drawing` / `end_drawing`.

**Deps:** `uv sync --package plyunit --extra raylib --extra imgui` (workspace; not on PyPI)
**Example:** `uv run --package plyunit plyunit-imgui` · `examples/example_imgui.py`

## 1. Enable

```python
import plyunit as pu

app = pu.init(
    MyApp(),
    pu.AppConfig(
        title="Debug UI",
        imgui=pu.ImGuiConfig(
            enabled=True,
            dark_style=True,
            no_ini=True,  # no imgui.ini
        ),
    ),
)
app.run()
```

Bootstrap calls `build_imgui_service` → registry retention → backend setup.

## 2. Draw callbacks

```python
from imgui_bundle import imgui


class MyApp(pu.App):
    def on_load(self) -> None:
        ui = self.one("@ImGui", scope="global")
        ui.add_draw(self._draw_ui)
        # ui.set_draw(only_one_callback)
        # ui.remove_draw(cb) / clear_draw()

    def _draw_ui(self) -> None:
        imgui.begin("Debug")
        imgui.text(f"FPS: {imgui.get_io().framerate:.1f}")
        if imgui.button("Reset"):
            self._reset()
        imgui.end()
        imgui.show_demo_window()  # optional
```

### When it is called

`App` no longer owns a render pipeline — the user calls `ImGui.frame()`
manually from `App.update(dt)`, after `flush_all` and before `end_drawing`:

```
SceneManager.render → ...app submissions... → renderer.flush_all
ImGui.frame(dt)   # NewFrame → user draw callbacks → Render
end_drawing
```

`frame(dt)` accepts the frame delta; without an argument it falls back to
`app.window.dt`.

ImGui is **not** part of the scene tree / render queue.

## 3. `ImGui` service API

| Method | Meaning |
| --- | --- |
| `frame(dt=None)` | One ImGui frame: NewFrame → callbacks → Render |
| `add_draw(cb)` | Add a `() -> None` callback |
| `remove_draw(cb)` | Remove one |
| `set_draw(cb)` | Replace with a single callback |
| `clear_draw()` | Clear all |
| `want_capture_mouse()` | UI is consuming the mouse |
| `want_capture_keyboard()` | UI is consuming the keyboard |
| `backend` | `ImGuiBackend` |

## 4. Game content + ImGui

Queued world content still goes through `update(dt)` / scenes:

```python
def update(self, dt: float) -> None:
    self.renderer.reset_frame()
    self.window.begin_drawing()
    self.window.clear_background(self.config.background_color)
    self.scene_manager.render(self.renderer)
    self.renderer.render_rect(
        z=0,
        layer=pu.Layer.WORLD,
        rect=(80, 80, 160, 100),
        color=(70, 110, 180, 255),
    )
    self.renderer.flush_all()
    self.one("@ImGui").frame(dt)
    self.window.end_drawing()
```

The ImGui panel renders on top inside `_draw_ui`.

## 5. Input gating

```python
def fixed_update(self, dt: float, step: int) -> None:
    ui = self.one_or_none("@ImGui", scope="global")
    if ui is not None and ui.want_capture_keyboard():
        return
    # game input...
    self.scene_manager.update(dt)
    self.scene_manager.apply_pending()
```

Without the gate, UI clicks also trigger game actions.

## 6. Gotchas

| Issue | Fix |
| --- | --- |
| ImportError imgui | Install the `imgui` + `raylib` extras |
| Blank UI | `enabled=True` + `add_draw` in `on_load` + call `frame()` in `update` |
| UI behind the game | Call `frame()` after `flush_all`, before `end_drawing` |
| Persisting layout | `no_ini=False` if you want `imgui.ini` |
| Using it as a production HUD | Fine for tools; for HUDs use typed `render_*` on `Layer.UI` |

## 7. When to use ImGui vs typed UI rendering

| ImGui | `render_*` with `Layer.UI` |
| --- | --- |
| Debug panels, editors, demos | HUDs, in-engine menus |
| Immediate, flexible widgets | Batched, consistent with the render queue |
| Extra dependency | Core renderer |

## 8. See also

- [immediate-rendering.md](immediate-rendering.md) (DrawScope ≠ ImGui)
- [input-and-events.md](input-and-events.md)
- [rendering/queued-submit.md](rendering/queued-submit.md)
