# Hexagonal architecture audit

This document describes the current `packages/plyunit/src/plyunit` layout
and its ports-and-adapters boundary. This is a breaking migration: removed
module paths, service loaders, and renderer methods have no compatibility
aliases. See [migration.md](migration.md).

## Dependency direction

```text
core / events / rendering / services / tilemap / utils
                         │
                         ▼
                  backends.ports
                         ▲
                         │
       backends.integrations.raylib / backends.physics.pymunk
                         ▲
                         │
             _bootstrap + lazy public facade
```

The package root `plyunit.__init__` owns a lazy export map. Plain
`import plyunit` does not load raylib, pymunk, or ImGui. Backend selection
happens at the facade/composition boundary; neutral modules import contracts
from `plyunit.backends.ports`, never the concrete backend or its selector.

Neutral services/data include `services/animations.py`,
`services/assets/schemas.py`, `services/assets/atlas.py`,
`services/spatial_index.py`, `services/text.py`, and `services/shaders.py`.
Concrete input, assets, audio, text, and shader services live under
`backends/integrations/raylib` and are selected by root facade exports.

## Current boundaries

| Domain | Core-facing API | Backend boundary | Concrete implementation |
| --- | --- | --- | --- |
| Window | `App`, `Window` root export | `IWindow` | raylib `Window` |
| Camera | `Camera2D` root export | `ICamera2D` | raylib `Camera2D` |
| Canvas/rendering | `Renderer`, `DrawScope`, `RenderPass` | `ICanvas2D`, `IUnifiedBufferBatch` | module-backed raylib canvas, native UBR |
| Assets/images | `Assets`, `ImageProcessor` | `IAssets`, `IImageProcessor` | raylib assets adapter |
| Text/fonts | `Text`, `ShapedText`, `TemplateText` | `IText`, `ITextRenderer`, `FontHandle` | raylib text service |
| Shaders | `Shaders`, `ShaderHandle` | `IShaders`, `ShaderHandle` | raylib shader service |
| Input | `Input`, `Mouse`, `Gamepad`, `Touch` | `IInput`, `IMouse`, `IGamepad`, `ITouch` | separate raylib device adapters |
| Audio | `Audio` | `IAudio` | raylib audio service |
| Physics | `Physics`, body/area/shape APIs | `PhysicsBackend` adapter boundary | pymunk |
| ImGui | `ImGui` | `ImGuiBackend` | imgui-bundle/raylib backend |

Tilemap rendering no longer uses `IRenderTargetOps` or a tilemap renderer
facade. `TileMapNode` uses the configured `Renderer.canvas` for render-target
baking and submits baked chunks or tiles through `Renderer.render_sprite`.

## Composition root

`init` and `create_app` in `plyunit._bootstrap` select concrete backends and
wire the application:

1. Resolve the configured window, canvas, native batch, assets, and camera
   factories. `Canvas2D()` returns the raylib canvas module, not a class instance.
2. Inject the adapters and construct `Renderer`, `SceneManager`, `Assets`,
   `Animations`, and the default camera. Renderer construction does not perform
   native GPU initialization.
3. Call `app.init(cfg)`: open the window, set up the camera, then call
   `Renderer.init()` / `ubr.init()` with a live graphics context.
4. Construct optional `Physics`, `ImGui`, and `Audio` services after App
   initialization; the active global registry retains them.
5. `app.run()` calls `on_load` before entering the loop. Load textures/fonts or
   bake reusable shapes here (or in scene/node load hooks), not before bootstrap.

Gameplay utilities are explicit services:

```python
timers = pu.Timer()
tweens = pu.TweenAnimation()
bus = pu.EventBus()
spatial = pu.SpatialIndex(cell_size=64.0)
```

They must be constructed while an App/global registry is active when automatic
service attachment is required.

## Public service names

The service class and unique registry name are intentionally the same:

| Class | Unique query |
| --- | --- |
| `Physics` | `@Physics` |
| `ImGui` | `@ImGui` |
| `Audio` | `@Audio` |
| `Timer` | `@Timer` |
| `TweenAnimation` | `@TweenAnimation` |
| `EventBus` | `@EventBus` |
| `SpatialIndex` | `@SpatialIndex` |

The old `*Service` names are not compatibility aliases.

## Current rendering boundary

```text
SceneManager.render(renderer)
  → SceneUnit.dispatch_render(renderer)
  → NodeUnit/component render_submit(renderer, context)
  → Renderer.render_sprite / render_batch / render_sprites → FrameBuffer SoA
  → Renderer.render_shaped_text                            → glyph quads in SoA
  → Renderer.render_custom                                → queued Canvas callback
  → Renderer.flush_all                                    → passes/state/native UBR
```

`SceneUnit` has no `render_submit` hook. Attach renderer nodes to its root,
or submit app-level work from `App.update(dt)` before `flush_all`.
Reusable shapes use cached `canvas.create_*` textures and the sprite path;
dynamic/debug geometry uses `render_custom(draw_func=lambda canvas:
canvas.draw_*())`. The former primitive submit methods are removed.

There is no `RenderPipeline` enum or immediate callback scheduler. `DrawScope`
is a helper owned by a renderer; direct Canvas lifecycle control remains with
the caller.

## Resource handles and ownership

The contracts in `backends.ports.handler` expose neutral size, region, and
identity information, never raw native structs. Concrete raylib handles
`Image`, `Texture2D`, `RenderTexture`, `Shader`, `Font`, and `StreamingTexture`
are defined in `backends/integrations/raylib/handler.py`. Their `raw_*` fields
are for adapter implementation only.

- `Assets.get_asset(id)` / `Assets[id]` returns a texture handle directly.
  `texture_id` is a logical string ID; `source_rect` and `parent_id` describe
  its region and owning cache entry. There is no `get_texture_data(...).texture`.
- The batch adapter's `texture_id(handle)` extracts the numeric GPU identifier
  used by the FrameBuffer/native runs. Core must not read `raw_texture.id`.
- `Assets.store_texture` transfers ownership of a standalone root texture
  (including a baked shape). Resolve its new handle from the assigned asset ID.
- `render_target.texture`, `font.texture`, and `stream.texture` are borrowed
  attachments. Never adopt them into `Assets` or unload them separately.
- Reloading, unloading, or atlas packing invalidates captured asset handles.
  Resolve the logical ID again; keep owners alive until queued draws finish.
- Shutdown releases scene/app resources and services, then assets and the
  renderer/native batch, before closing the window.

## Known boundary caveats

- `Physics` directly depends on pymunk inside its concrete backend package;
  consumers should import it through `plyunit.backends.physics` or root exports.
- `Renderer` requires the native UBR backend and fails fast without it.
- `TileMapNode` accesses `Renderer.canvas` for baking, so tilemap is coupled to
  the configured renderer abstraction rather than a separate RT protocol.
- Some public-looking deep-module types are not re-exported. Treat facade
  `__all__` lists as the stability boundary.
- `Input` maps keyboard actions only; `Gamepad` is separate. Keyboard events
  require `Input(emit_to_bus=True)` and an already registered `EventBus`.
- Input services do not automatically poll themselves on fixed steps; apps
  using deferred input events must poll before the early EventBus dispatch.

## Source map

All paths below are relative to `packages/plyunit/`.

| Area | Current path |
| --- | --- |
| App/config | `src/plyunit/core/` |
| Unit tree/components | `src/plyunit/core/units/`, `core/components/` |
| Events | `src/plyunit/events/` |
| Renderer | `src/plyunit/rendering/` |
| Services | `src/plyunit/services/` |
| Assets/audio data | `src/plyunit/services/assets/`, `src/plyunit/services/audio/` |
| Neutral text/shader helpers | `src/plyunit/services/text.py`, `src/plyunit/services/shaders.py` |
| Tilemap | `src/plyunit/tilemap/` |
| Backend contracts | `src/plyunit/backends/ports/` |
| Raylib adapters | `src/plyunit/backends/integrations/raylib/` |
| Raylib resource handles | `src/plyunit/backends/integrations/raylib/handler.py` |
| Pymunk adapter | `src/plyunit/backends/physics/pymunk/` |
| Composition root | `src/plyunit/_bootstrap.py` |

## Audit conclusion

The architectural contract is ports-only dependencies for neutral code,
adapter-owned native resources, and backend selection at composition/facade
boundaries. `packages/plyunit/tests/common/test_import_boundaries.py` guards
these imports (including typing imports) and checks that resource ports expose
no raw fields or native constructors. The native UBR requirement is intentional;
it is not a reason to add a Python draw fallback.
