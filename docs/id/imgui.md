# ImGui (debug / tool UI)

Immediate-mode UI via **imgui-bundle**, di-render **setelah** pass game, masih di dalam `begin_drawing` / `end_drawing`.

**Deps:** `uv sync --package plyunit --extra raylib --extra imgui` (workspace; belum di PyPI)
**Contoh:** `uv run --package plyunit plyunit-imgui` · `examples/example_imgui.py`

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

Bootstrap memanggil `build_imgui_service` → registry retention → backend setup.

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

### Kapan dipanggil

`App` tidak lagi memiliki pipeline render — user memanggil `ImGui.frame()`
manual dari `App.update(dt)`, setelah `flush_all` dan sebelum `end_drawing`:

```
SceneManager.render → ...app submissions... → renderer.flush_all
ImGui.frame(dt)   # NewFrame → user draw callbacks → Render
end_drawing
```

`frame(dt)` menerima delta frame; tanpa argumen ia fallback ke
`app.window.dt`.

ImGui **bukan** bagian scene tree / render queue.

## 3. API service `ImGui`

| Method | Arti |
| --- | --- |
| `frame(dt=None)` | Satu frame ImGui: NewFrame → callbacks → Render |
| `add_draw(cb)` | Tambah callback `() -> None` |
| `remove_draw(cb)` | Hapus |
| `set_draw(cb)` | Ganti single callback |
| `clear_draw()` | Kosongkan |
| `want_capture_mouse()` | UI makan mouse |
| `want_capture_keyboard()` | UI makan keyboard |
| `backend` | `ImGuiBackend` |

## 4. Game content + ImGui

Queued world tetap lewat `update(dt)` / scene:

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

ImGui panel di atasnya di `_draw_ui`.

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

Tanpa gate, klik UI juga memicu game actions.

## 6. Gotchas

| Issue | Fix |
| --- | --- |
| ImportError imgui | Install extra `imgui` + `raylib` |
| Blank UI | `enabled=True` + `add_draw` di `on_load` + panggil `frame()` di `update` |
| UI di belakang game | Panggil `frame()` setelah `flush_all`, sebelum `end_drawing` |
| Menyimpan layout | `no_ini=False` jika ingin `imgui.ini` |
| Pakai untuk HUD production | Boleh untuk tools; untuk HUD gunakan typed `render_*` pada `Layer.UI` |

## 7. Kapan ImGui vs typed UI rendering

| ImGui | `render_*` dengan `Layer.UI` |
| --- | --- |
| Debug panels, editors, demos | HUD, menus in-engine |
| Immediate, flexible widgets | Batched, konsisten dengan render queue |
| Extra dependency | Core renderer |

## 8. Lihat juga

- [immediate-rendering.md](immediate-rendering.md) (DrawScope ≠ ImGui)
- [input-and-events.md](input-and-events.md)
- [rendering/queued-submit.md](rendering/queued-submit.md)
