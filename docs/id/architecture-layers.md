# Architecture layers

`plyunit` uses ports and adapters. The source root is
`packages/plyunit/src/plyunit/`; the old `common` / `engine` / `api` layer
layout is not part of the current package.

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

| Boundary | May depend on | Must not depend on |
| --- | --- | --- |
| `core`, `events`, `rendering`, `services`, `tilemap`, `utils` | Backend-neutral data, domain modules, `backends.ports`, stdlib/numpy | Concrete backends, backend selectors, pyray/raylib, pymunk, imgui, raw OpenGL |
| `backends.ports` | Backend-neutral types and contracts | Concrete adapters, backend selection, native resource objects |
| Concrete adapters under `backends` | Ports, domain types, their vendor libraries | A reverse dependency from domain code |
| `plyunit._bootstrap` | Selected adapter factories and domain services | Moving backend selection into a domain service |
| `plyunit.__init__` | Lazy export maps | Eagerly importing optional backends on plain `import plyunit` |

## Services and resources

Neutral services/data live under `services`, including `animations.py`,
`assets/schemas.py`, `assets/atlas.py`, `spatial_index.py`, `text.py`, and
`shaders.py`. Concrete `Assets`, `Text`, `Shaders`, `Audio`, and input
implementations live under `backends/integrations/raylib`. Importing a
neutral service module does not select or wrap a backend.

Resource contracts such as `Texture2DHandle`, `RenderTextureHandle`,
`FontHandle`, and `ShaderHandle` live in `backends.ports.handler`.
The concrete raylib `Image`, `Texture2D`, `RenderTexture`, `Shader`, `Font`,
and `StreamingTexture` handles live in
`backends/integrations/raylib/handler.py`. Raw resources and native field
access belong inside adapters, not in ports or core.

`Texture2DHandle.texture_id` is a logical string asset ID. Only
`IUnifiedBufferBatch.texture_id(handle)` resolves the numeric GPU ID used by
native texture runs. Render-target, font-atlas, and streaming attachments
are borrowed; `Assets` must not adopt or free them separately.

## Composition and initialization

`plyunit._bootstrap.init` injects window/canvas/batch adapters and services,
then calls `app.init(cfg)`. `App.init` opens the window, sets up the default
camera, and only then calls `Renderer.init` to initialize native GPU resources.
Optional physics, ImGui, and audio services are constructed after
`app.init(cfg)` returns. Game loading and GPU asset creation belong in
`on_load` / `on_ready`, after bootstrap.

`Canvas2D()` is a factory returning the module-backed canvas that implements
`ICanvas2D`; it is not a canvas class to subclass or use as a type annotation.

## Guards

`packages/plyunit/tests/common/test_import_boundaries.py` checks neutral
module imports, port imports, and resource contracts. The import rules also
apply to typing-only, relative, and literal dynamic imports.

See [architecture-hexagonal-audit.md](architecture-hexagonal-audit.md) for the
source map and [migration.md](migration.md) for breaking API changes.
