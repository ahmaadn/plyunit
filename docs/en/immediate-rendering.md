# DrawScope and direct Canvas drawing

`DrawScope` is a convenience wrapper around `Renderer.canvas` for scissor,
blend, shader, texture-target, and stencil scopes. The current renderer has no
`RenderPipeline.IMMEDIATE`, `set_immediate`, or immediate callback scheduler.

Use typed `Renderer.render_*` methods for normal game content. Use `DrawScope`
only for operations that cannot be represented by the typed queue.

## Queued custom drawing

`render_custom` is the safest way to schedule Canvas/DrawScope work because it
keeps the callback in render-pass, layer, state, and depth ordering:

```python
def render_submit(self, renderer: pu.Renderer) -> None:
    def draw_special(canvas: pu.Canvas) -> None:
        draw = pu.DrawScope(canvas)
        with draw.blend(pu.BlendMode.ADDITIVE):
            draw.circle(400, 220, 36, (255, 90, 50, 160))

        with draw.scissor(40, 120, 400, 280):
            draw.rect((50, 140, 120, 80), (200, 180, 90, 220))

    renderer.render_custom(
        draw_func=draw_special,
        layer=pu.Layer.EFFECTS,
        z=0,
    )
```

Custom callbacks can break surrounding sprite runs. Prefer `render_sprite`,
`render_batch`, or primitive `render_*` methods when those APIs are enough.

## Direct use

`DrawScope` does not schedule itself and does not validate the raylib drawing
lifetime. Direct calls are valid only while the application is inside an
active drawing context, such as controlled code within `App.draw()`:

```python
draw = pu.DrawScope(self.renderer.canvas)
with draw.scissor(20, 20, 200, 120):
    draw.rect((24, 24, 80, 40), (40, 80, 140, 255))
```

Do not call Canvas, DrawScope, raylib, or raw OpenGL drawing methods from
fixed-update code or outside `window.begin_drawing()` / `window.end_drawing()`.

## Context managers

Scopes restore their previous state on exit:

```python
with draw.scissor(x, y, w, h):
    ...
with draw.blend(pu.BlendMode.ADDITIVE):
    ...
with draw.shader(shader_handle):
    ...
with draw.texture_mode(render_target):
    ...
with draw.stencil(inverse=False) as stencil:
    with stencil.mask():
        draw.circle(...)
    draw.rect(...)
```

Common operations:

```python
draw.circle(x, y, radius, color)
draw.rect(rect_tuple, color)
draw.line(...)
draw.texture(**kwargs)
draw.canvas  # complete Canvas API
```

## Tradeoffs

| Typed queue | DrawScope / Canvas |
| --- | --- |
| Layer, depth, and render-pass ordering | Caller controls execution point |
| Scene culling support | No automatic culling |
| Sprite FrameBuffer and native UBR batching | Does not enter sprite UBR batches |
| Default for gameplay rendering | Special effects, masks, tools, offscreen work |

For thousands of homogeneous sprites, use `Renderer.render_batch` with the
native UBR path rather than direct drawing.

## App draw order

The render pipeline is user-owned; it lives inside `App.update(dt)`:

```text
renderer.reset_frame()
window.begin_drawing() / clear
SceneManager.render(renderer)
...app-level submissions / controlled DrawScope calls...
renderer.flush_all(camera=...)
ImGui.frame(dt)                # optional, when imgui is enabled
window.end_drawing()
```

## Gotchas

| Issue | Guidance |
| --- | --- |
| Direct DrawScope outside drawing context | Unsupported; use `render_custom` or a controlled drawing phase |
| Nested stencil | Not supported |
| Nested scissor | Scope replaces the clip and restores its parent on exit |
| Heavy custom callback | It can interrupt batching; prefer typed methods |
| ImGui ordering | ImGui is separate and renders via `ImGui.frame(dt)` after `flush_all` |

## See also

- [rendering/index.md](rendering/index.md)
- [rendering/queued-submit.md](rendering/queued-submit.md)
- [imgui.md](imgui.md)
