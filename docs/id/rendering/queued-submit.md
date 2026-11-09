# Typed renderer queue

`Renderer` accepts submissions from node/component
`render_submit(renderer, context)` hooks or from `App.update(dt)`. Sprites and
shaped glyph quads use the SoA `FrameBuffer`; dynamic Canvas geometry and
custom callbacks use the typed render queue. `Renderer.flush_all` draws both.

## Lifecycle

```text
App.update(dt)  (user hook — the render pipeline)
  renderer.reset_frame()
  window.begin_drawing()
  SceneManager.render(renderer)
    SceneUnit.dispatch_render(renderer)
      NodeUnit.render_submit(renderer, context) / component render_submit
      renderer.render_sprite / render_batch / render_sprites / render_shaped_text
      renderer.render_custom
  ...app-level submissions...
  renderer.flush_all(camera=...)
  window.end_drawing()
```

Submit every render frame. Do not submit from fixed-update hooks.
`SceneUnit` has no `render_submit` hook; attach renderer nodes to `scene.root`.

Use `ICanvas2D` and resource handle types from `plyunit.backends.ports` for
neutral type annotations. `Canvas2D()` returns the module-backed canvas;
it is a factory, not a canvas class. Raw textures and native GPU IDs are not
renderer inputs.

## One sprite

```python
def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
    world = context.render_transform if context is not None else None
    if world is None:
        world = self.world_transform_lerp(1.0)
    renderer.render_sprite(
        texture=self.texture,
        pos=world.position,
        layer=context.layer if context is not None else self.layer,
        z=context.z if context is not None else self.z_index,
        scale=1.0,
        rotation=world.rotation,
        origin=(8.0, 8.0),
        source=None,
        tint=(255, 255, 255, 255),
        pass_name=context.pass_name if context is not None else None,
        state_id=context.state_id if context is not None else None,
        y_sort=context.y_sort if context is not None else self.y_sort_enabled,
        y_sort_origin=context.y_sort_origin if context is not None else world.position[1],
        screen_space=context.screen_space if context is not None else None,
    )
```

Each call appends one sprite to the FrameBuffer. Passing the resolved context
preserves inherited pass, scissor/blend/shader state, screen space, and y-sort.
`texture` is a `Texture2DHandle`, including a spritesheet/atlas region.
`source=None` uses its `source_rect`; its logical `texture_id` is a string,
while `IUnifiedBufferBatch.texture_id(handle)` resolves the GPU integer.

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
    pos_xy=pos_xy,  # contiguous numpy.float32 array with shape (n, 2)
    layer=pu.Layer.EFFECTS,
)
```

`positions` can be omitted when `pos_xy` is supplied. `pos_xy` avoids a Python
loop and avoids normalization allocation when already contiguous `float32`.
The renderer still copies positions into its FrameBuffer;
this is a vectorized bulk append, not zero-copy simulation-to-GPU storage.

## Many sprites, many textures

`render_sprites` is the opposite of `render_batch`: N different textures at N
positions in one submit. Render state (pass, layer, z, scissor, blend, shader)
is interned once; only texture, UV, size, and transform vary per sprite. It
replaces a loop of `render_sprite` calls when the batch comes from
`canvas.create_rects`/`create_circles`/... :

```python
# Create once in on_load/on_ready, after the graphics context exists.
rects = canvas.create_rects(
    rects=[(0, 0, 32, 32), (0, 0, 16, 48)],
    colors=[(255, 0, 0, 255), (0, 255, 0, 255)],
)
assets.store_textures({"red_rect": rects[0], "green_rect": rects[1]})

# Submit each render frame; resolve handles again if assets are repacked.
renderer.render_sprites(
    textures=[assets["red_rect"], assets["green_rect"]],
    positions=[(10.0, 10.0), (60.0, 40.0)],
    layer=pu.Layer.ENTITIES,
    z=0,
)
```

Per-sprite `sources`, `origins`, `rotations`, `scales`, and `tints` sequences
are optional; a `pos_xy` contiguous `float32` array is accepted instead of
`positions`. `None` textures are skipped.

## Primitives as textures

The former `Renderer` primitive submit methods are removed, including their
plural variants. For reusable geometry, bake a shape once with the Canvas
creation API, transfer its standalone texture to `Assets`, and draw it through
the sprite path. Do not bake shapes per frame.

```python
# App.on_load, after bootstrap.
self.assets.store_texture(
    "paddle",
    self.canvas.create_rect(rect=(0, 0, 32, 8), color=(255, 255, 255, 255)),
)

# App.update, after reset_frame and before flush_all.
self.renderer.render_sprite(texture=self.assets["paddle"], pos=(80.0, 120.0))
```

Each shape is baked into a transparent offscreen target sized to its bounds,
then copied into a standalone `Texture2DHandle`. `Assets.store_texture`
adopts this standalone resource and assigns its logical asset ID. Resolve
that ID again after storage or atlas packing; do not keep stale pre-pack handles.
Baked shape textures can be packed by `Assets.build_texture_atlas`.

A render target's `texture`, a font's atlas, and a streaming texture's
attachment are **borrowed**, unlike these standalone baked textures. `Assets`
cannot adopt or free them. Keep their owner alive until queued draws finish,
and release only the owner before the graphics context closes.

| Primitive | Single | Batch |
| --- | --- | --- |
| Rectangle | `canvas.create_rect(...)` | `canvas.create_rects(...)` |
| Circle | `canvas.create_circle(...)` | `canvas.create_circles(...)` |
| Line | `canvas.create_line(...)` | `canvas.create_lines(...)` |
| Triangle | `canvas.create_triangle(...)` | `canvas.create_triangles(...)` |
| Polygon | `canvas.create_poly(...)` | `canvas.create_polys(...)` |

## Dynamic and debug geometry

For geometry whose shape changes every frame, queue a Canvas callback.
The callback runs during flush in the selected pass/layer/state. The rectangle
Canvas method is `draw_rectangle`, not `draw_rect`:

```python
renderer.render_custom(
    draw_func=lambda canvas: canvas.draw_rectangle(
        rect=(20.0, 20.0, 200.0 * hp_ratio, 16.0),
        color=(220, 50, 50, 255),
    ),
    layer=pu.Layer.UI,
)
```

There are no `render_ui_*` or `render_debug_*` families. Use sprite/text
submissions or `render_custom` with `Layer.UI` / `Layer.DEBUG`, or select a
render pass explicitly.

## Text

Use `Text.push(...)` for the normal shaped-text path, or
`Renderer.render_shaped_text(...)` when text has already been shaped. Glyph
quads enter the same native sprite batch and carry a borrowed font-atlas
handle; the font must stay loaded until flush. Use `Text.draw` only for
intentional immediate Canvas drawing inside a drawing context.

```python
text = pu.Text()  # construct once while the App registry is active
text.push("Score: 10", pos=(20, 20), color=(255, 255, 255, 255), layer=pu.Layer.UI)
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

Use custom callbacks for dynamic/debug geometry and operations the sprite
path cannot express. Draw through the supplied `ICanvas2D`; do not submit
renderer work inside a callback (submissions during flush are rejected).
Callbacks can interrupt sprite runs. See [../immediate-rendering.md](../immediate-rendering.md).

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
