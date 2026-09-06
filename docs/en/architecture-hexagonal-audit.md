# Hexagonal architecture audit

This document describes the current `src/plyunit` layout. It replaces the old
generated snapshot that referenced removed `plyunit.api`, `plyunit.input`,
renderer facades, and render-target operation modules.

## Dependency direction

```text
core / events / services / rendering / assets / audio / tilemap
                         │
                         ▼
              backends.interfaces protocols
                         ▲
                         │
       backends.integrations.raylib / backends.physics.pymunk
                         │
                         ▼
             integrations._bootstrap composition root
```

The package root `plyunit.__init__` owns a lazy export map. There is no
`plyunit.api` package. Input classes are exported through
`plyunit.services.input` and the root facade.

## Current boundaries

| Domain | Core-facing API | Backend boundary | Concrete implementation |
| --- | --- | --- | --- |
| Window | `App`, `Window` root export | `IWindow` | raylib `Window` |
| Camera | `Camera2D` root export | `ICamera2D` | raylib `Camera2D` |
| Canvas/rendering | `Renderer`, `DrawScope`, `RenderPass` | `ICanvas2D`, `IUnifiedBufferBatch` | raylib `Canvas`, native UBR |
| Assets | `Assets`, `Text`, `Shaders` | `IAssetsLoader`, `IFont`, `IShaderLoader` | raylib loaders/font |
| Input | `Input`, `Mouse`, `Gamepad`, `Touch` | `IInput`, `IMouse`, `IGamepad`, `ITouch` | raylib input adapters |
| Audio | `Audio` | `IAudioBackend` | raylib `AudioBackend` |
| Physics | `Physics`, body/area/shape APIs | `PhysicsBackend` adapter boundary | pymunk |
| ImGui | `ImGui` | `ImGuiBackend` | imgui-bundle/raylib backend |

Tilemap rendering no longer uses `IRenderTargetOps` or a tilemap renderer
facade. `TileMapNode` uses the configured `Renderer.canvas` for render-target
baking and submits baked chunks or tiles through `Renderer.render_sprite`.

## Composition root

`init` and `create_app` in
`src/plyunit/backends/integrations/_bootstrap.py` select concrete backends and
wire the application:

1. Resolve window, canvas, and native UBR adapters.
2. Construct `Renderer`, `SceneManager`, `Assets`, and `Animations`.
3. Call `app.init(cfg)` to initialize the window and App registry.
4. Install optional `Physics`, `ImGui`, and `Audio` services; they attach through the
   active global registry.

The current code constructs `Renderer` and calls `ubr.init()` before
`app.init(cfg)` initializes the window. This ordering is significant for native
backends that require a live graphics context.

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
SceneUnit.dispatch_render
  → NodeUnit/component render_submit
  → Renderer.render_sprite(s)       → FrameBuffer SoA
  → Renderer.render_* primitives    → typed queue
  → Renderer.render_shaped_text     → FrameBuffer/typed text path
  → Renderer.render_custom          → typed queue callback
  → Renderer.flush_all              → passes, state, native UBR, Canvas
```

There is no `RenderPipeline` enum or immediate callback scheduler. `DrawScope`
is an unrestricted Canvas helper; lifecycle control remains with the caller.

## Known boundary caveats

- `Physics` directly depends on pymunk inside its concrete backend package;
  consumers should import it through `plyunit.backends.physics` or root exports.
- `Renderer` requires the native UBR backend and fails fast without it.
- `TileMapNode` accesses `Renderer.canvas` for baking, so tilemap is coupled to
  the configured renderer abstraction rather than a separate RT protocol.
- Some public-looking deep-module types are not re-exported. Treat facade
  `__all__` lists as the stability boundary.
- Input services do not automatically poll themselves on fixed steps; apps
  using deferred input events must poll before the early EventBus dispatch.

## Source map

| Area | Current path |
| --- | --- |
| App/config | `src/plyunit/core/` |
| Unit tree/components | `src/plyunit/core/units/`, `core/components/` |
| Events | `src/plyunit/events/` |
| Renderer | `src/plyunit/rendering/` |
| Services | `src/plyunit/services/` |
| Assets/audio | `src/plyunit/assets/`, `src/plyunit/audio/` |
| Tilemap | `src/plyunit/tilemap/` |
| Backend protocols | `src/plyunit/backends/interfaces/` |
| Raylib adapters | `src/plyunit/backends/integrations/raylib/` |
| Pymunk adapter | `src/plyunit/backends/physics/pymunk/` |
| Composition root | `src/plyunit/backends/integrations/_bootstrap.py` |

## Audit conclusion

The main architecture follows dependency inversion for host I/O, rendering,
input, audio, and assets. The principal intentional concrete edges are the
pymunk implementation package, native UBR requirement, and tilemap's use of
the configured renderer Canvas. Current user documentation should use facade
exports and must not reference removed backend factories or renderer facades.
