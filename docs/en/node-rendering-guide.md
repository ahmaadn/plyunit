# Node and Efficient Rendering Guide

> **Full rendering guide:** [rendering/index.md](rendering/index.md)  
> (choosing a draw path, batching, native C, layers, culling).

This document explains how to build correct `NodeUnit`s and how to draw objects
singly or in batches in plyunit.

The main focus is keeping the code easy to use without sacrificing
performance. After the runtime optimizations, the fastest patterns are:

- use `NodeUnit` for scene structure, lifecycle, parent-child, and transforms;
- use `SpriteRenderer` for ordinary sprites;
- use `renderer.render_batch()` for many sprites managed by one node/system;
- use `draw(canvas)` only for custom drawing that truly needs direct Canvas
  access.

## 1. Core principles

### 1.1 Pick the right render path

| Need | Use | Notes |
| --- | --- | --- |
| One sprite per node | `SpriteRenderer` | The common, automatically optimized path. |
| Many sprites with the same texture/state | `renderer.render_batch()` | Fits particles, simple tiles, crowds, or sprite spam. |
| Primitive shapes like rectangles/circles/lines | `renderer.render_rect()`, `render_circle()`, `render_line()` | Call in `render_submit()`, not `draw()`, whenever possible. |
| Drawing directly to the Canvas | `draw(canvas)` + `enable_custom_draw()` | Special cases only. |
| UI sprites/text | typed `render_*` with `Layer.UI`, plus `Text.push()` | Screen-space UI through the UI layer. |

### 1.2 Avoid expensive patterns

- Do not override `draw()` for nodes that only show a sprite; use `SpriteRenderer`.
- Do not create hundreds of nodes with empty `draw()`; the default `NodeUnit` no longer submits custom draws.
- Do not give thousands of sprites unique `z_index` values when the visual order does not require it.
- Do not use `dest` on `render_sprite()` when `pos + scale` is enough.
- For high volume, use `render_batch` (or `pos_xy=`) instead of N× `render_sprite`.

## 2. Building a correct node

`NodeUnit` should be used as a transform and lifecycle container. A node can
have children and components.

```python
import plyunit as pu
from plyunit.core.components.builtin import SpriteRenderer


class Player(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="Player")
        self.transform.set_position(100.0, 120.0)
        self.add_component(
            SpriteRenderer(
                texture=texture,
                layer=int(pu.Layer.PLAYER),
                z_index=0,
                scale=1.0,
            )
        )

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        self.transform.set_position(x + 120.0 * dt, y)
```

What the example above does right:

- the position is changed with `transform.set_position(...)`, not by assigning directly to `transform.local.position`;
- the sprite is shown through `SpriteRenderer`;
- `z_index` is only used when a special order is truly needed;
- the node only overrides `update()` because it actually has movement logic.

## 3. Static nodes

For nodes that do not move and have no per-frame logic, do not override
`update()`.

```python
class Tree(pu.NodeUnit):
    def __init__(self, texture, x: float, y: float) -> None:
        super().__init__(name="Tree")
        self.transform.set_position(x, y)
        self.add_component(
            SpriteRenderer(
                texture=texture,
                layer=int(pu.Layer.ENTITIES),
                z_index=0,
            )
        )
```

When creating many static sprites with the same texture and state, use the
same `z_index` so the renderer can merge them into a batch.

```python
for i in range(500):
    tree = Tree(texture, x=float(i % 25) * 32.0, y=float(i // 25) * 32.0)
    scene.root.attach(tree)
```

## 4. Drawing a single sprite with a component

This is the recommended approach for one sprite per node.

```python
node = pu.NodeUnit(name="Coin")
node.transform.set_position(240.0, 160.0)
node.add_component(
    SpriteRenderer(
        texture=coin_texture,
        layer=int(pu.Layer.ENTITIES),
        z_index=0,
        scale=1.0,
        tint=(255, 255, 255, 255),
    )
)
scene.root.attach(node)
```

`SpriteRenderer` supports:

- `texture` or `asset_key`;
- `source_rect` for spritesheets;
- `pivot` for the rotation origin;
- `flip_x` and `flip_y`;
- `scale`;
- `layer` and `z_index`;
- `tint`;
- `use_interpolation`.

## 5. Drawing a single sprite manually

If the node acts as a renderer/system and a component does not fit, use
`render_submit()`.

```python
class SingleSpriteNode(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="SingleSpriteNode")
        self.texture = texture
        self.transform.set_position(100.0, 100.0)

    def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
        wt = self.world_transform_lerp(1.0)
        renderer.render_sprite(
            texture=self.texture,
            pos=wt.position,
            layer=int(pu.Layer.ENTITIES),
            z=0,
            scale=1.0,
            tint=(255, 255, 255, 255),
        )
```

Use this pattern when:

- the sprite is not a component of an ordinary node;
- the node is a dedicated renderer;
- there is only one sprite or a small number;
- you need manual submit control.

For ordinary sprites, `SpriteRenderer` remains the recommended choice.

## 6. Drawing many sprites with a batch

When one node/system manages many sprites, use `render_batch()`.

```python
class StarField(pu.NodeUnit):
    def __init__(self, texture, positions: list[tuple[float, float]]) -> None:
        super().__init__(name="StarField")
        self.texture = texture
        self.positions = positions

    def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
        renderer.render_batch(
            texture=self.texture,
            positions=self.positions,
            layer=int(pu.Layer.BACKGROUND),
            z=0,
            scale=1.0,
            tint=(255, 255, 255, 255),
        )
```

Batches fit:

- simple particles;
- bullets or projectiles sharing one texture;
- static decoration;
- simple tiles without a full tilemap;
- background sprite spam.

`render_batch` assumes shared material (texture, source, tint, scale,
rotation, origin, layer/state). Many `render_sprite` calls still land in the
same FrameBuffer; the UBR flush groups runs by `tex_id` (not automatic
submit-time batching). For homogeneous position lists, always prefer the batch
API.

## 7. Many `render_sprite` vs `render_batch`

Each `render_sprite` writes one SoA row. For hundreds to thousands of
positions with the same material, use `render_batch` (+ a contiguous float32
`pos_xy` for a vectorized FrameBuffer copy).

```python
class ManyCoins(pu.NodeUnit):
    def __init__(self, texture, positions: list[tuple[float, float]]) -> None:
        super().__init__(name="ManyCoins")
        self.texture = texture
        self.positions = positions

    def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
        renderer.render_batch(
            texture=self.texture,
            positions=self.positions,
            layer=int(pu.Layer.ENTITIES),
            z=0,
            scale=1.0,
        )
```

## 8. Custom drawing with `draw(canvas)`

`draw(canvas)` is the escape hatch. The default `NodeUnit` does not submit an
empty draw. To use `draw()`, enable custom draw or override `draw()` on the
class.

```python
class HealthBar(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="HealthBar")
        self.enable_custom_draw()
        self.hp_ratio = 1.0

    def draw(self, canvas: pu.Canvas) -> None:
        canvas.draw_rect(
            rect=(20.0, 20.0, 200.0, 16.0),
            color=(40, 40, 40, 255),
        )
        canvas.draw_rect(
            rect=(20.0, 20.0, 200.0 * self.hp_ratio, 16.0),
            color=(220, 50, 50, 255),
        )
```

However, for simple shapes it is better to submit primitives in
`render_submit()`.

```python
class HealthBarFast(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="HealthBarFast")
        self.hp_ratio = 1.0

    def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
        renderer.render_rect(
            rect=(20.0, 20.0, 200.0, 16.0),
            color=(40, 40, 40, 255),
            layer=pu.Layer.UI,
        )
        renderer.render_rect(
            rect=(20.0, 20.0, 200.0 * self.hp_ratio, 16.0),
            color=(220, 50, 50, 255),
            layer=pu.Layer.UI,
        )
```

Prefer `render_submit()` for the typed renderer because the engine can still
sort, group state, and batch.

## 9. Layers and z-index

`layer` defines the coarse render-order group. `z` or `z_index` defines the
order inside a layer.

```python
SpriteRenderer(
    texture=texture,
    layer=int(pu.Layer.ENTITIES),
    z_index=0,
)
```

Use unique z only when an object truly needs a specific visual order.

```python
# Good for batching: all decorations can be drawn in the same order.
z_index = 0

# Only if needed: objects must always be ordered by manual depth.
z_index = object_depth
```

If you need sorting by Y position, use a y-sort layer or `y_sort` according to
the renderer feature. Keep in mind that y-sort usually breaks batching because
the sort key differs.

## 10. Recommended transform usage

Use the transform setters so dirty tracking and world-transform
synchronization stay correct.

```python
node.transform.set_position(100.0, 200.0)
node.transform.set_rotation(45.0)
node.transform.set_scale(2.0, 2.0)
```

Avoid direct assignment for runtime changes:

```python
# Avoid for runtime updates.
node.transform.local.position = (100.0, 200.0)
```

Direct assignment may still appear in old code, but setters are safer for the
runtime optimizations.

## 11. Recommended patterns

### 11.1 Actor with a sprite

```python
class Enemy(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="Enemy")
        self.velocity = (-40.0, 0.0)
        self.add_component(
            SpriteRenderer(
                texture=texture,
                layer=int(pu.Layer.ENTITIES),
                z_index=0,
            )
        )

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        vx, vy = self.velocity
        self.transform.set_position(x + vx * dt, y + vy * dt)
```

### 11.2 Static decoration

```python
class Decoration(pu.NodeUnit):
    def __init__(self, texture, pos: tuple[float, float]) -> None:
        super().__init__(name="Decoration")
        self.transform.set_position(*pos)
        self.add_component(
            SpriteRenderer(
                texture=texture,
                layer=int(pu.Layer.BACKGROUND),
                z_index=0,
            )
        )
```

### 11.3 Renderer node for bulk data

```python
class BulletRenderer(pu.NodeUnit):
    def __init__(self, texture) -> None:
        super().__init__(name="BulletRenderer")
        self.texture = texture
        self.positions: list[tuple[float, float]] = []

    def render_submit(self, renderer: pu.Renderer, context: pu.RenderContext | None = None) -> None:
        renderer.render_batch(
            texture=self.texture,
            positions=self.positions,
            layer=int(pu.Layer.EFFECTS),
            z=0,
            scale=1.0,
        )
```

## 12. Performance checklist

Before creating many nodes or many draw calls, check the following:

- Do static nodes avoid overriding `update()`?
- Do ordinary sprites use `SpriteRenderer`, not `draw()`?
- Do many identical sprites use `render_batch()`?
- Can `z_index` be shared for sprites that do not need a unique order?
- Are texture/source/tint/scale/layer/state shared within one batch?
- Are runtime transforms changed via `set_position`, `set_rotation`, or `set_scale`?
- Are y-sort, shaders, scissor, blend modes, and custom draws only used when needed?

## 13. Practical summary

- One sprite per node: `NodeUnit + SpriteRenderer`.
- Many data-oriented sprites: one node/system + `render_batch()`.
- Shapes/text/UI: typed renderer (`render_rect`, `Text.push`, `render_*` + `Layer.UI`).
- Direct Canvas: `draw(canvas)` only when no typed renderer fits.
- Large batches: `render_batch` + shared material; the UBR flush groups by `tex_id`.
