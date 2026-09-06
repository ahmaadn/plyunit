# Gameplay utilities (Timer, Tween, animation events)

Optional services for delays, property motion, and animation-end signals.

## Registration

**Not** auto-wired by `init`. Explicit only:

```python
import plyunit as pu

app = pu.init(MyApp(), pu.AppConfig(...))
timers = pu.Timer()
tweens = pu.TweenAnimation()
# optional
pu.EventBus()  # for animation.finished bus events
```

Query:

```python
timers = app.one("@Timer")
tweens = app.one("@TweenAnimation")
```

## Time bases

| Base | Hook | Delta | Typical use |
| --- | --- | --- | --- |
| `fixed` | `on_fixed_update` | `fixed_delta_time` | combat CD, physics-synced |
| `wall` | `on_start_frame` | `unscaled_dt` | UI fades, real-time UX |
| `scaled` | `on_start_frame` | `dt` (= unscaled × `time_scale`) | game-time UI |

Rules:

- Each timer/tween picks **one** base — no double tick.
- `service.pause()` freezes that service entirely.
- `time_scale == 0` → no fixed steps; `wall` still advances; `scaled` freezes.
- On scene unload, call `timers.clear()` / `tweens.kill_all()` from game code.

## Timer

```python
h = timers.delay(0.5, on_done, time_base="fixed")
h = timers.interval(1.0, on_tick, time_base="wall", count=5)  # count=None forever
h.cancel()

timers.pause()
timers.resume()
timers.clear()
```

### Generator runner

```python
def cutscene():
    yield timers.wait(0.5, time_base="wall")
    yield tweens.to(node.transform, 0.3).position((100, 50)).play()
    yield timers.wait(0.2)


coro = timers.run(cutscene())
coro.cancel()
```

Yield `timers.wait(...)` or a tween / sequence / parallel.

## TweenAnimation

### Fluent transform

```python
tw = (
    tweens
    .to(node.transform, duration=0.3, easing="quad_out", time_base="wall")
    .position((x, y))
    .rotation(90)
    .scale((2, 2))
    .yoyo(True)
    .loop(2)  # total plays; -1 infinite
    .on_complete(cb)
    .play()
)
tw.kill()
```

Writes through `set_position` / `set_rotation` / `set_scale` so TransformStore dirty flags stay correct.

### Raw property

```python
tweens.tween(getter, setter, end, duration=0.2, easing="linear", time_base="fixed")
```

### Sequence / parallel

```python
a = tweens.to(t, 0.3).position((10, 0))
b = tweens.to(t, 0.3).position((10, 10))
tweens.sequence(a, b).on_complete(done).play()
tweens.parallel(a, b).play()  # different properties
```

### Kill helpers

```python
tweens.kill(tw)
tweens.kill_by_target(node.transform)
tweens.kill_by_tag("ui")
tweens.kill_all()
```

### Same-property policy

Property key = `(id(target), prop_name)`. A new tween on the same property **kills** the previous (no `on_complete`). Parallel is OK across different properties.

### Easing names

`linear`, `quad_in/out/in_out`, `cubic_in/out/in_out`, `expo_in/out/in_out`, `back_out`, `elastic_out`.

```python
from plyunit import get_easing, EASINGS
```

### Physics note

Do not tween dynamic physics bodies without kinematic mode — transform fights the solver.

## Animation finished

When a **non-looping** clip ends, `AnimationController`:

1. Emits `controller.finished` with `(clip_name, controller)`
2. If EventBus is registered: `publish("animation.finished", name=..., unit=..., controller=...)`

```python
controller.finished.connect(handler)

bus.subscribe("animation.finished", handler)
# handler(*, name, unit, controller)
```

Looping clips do not emit finished. Frame markers are not in v1.

## Example

```bash
uv run plyunit-example --tween
```
