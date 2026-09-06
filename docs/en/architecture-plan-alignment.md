# Engine architecture summary

What already exists in plyunit, in practical language (not internal feature numbers).

## Available today

| Need | Where |
| --- | --- |
| Find global services / units | `UnitRegistry`, `ServiceUnit`, `"@Name"` queries |
| Scene registry | per-`SceneUnit` registry |
| Components per node | `add_component`, one type per node |
| Fast transforms (many nodes) | `TransformStore` per scene |
| Entity pooling | `EntityPool` + handle generations |
| Events | `Signal`, `@on`, `EventBus` (two dispatches per step when registered) |
| Many sprites, one texture | `render_batch` → FrameBuffer → `ubr_submit_frame` (`plyunit-native` required) |
| Draw ordering | pass/layer, then depth/y-sort or texture grouping depending on the layer |
| Spatial index | `SpatialIndex` (opt-in; construct manually, refreshed incrementally by the scene) |
| Off-camera culling | via SpatialIndex or AABB |
| Frame order | update → transform sync → scene transition apply → physics → late events → render |

## Performance targets (bunny)

- 8000 sprites @ ~60 FPS (strict profile)
- 10000 sprites @ ~30 FPS (strict profile)

Commands and native path: [batch-render.md](batch-render.md).

## Deliberately not done / out of scope

- Replacing pymunk broadphase with the SpatialIndex
- Storing every game sprite in a single permanent array registry
- SpatialIndex is not a default bootstrap service; create it after the App is active
- Full world matrices in the transform store
- Renaming `NodeUnit` → `Unit`

## Data policy

- **Transforms:** flat fast data while the node is in a scene
- **Sprite batches:** assembled per frame when drawn (not a global sprite registry)
- **Particles:** explicit `ParticlePool`; `ParticleEmitter` does not yet auto-update/render

## Physics → transforms

Dynamic bodies write poses through `apply_physics_state` so transforms stay
aligned.

## Document map

| Topic | Document |
| --- | --- |
| Start | [getting-started.md](getting-started.md) |
| Core | [engine-core.md](engine-core.md) |
| Frame | [frame-execution-order.md](frame-execution-order.md) |
| Render | [rendering/index.md](rendering/index.md) |
| Physics | [physics.md](physics.md) |
