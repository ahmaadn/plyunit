# Physics

Integrasi **pymunk** lewat service `Physics`. Opt-in; tidak wajib untuk game pure render.

**Deps:** `uv sync --package plyunit --extra physics` (workspace; belum di PyPI)
**Contoh:** `uv run --package plyunit plyunit-physics` · `examples/example_physics.py`

## 1. Enable

```python
app = pu.init(
    MyApp(),
    pu.AppConfig(
        physics=pu.PhysicsConfig(
            enabled=True,
            gravity=(0.0, 900.0),
            iterations=10,
            enable_spatial_hash=True,
            spatial_hash_dim=100.0,
        ),
    ),
)
```

Saat `enabled=True`, bootstrap:

1. Memanggil `build_physics_service`
2. Membuat `Physics(...)` while the App is active
3. Registry invokes `on_attach`, connecting **`App.on_fixed_update` → `Physics.step`**

### Jangan

```python
# BURUK — double step
def update(self, dt):
    self.one("@Physics").step(dt)
```

## 2. Frame order (physics)

```
update tree (mutate transforms)
TransformStore.sync()
on_fixed_update → Physics.step:
  pre_sync  (kinematic / areas track transform)
  pymunk.step
  post_sync (dynamic → apply_physics_state on Transform)
render (world_transform_lerp for smooth motion)
```

Detail: [frame-execution-order.md](frame-execution-order.md).

## 3. Tiga jenis geometry

| Jenis | API | Scene tree? |
| --- | --- | --- |
| Dynamic / kinematic body | `PhysicsBody` component on `NodeUnit` | Ya |
| Sensor area | `PhysicsArea` component | Ya |
| Static world | `StaticBody` + `physics.add_static` | **Tidak** |

### Dynamic body

```python
body = pu.PhysicsBody.dynamic(mass=1.0)
body.add_shape(pu.BoxShape(width=32, height=32, friction=0.6, elasticity=0.3))
body.filter.set_layer_bit(1, True)  # "I am on layer 1"
body.filter.set_mask_bit(0, True)  # "I collide with layer 0"

node = pu.NodeUnit(name="Box")
node.transform.set_position(100, 50)
node.add_component(body)
scene.root.attach(node)
# Registers when the PhysicsBody component enters the scene tree
```

### Kinematic

```python
body = pu.PhysicsBody.kinematic()
body.add_shape(pu.BoxShape(width=120, height=16))
# Move via transform; engine drives velocity toward target each step
```

### StaticBody (floor, walls)

```python
physics = scene.one("@Physics", scope="global")
physics.add_static(
    pu.StaticBody(
        position=(400.0, 560.0),
        shapes=[pu.BoxShape(width=760, height=32)],
        filter=pu.CollisionFilter(...),  # optional
    )
)
# Batch: physics.add_static_batch([...])
# Cleanup: physics.remove_static / clear_statics
```

### Sensor area

```python
area = pu.PhysicsArea.sensor()
area.add_shape(pu.BoxShape(width=64, height=64))
# signals: on_body_entered / on_body_exited (see PhysicsArea API)
node.add_component(area)
```

## 4. Shapes

| Class | Use |
| --- | --- |
| `BoxShape(width, height, …)` | Axis box (offset, friction, elasticity, is_sensor) |
| `CircleShape(radius, …)` | Circle |
| `SegmentShape` | Edge / thin wall |
| `PolygonShape` | Convex poly |

Angles di API publik: **derajat** (internal pymunk: radians).

## 5. Collision layers (Godot-style bits)

```python
LAYER_WORLD = 0
LAYER_PLAYER = 1
LAYER_ENEMY = 2

filt = pu.CollisionFilter()
filt.set_layer_bit(LAYER_PLAYER, True)  # who I am
filt.set_mask_bit(LAYER_WORLD, True)  # who I hit
filt.set_mask_bit(LAYER_ENEMY, True)

body.filter = filt
```

Presets (import dari `plyunit`): `WORLD_STATIC`, `DYNAMIC_ACTOR`, `SENSOR`, `PROJECTILE`, …

## 6. Forces & state

```python
body.apply_force(fx, fy)
body.apply_impulse(ix, iy)
body.velocity = (vx, vy)
body.angular_velocity = deg_per_sec
body.wake() / body.sleep()
body.is_sleeping
```

Collision signals (body):

```python
body.on_collision_enter.connect(handler)  # CollisionInfo
body.on_collision_exit.connect(handler)
```

## 7. Queries

```python
physics = self.one("@Physics", scope="global")
physics.point_query(x, y, max_distance=0, filter=None)
physics.ray_cast(start, end, radius=0, filter=None)
physics.area_query(aabb, filter=None)
physics.query_aabb_fast(aabb)
```

## 8. Debug draw

```python
node.add_component(
    pu.PhysicsDebugDraw(
        draw_bodies=True,
        draw_statics=True,
        draw_areas=True,
        draw_contacts=True,
    )
)
# toggle: component.enabled = False
```

Submit ke pass debug (tinggi z). Contoh keyboard **D** di `example_physics.py`.

## 9. Render + physics

Dynamic pose di-write ke transform **setelah** step. Untuk visual mulus:

```python
world = node.world_transform_lerp()  # uses Window.alpha
canvas.draw_rectangle(rect=(...), rotation=world.rotation, origin=(...))
```

Jangan mengasumsikan `transform.world` di `update` sudah final physics frame yang sama sebelum step — step ada di `on_fixed_update` **setelah** update tree.

## 10. Tilemap physics

`TileMapNode` + physics baker/bridge dapat spawn static collision dari map.
Contoh: `plyunit-tilemap-physics` · [assets-tilemap-particles.md](assets-tilemap-particles.md).

## 11. Gotchas

| Issue | Fix |
| --- | --- |
| Body tidak collides | Set layer **dan** mask bits |
| Body tidak register | Pastikan node dan component sudah masuk scene tree |
| Static “node” | Gunakan `StaticBody`, bukan NodeUnit kosong |
| Double step | Jangan `step` di `update` |
| Scene reload leaks | `clear_statics` / destroy bodies on unload |
| Sleeping “stuck” | `wake()` setelah impulse |

## 12. API map cepat

```
Physics
  step / set_gravity / body_count
  register_body / unregister_body
  add_static / add_static_batch / clear_statics
  register_area / unregister_area
  point_query / ray_cast / area_query

PhysicsBody.dynamic() / .kinematic()
PhysicsArea.sensor()
StaticBody(position, shapes, filter=)
PhysicsDebugDraw(...)
BoxShape / CircleShape / SegmentShape / PolygonShape
CollisionFilter / CollisionInfo / BodyType
```
