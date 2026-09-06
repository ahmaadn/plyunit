# Getting started

Cara memasang plyunit dan membuat proyek game baru.

plyunit **belum dipublikasikan ke PyPI** — pasang dari repositorinya.

## 1. Requirements

- **[uv](https://docs.astral.sh/uv/)** (manajer package/dependency)
- Python **≥ 3.13**
- **Compiler C** untuk ekstensi native sprite-batching
  (`plyunit._plyunit_batch`): MSVC Build Tools **atau** MinGW-w64
  (`gcc` di `PATH`, mis. [MSYS2](https://www.msys2.org/))
- Untuk game 2D raylib: extra **raylib** (window + Canvas + Renderer) —
  sudah termasuk dalam setup di bawah

## 2. Install

Clone repositori lalu jalankan script bootstrap:

```bash
git clone https://github.com/ahmaadn/plyunit.git
cd plyunit
./init.sh
```

`init.sh` menjalankan `uv sync` (memasang `plyunit[all]` + dev group,
mengompilasi ekstensi native C — gcc MinGW dipilih otomatis saat MSVC tidak
ada) lalu memverifikasi instalasi (`./verify.sh` untuk cek ulang kapan saja).

Perintah setara tanpa bash:

```bash
uv sync
uv run python scripts/verify_install.py
```

Extras (sudah tercakup oleh setup root; ditampilkan untuk pemakaian `--package`):

```bash
uv sync --package plyunit --extra all   # raylib + physics + imgui + native
```

Base dependency: `numpy`. Host backends (raylib, pymunk, imgui) **opsional** via extras.

## 3. Membuat proyek baru

Scaffold proyek baru di dalam workspace pada `projects/<name>`:

```bash
./new_project.sh my_project
uv run python projects/my_project/main.py
```

Ini membuat kerangka yang langsung bisa dijalankan — virtual uv workspace
member yang bergantung pada `plyunit[raylib,native]` (perubahan engine
langsung terpakai). Semua script Python berada di `scripts/`:

```
projects/my_project/
  main.py                 # entrypoint — dijalankan dengan uv dari root repo
  scripts/                # semua script Python di sini (main_scene.py, player.py, …)
  data/                   # aset
  pyproject.toml
```

Isolated plyunit setup — sematkan salinan engine (source + C extension hasil
build) agar proyek berjalan dengan plyunit-nya sendiri, terisolasi dari
perubahan engine di workspace:

```bash
./new_project.sh my_project --isolated
```

```
projects/my_project/
  main.py                 # entrypoint — memakai scripts/plyunit saat runtime
  scripts/                # semua script Python di sini
  scripts/plyunit/        # salinan engine plyunit terisolasi (+ .pyd/.so)
  data/                   # aset
  pyproject.toml
```

## 4. Minimal game

```python
import plyunit as pu


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__(name="Main")

    def on_load(self) -> None:
        player = pu.NodeUnit(name="Player")
        player.transform.set_position(100.0, 100.0)
        self.root.attach(player)

    def update(self, dt: float) -> None:
        _ = dt  # scene-level logic optional


class GameApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        # Simulation: drive the scene tree every fixed substep.
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        # Per-frame render pipeline (fully user-owned).
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        GameApp(),
        pu.AppConfig(
            title="My Game",
            window_width=1280,
            window_height=720,
            target_fps=60,
            fixed_update_hz=60,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
```

### Urutan wajib

1. Subclass `App` / `SceneUnit` (opsional tapi disarankan)
2. **`init(app, AppConfig)`** — window, renderer, services
3. Di `App.on_load`: push scene, map input, daftar callback
4. **`app.run()`** — `on_load`, main loop, lalu teardown
5. `App.on_unload()` — cleanup aplikasi sebelum services dan window ditutup

Jangan `app.run()` sebelum bootstrap.

`App.run()` owns frame timing and fixed-step scheduling. Implement
`fixed_update(dt, step)` for deterministic simulation (call
`SceneManager.update`/`apply_pending` there) and `update(dt)` for the
per-frame render pipeline — the engine never renders on its own. Use
`app.quit()` to stop the loop without `sys.exit()`.

## 5. AppConfig penting

```python
pu.AppConfig(
    title="My Game",
    window_width=1280,
    window_height=720,
    target_fps=60,  # 0 = uncapped
    fixed_update_hz=60,
    max_frame_delta_time=0.25,
    max_substeps_per_frame=5,
    background_color=(245, 245, 245, 255),
    log_level="INFO",
    physics=pu.PhysicsConfig(enabled=False, gravity=(0.0, 900.0)),
    imgui=pu.ImGuiConfig(enabled=False, dark_style=True, no_ini=True),
)
```

| Field | Arti |
| --- | --- |
| `target_fps` | Cap frame (raylib); 0 = unlimited |
| `fixed_update_hz` | Fixed timestep gameplay/physics |
| `max_substeps_per_frame` | Clamp spiral-of-death |
| `physics.enabled` | Auto `Physics` + step di `on_fixed_update` |
| `imgui.enabled` | Auto `ImGui` service; draw via `ImGui.frame()` |

## 6. Struktur folder disarankan

Scaffold dari `new_project.sh` (lihat [3. Membuat proyek baru](#3-membuat-proyek-baru)) — standard:

```
projects/my_project/
  main.py                 # entrypoint — dijalankan dengan uv dari root repo
  scripts/                # semua script Python di sini
    main_scene.py         # class SceneUnit
    player.py             # subclass NodeUnit, komponen, helper
  data/                   # aset
    images/
    maps/
  pyproject.toml          # virtual workspace member; deps: plyunit[raylib,native]
```

Isolated plyunit setup (`./new_project.sh my_project --isolated`) juga
menyematkan engine di dalam `scripts/`:

```
projects/my_project/
  main.py                 # entrypoint — memakai scripts/plyunit saat runtime
  scripts/                # semua script Python di sini
    plyunit/              # salinan engine plyunit terisolasi (source + .pyd/.so)
  data/                   # aset
  pyproject.toml
```

Layout per-topik yang sama (scene/unit sebagai script) dipakai di `examples/`
(root monorepo). Run: `uv run plyunit-example --list`.

## 7. Scene & tree

```python
class MainScene(pu.SceneUnit):
    def on_load(self) -> None:
        # dipanggil sekali saat scene masuk stack (load)
        hero = Player()
        self.root.attach(hero)

    def on_unload(self) -> None:
        # cleanup opsional; tree di-destroy oleh engine
        pass
```

- `SceneUnit.root` adalah `NodeUnit` root.
- `attach` / `detach` mengelola parent + TransformStore (in-scene reparent in-place).
- Lifecycle node: `on_enter_tree` → `on_ready` (sekali) → per-frame `update` / `render_submit`.

## 8. Sprite pertama

```python
from plyunit.core.components.builtin import SpriteRenderer

node = pu.NodeUnit(name="Coin")
node.transform.set_position(200.0, 160.0)
node.add_component(
    SpriteRenderer(
        texture=texture,  # raylib Texture / dari Assets
        layer=int(pu.Layer.ENTITIES),
        z_index=0,
    )
)
scene.root.attach(node)
```

Lihat [node-rendering-guide.md](node-rendering-guide.md) dan [rendering/index.md](rendering/index.md).

## 9. Input cepat (poll)

```python
import pyray as pr


class GameApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()  # service name "@Input"
        self.input.map("jump", pr.KEY_SPACE)
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        # is_pressed is once per wall-clock frame (first fixed substep under lag).
        if self.input.is_pressed("jump"):
            ...
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()
```

Event-driven: [input-and-events.md](input-and-events.md).

## 10. Physics opt-in

```python
app = pu.init(
    GameApp(),
    pu.AppConfig(
        physics=pu.PhysicsConfig(enabled=True, gravity=(0.0, 900.0)),
    ),
)
```

Jangan panggil `Physics.step` manual jika sudah di-bootstrap.
Panduan: [physics.md](physics.md). Contoh: `uv run --package plyunit plyunit-physics`.

## 11. ImGui debug UI

```python
pu.AppConfig(imgui=pu.ImGuiConfig(enabled=True))
# in on_load:
self.one("@ImGui").add_draw(self._draw_ui)
# in update(dt), after flush_all and before end_drawing:
self.one("@ImGui").frame(dt)
```

[imgui.md](imgui.md) · CLI: `plyunit-imgui`.

## 12. Checklist proyek baru

- [ ] `init` + `AppConfig`
- [ ] Satu `SceneUnit` di-push di `on_load`
- [ ] Node di-`attach` ke `scene.root`
- [ ] Transform lewat `set_position` / `set_rotation` / `set_scale`
- [ ] Sprite lewat `SpriteRenderer` atau `render_batch` (bukan `draw` sembarangan)
- [ ] Physics/ImGui hanya jika needed via config
- [ ] Tidak double-step physics
- [ ] Ikuti [naming-convention.md](naming-convention.md)

## 13. Lanjut

| Topik | Dokumen |
| --- | --- |
| Cara kerja engine | [engine-core.md](engine-core.md) |
| Urutan frame | [frame-execution-order.md](frame-execution-order.md) |
| Render | [rendering/index.md](rendering/index.md) |
| Examples CLI | [examples-and-cli.md](examples-and-cli.md) |
