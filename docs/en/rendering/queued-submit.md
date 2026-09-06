# Typed renderer queue

Normal game content enters `Renderer` during `render_submit` and is flushed by
`Renderer.flush_all`. Sprites use a SoA `FrameBuffer`; primitives, shaped text,
and custom callbacks use the typed render queue.

## Lifecycle

```text
App.update(dt)  (user hook — the render pipeline)
  renderer.reset_frame()
  window.begin_drawing()
  SceneManager.render(renderer)
    SceneUnit.dispatch_render(renderer)
      NodeUnit.render_submit(renderer) / component render_submit
      renderer.render_*(...)
  ...app-level submissions...
  renderer.flush_all(camera=...)
  window.end_drawing()
```

Submit every render frame. Do not submit from fixed-update hooks.

## One sprite

```python
def render_submit(self, renderer: pu.Renderer) -> None:
    world = self.world_transform_lerp(1.0)
    renderer.render_sprite(
        texture=self.texture,
        pos=world.position,
        layer=pu.Layer.ENTITIES,
        z=0,
        scale=1.0,
        rotation=world.rotation,
        origin=(8.0, 8.0),
        source=None,
        tint=(255, 255, 255, 255),
    )
```

Each call appends one sprite to the FrameBuffer.

## Many sprites

`render_batch` shares texture, source, origin, rotation, scale, tint, state,
layer, and depth across all positions:

```python
renderer.render_batch(
    texture=texture,
    positions=positions,
    layer=pu.Layer.ENTITIES,
    z=0,
    source=None,
    origin=(0.0, 0.0),
    rotation=0.0,
    scale=1.0,
    tint=(255, 255, 255, 255),
)
```

For a NumPy hot path:

```python
renderer.render_batch(
    texture=texture,
    positions=pos_xy,  # required by the current signature
    pos_xy=pos_xy,     # contiguous numpy.float32 array with shape (n, 2)
    layer=pu.Layer.EFFECTS,
)
```

`pos_xy` avoids a Python loop and avoids normalization allocation when already
contiguous `float32`. The renderer still copies positions into its FrameBuffer;
this is a vectorized bulk append, not zero-copy simulation-to-GPU storage.

## Many sprites, many textures

`render_sprites` is the opposite of `render_batch`: N different textures at N
positions in one submit. Render state (pass, layer, z, scissor, blend, shader)
is interned once; only texture, UV, size, and transform vary per sprite. It
replaces a loop of `render_sprite` calls when the batch comes from
`canvas.create_rects`/`create_circles`/... :

```python
rects = canvas.create_rects(
    rects=[(0, 0, 32, 32), (0, 0, 16, 48)],
    colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
)
renderer.render_sprites(
    textures=rects,
    positions=[(10.0, 10.0), (60.0, 40.0)],
    layer=pu.Layer.ENTITIES,
    z=0,
)
```

Per-sprite `sources`, `origins`, `rotations`, `scales`, and `tints` sequences
are optional; a `pos_xy` contiguous `float32` array is accepted instead of
`positions`. `None` textures are skipped.

## Primitives as textures

Immediate primitives (`render_rect`, `render_circle`, ...) are convenient for
debug overlays but can become a bottleneck when drawn every frame. Bake them
once into a `Texture2D` with the Canvas creation API, store it in `Assets`,
and render it through the sprite path:

```python
paddle = canvas.create_rect(rect=(0, 0, 32, 8), color=(255, 255, 255, 255))
self.one("@Assets").store_texture("paddle", paddle)

# Or in bulk:
rects = canvas.create_rects(rects=[...], colors=[...])
self.one("@Assets").store_textures({"rect_1": rects[0], "rect_2": rects[1]})
```

Each primitive is drawn into a transparent render texture sized to its
bounding box (offsets normalized to the top-left corner) and returned as a
standalone `Texture2D`, so stored textures stay valid for reuse and are
packable by `Assets.build_texture_atlas` like any other root asset.

| Primitive | Single | Batch |
| --- | --- | --- |
| Rectangle | `canvas.create_rect(...)` | `canvas.create_rects(...)` |
| Circle | `canvas.create_circle(...)` | `canvas.create_circles(...)` |
| Line | `canvas.create_line(...)` | `canvas.create_lines(...)` |
| Triangle | `canvas.create_triangle(...)` | `canvas.create_triangles(...)` |
| Polygon | `canvas.create_poly(...)` | `canvas.create_polys(...)` |

## Primitives

> **Deprecated.** The immediate primitive submits (`render_rect`,
> `render_circle`, `render_line`, `render_triangle`, and the plural batch
> variants) are a per-frame performance bottleneck. Bake the shape once with
> `canvas.create_rect`/`create_circle`/... , store it via
> `Assets.store_texture`, and render it through `render_sprite` /
> `render_sprites` — see [Primitives as textures](#primitives-as-textures).

```python
renderer.render_rect(  # DeprecationWarning
    rect=(10, 10, 40, 20),
    color=(255, 0, 0, 255),
    layer=pu.Layer.WORLD,
)
renderer.render_circle(  # DeprecationWarning
    center=(50, 50),
    radius=8.0,
    color=(0, 255, 0, 255),
)
renderer.render_line(  # DeprecationWarning
    start=(0, 0),
    end=(100, 100),
    color=(0, 0, 255, 255),
)
renderer.render_triangle(...)  # DeprecationWarning

# Vectorized primitive APIs (also deprecated)
renderer.render_rects(...)
renderer.render_circles(...)
renderer.render_lines(...)
renderer.render_triangles(...)
```

There are no separate `render_ui_*` or `render_debug_*` families. Use ordinary
typed methods with `layer=Layer.UI` / `Layer.DEBUG`, or set `pass_name`.

## Text

Use `Text.push(...)` for the normal shaped-text path, or
`Renderer.render_shaped_text(...)` when text has already been shaped. The old
`Renderer.render_text(...)` method is deprecated.

```python
text = pu.Text()  # construct once while the App registry is active
text.push("Score: 10", pos=(20, 20), color=(255, 255, 255, 255))
```

## Custom drawing

```python
renderer.render_custom(
    draw_func=lambda canvas: canvas.draw_circle(
        center=(64, 64),
        radius=32,
        color=(255, 255, 0, 180),
    ),
    layer=pu.Layer.EFFECTS,
    z=0,
)
```

Use custom callbacks only when typed methods cannot express the operation;
callbacks can interrupt sprite runs. See [../immediate-rendering.md](../immediate-rendering.md).

## Render state

```python
renderer.render_sprite(
    texture=texture,
    pos=(0, 0),
    scissor=(10, 10, 100, 100),
    blend_mode=pu.BlendMode.ADDITIVE,
    shader=shader,
)
```

Different scissor, blend, shader, or explicit state IDs form separate groups.

## Sorting behavior

Pass and layer order are resolved first. Exact painter-order behavior then
depends on the layer:

- Depth-sorted and y-sorted sprites retain depth/y ordering.
- Ordinary sprite layers may regroup same-state sprites by texture to create
  longer native UBR runs; `z` is not a strict painter-order guarantee there.
- `Layer.EFFECTS` is depth-sorted by default.
- `Renderer.enable_y_sort_layer(layer, enabled=True)` controls global y-sort
  layer behavior.

When overlapping sprites require strict order, use a depth-sorted/y-sorted
layer or separate state/layer boundaries. Do not rely on unique `z` values on
an ordinary texture-sorted layer.

## Anti-pattern

```python
# Expensive and unnecessary for homogeneous sprites
for position in positions:
    renderer.render_sprite(texture=texture, pos=position)

# One vectorized append
renderer.render_batch(texture=texture, positions=positions)

# Also expensive: N distinct textures through N render_sprite calls
for texture, position in zip(textures, positions):
    renderer.render_sprite(texture=texture, pos=position)

# One vectorized append
renderer.render_sprites(textures=textures, positions=positions)
```

## See also

- [best-practices.md](best-practices.md)
- [ubr.md](ubr.md)
- [layers-sort-cull.md](layers-sort-cull.md)
- [../node-rendering-guide.md](../node-rendering-guide.md)
