# Input and EventBus

Two input paths: **polling** (directly in `update`) and **events** (EventBus + dual drain).

**Examples:** `plyunit-example --input`, `--event-bus-input`, `--gamepad`
**Services (opt-in in `on_load`):** `Input`, `Mouse`, `Gamepad`, `Touch`

## 1. Poll path (simple)

```python
import pyray as pr
import plyunit as pu


class GameApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input(gamepad=True)  # KB + pad; service "@Input"
        self.mouse = pu.Mouse()
        self.input.map("jump", pr.KEY_SPACE, buttons=["a"])
        self.input.map_axis(
            "move_x",
            key_neg=[pr.KEY_A, pr.KEY_LEFT],
            key_pos=[pr.KEY_D, pr.KEY_RIGHT],
            pad_axis="left_x",
            pad_buttons_neg=["dpad_left"],
            pad_buttons_pos=["dpad_right"],
        )
        self.scene_manager.push(MainScene())

    def update(self, dt: float) -> None:
        if self.input.is_pressed("jump"):
            ...
        dx = self.input.get_axis("move_x")  # named axis from map_axis
        # or two actions: self.input.get_axis("left", "right")
        if self.mouse.is_pressed("left"):
            x, y = self.mouse.position
```

### Input API (summary)

| Method | Meaning |
| --- | --- |
| `Input(gamepad=True\|0\|Gamepad)` | KB only, or attach/create a Gamepad |
| `map(action, *keys, buttons=[…])` | Bind keys and/or pad buttons |
| `map_axis(name, key_neg=…, pad_axis=…)` | Digital + analog axis |
| `is_pressed` / `is_down` / `is_released` | Edge / level (KB **or** pad) |
| `get_axis(left, right)` / `get_axis("move_x")` | Two actions **or** a named axis |
| `load` / `save` | JSON only |
| `emit_to_bus` | Default True → `key.{action}.*` |

`pu.Input` is the only input action-map service (no `Keyboard` alias).

### Mouse API (summary)

| Method | Meaning |
| --- | --- |
| `position`, `x`, `y`, `movement` | Cursor |
| `is_pressed/down/released(button)` | `"left"`, `"right"`, … |

### Gamepad (device service)

Poll-only; usually created by `Input(gamepad=True)`. Standalone: `pu.Gamepad(player=0)`.

| Method | Meaning |
| --- | --- |
| `is_available()` / `name_on_device` | Connection |
| `is_pressed/down/released("a")` | Button aliases |
| `get_axis` / `get_vector` | Default deadzone 0.15 |
| `set_vibration` | Best-effort rumble |

Aliases: `a/b/x/y`, `lb/rb/lt/rt`, `dpad_*`, `start/select/guide`.
Axes: `left_x/y`, `right_x/y`, `left_trigger`, `right_trigger`.

### Touch (minimal)

| Method | Meaning |
| --- | --- |
| `count`, `position` | Primary point |
| `is_down` / `is_pressed` / `is_released` | Edges from the previous frame |

Queries: `one("@Input")`, `@Mouse`, `@Gamepad`, `@Touch`.

## 2. EventBus path

EventBus is **not** bootstrapped automatically — add it yourself:

```python
class GameApp(pu.App):
    def on_load(self) -> None:
        self.bus = pu.EventBus()

        self.input = pu.Input()
        self.input.map("jump", pr.KEY_SPACE)

        self.bus.subscribe("key.jump.pressed", self._on_jump, priority=10)
        self.bus.subscribe("mouse.left.pressed", self._on_click)

    def _on_jump(self, **kwargs) -> None:
        action = kwargs.get("action")
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

| Pattern | Example | Source |
| --- | --- | --- |
| `key.{action}.pressed` | `key.jump.pressed` | Input (KB and/or pad actions) |
| `key.{action}.down` / `.released` / `.repeat` | | Input |
| `mouse.{button}.pressed` | `mouse.left.pressed` | Mouse |
| `touch.pressed` / `.down` / `.released` | | Touch |

Typical payload: `action=`, `device=`, `position=` (mouse/touch).

Events are only `defer`red when there are listeners (`has_listeners` gate).

## 3. Dual drain (important)

Per **fixed step** (`App._fixed_step`):

```
1. on_begin_update     ← Input/Mouse/Touch poll → EventBus.defer
2. EventBus.dispatch() ← EARLY  (same-frame input before gameplay update)
3. App.fixed_update(dt, step)  ← application logic (user hook)
4. SceneManager.update(dt)     ← update tree (called by user)
5. sync transforms
6. on_after_update + SceneManager.apply_pending (called by user)
7. on_fixed_update     ← physics
8. EventBus.dispatch() ← LATE   (gameplay events deferred during update/physics)
```

| Drain | When | For |
| --- | --- | --- |
| Early | After input polling | Same-frame input reactions |
| Late | After physics | Gameplay / post-collision events |

`publish` = immediate and synchronous (avoid in large hot paths).
`defer` + drain = frame-order safe.

## 4. Signals (decorator)

Besides EventBus string topics, units have **Signal** + `@on`:

```python
from plyunit import on


class MyService(pu.ServiceUnit):
    @on("@App", event="on_begin_update")
    def _poll(self, dt: float) -> None: ...
```

Wiring happens automatically when the service attaches (see `wire_bindings`).
Input services use this pattern toward `@App`.

## 5. ImGui capture

When ImGui is active, check it before game input:

```python
imgui = self.one_or_none("@ImGui", scope="global")
if imgui is not None and imgui.want_capture_keyboard():
    return  # do not process game keys
if imgui is not None and imgui.want_capture_mouse():
    return
```

[imgui.md](imgui.md).

## 6. One-shot input vs fixed catch-up

Under lag, `App` may run **2–`max_substeps_per_frame`** fixed steps in one wall-clock frame. Raylib `Is*Pressed` latches for the whole frame, so unguarded edge polls in `update` multi-fire (e.g. 1 click → N spawns).

| API | Policy |
| --- | --- |
| `Input` / `Mouse` / `Gamepad` / `Touch` edges | **First fixed substep only** (`App.is_first_fixed_step`) |
| EventBus `*.pressed` / `*.released` / `*.repeat` | Same (via service edges) |
| `is_down` / `is_up` / EventBus `*.down` | **Every** fixed substep (held movement) |
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
| Events never arrive | Subscribe **before** the frame; make sure `EventBus` was created while the App is active |
| No early drain | The App must have `@EventBus` registered |
| Two Keyboards | Unique service — a second instance can conflict on name |
| Polling in render | OK, but fixed logic belongs in `fixed_update` |
| `publish` re-entrancy | Prefer `defer` for chained effects |
| One-shot multi-fires under lag | Use services **or** `app.is_first_fixed_step` for raw pyray |
| INI bindings | Not supported — use JSON only |

## 8. Recommended patterns

| Use case | Path |
| --- | --- |
| Multi-device movement | `Input(gamepad=True)` + `map_axis` / `get_axis` |
| Jump on KB + pad | `map(..., buttons=["a"])` + `is_pressed` / `key.jump.pressed` |
| Pad-only polling | `Gamepad` device service |
| Raw pyray one-shots | Gate with `app.is_first_fixed_step` |
| Debug UI | ImGui + want_capture_* |
| Decoupled gameplay systems | Late EventBus + custom topics like `game.player.died` |

### Input JSON schema

Flat (keyboard only)::

```json
{ "jump": [32, 38], "shoot": [17] }
```

Extended (actions + axes)::

```json
{
  "actions": {
    "jump": { "keys": [32], "buttons": ["a"] }
  },
  "axes": {
    "move_x": {
      "key_neg": [65, 263],
      "key_pos": [68, 262],
      "pad_axis": "left_x",
      "pad_buttons_neg": ["dpad_left"],
      "pad_buttons_pos": ["dpad_right"],
      "deadzone": 0.2
    }
  }
}
```
