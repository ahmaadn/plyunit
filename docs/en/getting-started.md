# Getting started

How to set up plyunit and create a new game project.

plyunit is **not published to PyPI** — install it from the repository.

## 1. Requirements

- **[uv](https://docs.astral.sh/uv/)** (package/dependency manager)
- Python **≥ 3.13**
- A **C compiler** for the native sprite-batching extension
  (`plyunit._plyunit_batch`): MSVC Build Tools **or** MinGW-w64
  (`gcc` on `PATH`, e.g. [MSYS2](https://www.msys2.org/))
- For 2D raylib games: the **raylib** extra (window + Canvas + Renderer) —
  included by the setup below

## 2. Install

Clone the repository and run the bootstrap script:

```bash
git clone https://github.com/ahmaadn/plyunit.git
cd plyunit
./init.sh
```

`init.sh` runs `uv sync` (installs `plyunit[all]` + dev group, compiles the
native C extension — MinGW gcc is picked automatically when MSVC is absent)
and verifies the install (`./verify.sh` re-checks at any time).

Equivalent commands without bash:

```bash
uv sync
uv run python scripts/verify_install.py
```

Extras (already covered by the root setup; shown for `--package` usage):

```bash
uv sync --package plyunit --extra all   # raylib + physics + imgui + native
```

Base dependency: `numpy`. Host backends (raylib, pymunk, imgui) are **optional** via extras.

## 3. Create a new project

Scaffold a project inside the workspace at `projects/<name>`:

```bash
./new_project.sh my_project
uv run python projects/my_project/main.py
```

This creates a runnable skeleton — a virtual uv workspace member depending
on `plyunit[raylib,native]` (engine edits apply immediately). All Python
scripts live in `scripts/`:

```
projects/my_project/
  main.py                 # entrypoint — run with uv from repo root
  scripts/                # all Python scripts here (main_scene.py, player.py, …)
  data/                   # assets
  pyproject.toml
```

Isolated plyunit setup — embed a copy of the engine (source + built C
extension) so the project runs against its own plyunit, insulated from
workspace engine changes:

```bash
./new_project.sh my_project --isolated
```

```
projects/my_project/
  main.py                 # entrypoint — prefers scripts/plyunit at runtime
  scripts/                # all Python scripts here
  scripts/plyunit/        # isolated plyunit engine copy (+ .pyd/.so)
  data/                   # assets
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

### Mandatory order

1. Subclass `App` / `SceneUnit` (optional but recommended)
2. **`init(app, AppConfig)`** — window, renderer, services
3. In `App.on_load`: push scene, map input, register callbacks
4. **`app.run()`** — `on_load`, main loop, then teardown
5. `App.on_unload()` — application cleanup before services and the window close

Do not call `app.run()` before bootstrap.

`App.run()` owns frame timing and fixed-step scheduling. Implement
`fixed_update(dt, step)` for deterministic simulation (call
`SceneManager.update`/`apply_pending` there) and `update(dt)` for the
per-frame render pipeline — the engine never renders on its own. Use
`app.quit()` to stop the loop without `sys.exit()`.

## 5. Important AppConfig fields

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

| Field | Meaning |
| --- | --- |
| `target_fps` | Frame cap (raylib); 0 = unlimited |
| `fixed_update_hz` | Fixed timestep for gameplay/physics |
| `max_substeps_per_frame` | Clamps the spiral of death |
| `physics.enabled` | Auto `Physics` + step inside `on_fixed_update` |
| `imgui.enabled` | Auto `ImGui` service; draw via `ImGui.frame()` |

## 6. Recommended folder structure

The `new_project.sh` scaffold (see [3. Create a new project](#3-create-a-new-project)) — standard:

```
projects/my_project/
  main.py                 # entrypoint — run with uv from repo root
  scripts/                # all Python scripts here
    main_scene.py         # SceneUnit classes
    player.py             # NodeUnit subclasses, components, helpers
  data/                   # assets
    images/
    maps/
  pyproject.toml          # virtual workspace member; deps: plyunit[raylib,native]
```

Isolated plyunit setup (`./new_project.sh my_project --isolated`) additionally
embeds the engine inside `scripts/`:

```
projects/my_project/
  main.py                 # entrypoint — prefers scripts/plyunit at runtime
  scripts/                # all Python scripts here
    plyunit/              # isolated plyunit engine copy (source + .pyd/.so)
  data/                   # assets
  pyproject.toml
```

The same per-topic layout (scenes/units as scripts) is used in `examples/`
(monorepo root). Run: `uv run plyunit-example --list`.

## 7. Scenes & tree

```python
class MainScene(pu.SceneUnit):
    def on_load(self) -> None:
        # called once when the scene enters the stack (load)
        hero = Player()
        self.root.attach(hero)

    def on_unload(self) -> None:
        # optional cleanup; the tree is destroyed by the engine
        pass
```

- `SceneUnit.root` is the root `NodeUnit`.
- `attach` / `detach` manage parent + TransformStore (in-scene reparent is in-place).
- Node lifecycle: `on_enter_tree` → `on_ready` (once) → per-frame `update` / `render_submit`.

## 8. First sprite

```python
from plyunit.core.components.builtin import SpriteRenderer

node = pu.NodeUnit(name="Coin")
node.transform.set_position(200.0, 160.0)
node.add_component(
    SpriteRenderer(
        texture=texture,  # raylib Texture / from Assets
        layer=int(pu.Layer.ENTITIES),
        z_index=0,
    )
)
scene.root.attach(node)
```

See [node-rendering-guide.md](node-rendering-guide.md) and [rendering/index.md](rendering/index.md).

## 9. Quick input (poll)

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

Do not call `Physics.step` manually when it is already bootstrapped.
Guide: [physics.md](physics.md). Example: `uv run --package plyunit plyunit-physics`.

## 11. ImGui debug UI

```python
pu.AppConfig(imgui=pu.ImGuiConfig(enabled=True))
# in on_load:
self.one("@ImGui").add_draw(self._draw_ui)
# in update(dt), after flush_all and before end_drawing:
self.one("@ImGui").frame(dt)
```

[imgui.md](imgui.md) · CLI: `plyunit-imgui`.

## 12. New project checklist

- [ ] `init` + `AppConfig`
- [ ] One `SceneUnit` pushed in `on_load`
- [ ] Nodes `attach`ed to `scene.root`
- [ ] Transforms via `set_position` / `set_rotation` / `set_scale`
- [ ] Sprites via `SpriteRenderer` or `render_batch` (no arbitrary `draw`)
- [ ] Physics/ImGui only when needed, via config
- [ ] No double-stepping physics
- [ ] Follow [naming-convention.md](naming-convention.md)

## 13. Next steps

| Topic | Document |
| --- | --- |
| How the engine works | [engine-core.md](engine-core.md) |
| Frame order | [frame-execution-order.md](frame-execution-order.md) |
| Rendering | [rendering/index.md](rendering/index.md) |
| Examples CLI | [examples-and-cli.md](examples-and-cli.md) |
