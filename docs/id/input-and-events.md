# Input and EventBus

Two input paths: **polling** (directly in `fixed_update`) and **events** (EventBus + dual drain).

**Contoh:** `plyunit-example --input`, `--event-bus-input`, `--gamepad`
**Services (opt-in in `on_load`):** `Input`, `Mouse`, `Gamepad`, `Touch`

`Input` is a keyboard action map. `Gamepad` is a separate device service;
combine their values in gameplay code. Neutral code types against `IInput`,
`IMouse`, `IGamepad`, and `ITouch` in `plyunit.backends.ports.input`, while
the root facade selects concrete adapters.

## 1. Poll path (sederhana)

```python
import pyray as pr
import plyunit as pu


class GameApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()  # keyboard polling; events are disabled by default
        self.pad = pu.Gamepad(player=0)
        self.mouse = pu.Mouse()
        self.input.map("jump", pr.KeyboardKey.KEY_SPACE)
        self.input.map_axis(
            "move_x",
            key_neg=[pr.KeyboardKey.KEY_A, pr.KeyboardKey.KEY_LEFT],
            key_pos=[pr.KeyboardKey.KEY_D, pr.KeyboardKey.KEY_RIGHT],
        )
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        if self.input.is_pressed("jump") or self.pad.is_pressed("a"):
            ...
        keyboard_x = self.input.get_axis("move_x")
        pad_x = self.pad.get_axis("left_x")
        self.move_x = pad_x if abs(pad_x) > abs(keyboard_x) else keyboard_x
        if self.mouse.is_pressed("left"):
            x, y = self.mouse.position
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()
```

### Input API (ringkas)

| Method | Arti |
| --- | --- |
| `Input(emit_to_bus=False)` | Keyboard action map; no gamepad attachment |
| `map(action, *keys)` / `unmap(action, *keys)` | Bind/unbind keyboard key codes |
| `map_axis(name, key_neg=…, key_pos=…)` | Digital keyboard axis |
| `is_pressed` / `is_down` / `is_released` | Keyboard edge / level |
| `get_axis(left, right)` / `get_axis("move_x")` | Two actions **or** a named keyboard axis |
| `get_vector("move_x", "move_y")` | Pair of named keyboard axes |
| `Input(emit_to_bus=True)` | Opt in to `key.{action}.*`; explicitly poll `update(dt)` |

`pu.Input` has no `Keyboard` alias, `gamepad=` option, pad binding fields,
or built-in `load` / `save` API. Binding persistence belongs to the application.

### Mouse API (ringkas)

| Method | Arti |
| --- | --- |
| `position`, `x`, `y`, `movement` | Cursor |
| `is_pressed/down/released(button)` | `"left"`, `"right"`, … |

### Gamepad (device service)

Poll-only, constructed separately: `pu.Gamepad(player=0)`. It does not emit
keyboard action events or enter the `Input` action map.

| Method | Arti |
| --- | --- |
| `is_available()` / `name_on_device` | Connection |
| `is_pressed/down/released("a")` | Button aliases |
| `get_axis` / `get_vector` | Deadzone default 0.15 |
| `set_vibration` | Best-effort rumble |

Aliases: `a/b/x/y`, `lb/rb/lt/rt`, `dpad_*`, `start/select/guide`.
Axes: `left_x/y`, `right_x/y`, `left_trigger`, `right_trigger`.

### Touch (minimal)

| Method | Arti |
| --- | --- |
| `count`, `position` | Primary point |
| `is_down` / `is_pressed` / `is_released` | Edges from previous frame |

Query: `one("@Input")`, `@Mouse`, `@Gamepad`, `@Touch`.

## 2. EventBus path

EventBus **tidak** di-bootstrap otomatis — tambahkan sendiri:

```python
class GameApp(pu.App):
    def on_load(self) -> None:
        self.bus = pu.EventBus()  # create before the input services attach
        self.input = pu.Input(emit_to_bus=True)
        self.mouse = pu.Mouse()
        self.input.map("jump", pr.KeyboardKey.KEY_SPACE)

        self.bus.subscribe("key.jump.pressed", self._on_jump, priority=10)
        self.bus.subscribe("mouse.left.pressed", self._on_click)
        self.on_begin_update.connect(self._poll_input)

    def _poll_input(self, dt: float) -> None:
        self.input.update(dt)
        self.mouse.update(dt)

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def _on_jump(self, **kwargs) -> None:
        action = kwargs.get("action")
        ...

    def _on_click(self, **kwargs) -> None:
        position = kwargs.get("position")
        ...
```

### EventBus API

```python
bus.subscribe(event_name, listener, *, priority=0)
bus.unsubscribe(event_name, listener)
bus.publish(event_name, *args, **kwargs)   # immediate
bus.defer(event_name, *args, **kwargs)     # queue
bus.dispatch()                             # App calls this twice per fixed step
bus.has_listeners(event_name)
bus.clear_queue()
```

### Event names

| Pattern | Contoh | Source |
| --- | --- | --- |
| `key.{action}.pressed` | `key.jump.pressed` | Input (keyboard actions only) |
| `key.{action}.down` / `.released` / `.repeat` | | Input |
| `mouse.{button}.pressed` | `mouse.left.pressed` | Mouse |
| `touch.pressed` / `.down` / `.released` | | Touch |

Payload tipikal: `action=`, `device=`, `position=` (mouse/touch).

Events hanya di-`defer` jika ada listener (`has_listeners` gate).

## 3. Dual drain (penting)

Per **fixed step** (`App._fixed_step`):

```
SceneManager.begin_step()
on_begin_update(dt)             # explicitly connected Input/Mouse/Touch polling
EventBus.dispatch()             # EARLY: input available before gameplay
App.fixed_update(dt, step)      # user hook
  SceneManager.update(dt)       # tree update + transform/spatial sync
  SceneManager.apply_pending()  # user applies queued scene transitions
on_after_update(dt)
on_end_update(dt)
on_fixed_update(dt)             # physics/timer/tween services
EventBus.dispatch()             # LATE: deferred gameplay/physics events
SceneManager.end_step()
```

| Drain | Kapan | Untuk |
| --- | --- | --- |
| Early | Setelah input poll | Reaksi input frame yang sama |
| Late | Setelah physics | Event gameplay / post-collision |

`publish` = immediate and synchronous (avoid in large hot paths).
`defer` + drain = frame-order safe.

Services do not connect their polling methods automatically. The example
connects `_poll_input` before the early drain; polling inside `fixed_update`
queues events for the late drain instead. Do not poll in both places.
The raylib services cache the bus at attachment and disable emission if none
is present, so create `EventBus` before event-enabled input services.

## 4. Signals (decorator)

Selain EventBus string topics, unit punya **Signal** + `@on`:

```python
from plyunit import on


class MyService(pu.ServiceUnit):
    @on("@App", event="on_begin_update")
    def _poll(self, dt: float) -> None: ...
```

Wiring happens automatically for **declared** `@on` bindings when a service
attaches (see `wire_bindings`). This does not automatically wire `Input.update`,
`Mouse.update`, or `Touch.update`; connect the polling phase yourself.

## 5. ImGui capture

Saat ImGui aktif, cek sebelum input game:

```python
imgui = self.one_or_none("@ImGui", scope="global")
if imgui is not None and imgui.want_capture_keyboard():
    return  # jangan proses game keys
if imgui is not None and imgui.want_capture_mouse():
    return
```

[imgui.md](imgui.md).

## 6. One-shot input vs fixed catch-up

Under lag, `App` may run **2–`max_substeps_per_frame`** fixed steps in one wall-clock frame. Raylib `Is*Pressed` latches for the whole frame, so unguarded edge polls in scene/node `update` or `App.fixed_update` can multi-fire (e.g. 1 click → N spawns). `App.update` runs only once per wall-clock frame.

| API | Policy |
| --- | --- |
| `Input` / `Mouse` / `Gamepad` / `Touch` edges | **First fixed substep only** (`App.is_first_fixed_step`) |
| EventBus `*.pressed` / `*.released` / `*.repeat` | Same (via service edges) |
| `is_down` / `is_up` / EventBus `*.down` | **Every** fixed substep (hold movement) |
| Raw `pr.is_*_pressed` in scene `update` | Still multi-fires — guard with `app.is_first_fixed_step` or use services |

```python
def update(self, dt: float) -> None:
    # Continuous sim always runs...
    self._move_player(dt)

    # One-shot: service (auto-gated) or raw + guard
    if self.input.is_pressed("jump"):
        self._jump()
    app = self.one("@App", scope="global")
    if app.is_first_fixed_step and pr.is_key_pressed(pr.KEY_R):
        self._reset()
```

Frames with **0** fixed steps (high FPS / low accumulator) still skip edges — pre-existing behavior.

## 7. Gotchas

| Issue | Fix |
| --- | --- |
| Keyboard events never arrive | Create the bus first, use `Input(emit_to_bus=True)`, subscribe, and poll `Input.update(dt)` |
| No early drain | Register `@EventBus` and poll from `on_begin_update` |
| Two Input services | Unique service — a second instance can conflict on name |
| Poll di render | Boleh, tapi fixed logic di `fixed_update` |
| `publish` re-entrancy | Prefer `defer` untuk efek berantai |
| One-shot multi-fires under lag | Use services **or** `app.is_first_fixed_step` for raw pyray |
| Persisted bindings | Application-owned JSON parsing; bind with `map` / `map_axis` |

## 8. Pola rekomendasi

| Use case | Jalur |
| --- | --- |
| Multi-device movement | Separate `Input.get_axis` and `Gamepad.get_axis`; combine in gameplay |
| Jump on KB + pad | `input.is_pressed("jump") or pad.is_pressed("a")` |
| Pad-only poll | `Gamepad` device service |
| Raw pyray one-shot | Gate with `app.is_first_fixed_step` |
| UI debug | ImGui + want_capture_* |
| Gameplay systems decoupled | EventBus late + custom topics `game.player.died` |

### Application-owned binding JSON

`Input` does not parse or save files. If the game persists keyboard bindings,
use its own data format, for example:

```json
{
  "actions": {
    "jump": [32]
  },
  "axes": {
    "move_x": {
      "key_neg": [65, 263],
      "key_pos": [68, 262]
    }
  }
}
```

Apply it through the keyboard APIs:

```python
import json
from pathlib import Path

bindings = json.loads(Path("data/input.json").read_text(encoding="utf-8"))
for action, keys in bindings["actions"].items():
    self.input.map(action, *keys)
for name, axis in bindings["axes"].items():
    self.input.map_axis(name, key_neg=axis["key_neg"], key_pos=axis["key_pos"])
```

Validate persisted data in the application. This is an example format, not
an engine schema; gamepad button/axis policy stays separate.
