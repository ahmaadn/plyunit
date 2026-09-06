# Panduan Node dan Rendering Efisien

> **Panduan rendering lengkap:** [rendering/index.md](rendering/index.md)  
> (pilih jalur gambar, batch, native C, layer, culling).

Dokumen ini menjelaskan cara membuat `NodeUnit` yang benar dan cara menggambar objek secara single maupun batch di plyunit.

Fokus utamanya adalah menjaga kode tetap mudah dipakai tanpa menghilangkan performa. Setelah optimasi runtime, pola yang paling cepat adalah:

- pakai `NodeUnit` untuk struktur scene, lifecycle, parent-child, dan transform;
- pakai `SpriteRenderer` untuk sprite biasa;
- pakai `renderer.render_batch()` untuk banyak sprite yang dikelola satu node/system;
- pakai `draw(canvas)` hanya untuk custom drawing yang memang membutuhkan Canvas langsung.

## 1. Prinsip Dasar

### 1.1 Pilih Jalur Render yang Tepat

| Kebutuhan | Gunakan | Catatan |
| --- | --- | --- |
| Satu sprite per node | `SpriteRenderer` | Jalur umum dan otomatis dioptimalkan. |
| Banyak sprite dengan texture/state sama | `renderer.render_batch()` | Cocok untuk particle, tile sederhana, crowd, atau spam sprite. |
| Bentuk primitive seperti rectangle/circle/line | `renderer.render_rect()`, `render_circle()`, `render_line()` | Gunakan di `render_submit()`, bukan `draw()`, jika bisa. |
| Gambar langsung ke Canvas | `draw(canvas)` + `enable_custom_draw()` | Untuk kasus khusus saja. |
| UI sprite/text | typed `render_*` dengan `Layer.UI`, serta `Text.push()` | Screen-space UI melalui layer UI. |

### 1.2 Hindari Pola Mahal

- Jangan override `draw()` untuk node yang hanya menampilkan sprite; gunakan `SpriteRenderer`.
- Jangan membuat ratusan node dengan `draw()` kosong; default `NodeUnit` tidak lagi submit custom draw.
- Jangan memberi `z_index` unik pada ribuan sprite jika urutan visual tidak membutuhkan itu.
- Jangan memakai `dest` pada `render_sprite()` kalau `pos + scale` sudah cukup.
- Untuk volume tinggi, pakai `render_batch` (atau `pos_xy=`) alih-alih N× `render_sprite`.

## 2. Membuat Node yang Benar

`NodeUnit` sebaiknya dipakai sebagai container transform dan lifecycle. Node bisa punya child dan component.

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

Hal yang benar dari contoh di atas:

- posisi diubah dengan `transform.set_position(...)`, bukan assignment langsung ke `transform.local.position`;
- sprite ditampilkan melalui `SpriteRenderer`;
- `z_index` hanya dipakai saat memang perlu urutan khusus;
- node hanya override `update()` karena memang punya logic bergerak.

## 3. Node Statis

Untuk node yang tidak bergerak dan tidak punya logic per-frame, jangan override `update()`.

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

Jika membuat banyak sprite statis dengan texture dan state yang sama, gunakan nilai `z_index` yang sama agar renderer bisa menggabungkannya menjadi batch.

```python
for i in range(500):
    tree = Tree(texture, x=float(i % 25) * 32.0, y=float(i // 25) * 32.0)
    scene.root.attach(tree)
```

## 4. Menggambar Satu Sprite dengan Component

Ini adalah cara yang direkomendasikan untuk satu sprite per node.

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

`SpriteRenderer` mendukung:

- `texture` atau `asset_key`;
- `source_rect` untuk spritesheet;
- `pivot` untuk origin rotasi;
- `flip_x` dan `flip_y`;
- `scale`;
- `layer` dan `z_index`;
- `tint`;
- `use_interpolation`.

## 5. Menggambar Satu Sprite Secara Manual

Jika node bertugas sebagai renderer/system dan tidak cocok memakai component, gunakan `render_submit()`.

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

Gunakan pola ini jika:

- sprite bukan component milik node biasa;
- node adalah renderer khusus;
- sprite hanya satu atau jumlahnya kecil;
- Anda butuh kontrol submit manual.

Untuk sprite biasa, `SpriteRenderer` tetap lebih disarankan.

## 6. Menggambar Banyak Sprite dengan Batch

Jika satu node/system mengelola banyak sprite, gunakan `render_batch()`.

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

Batch cocok untuk:

- particle sederhana;
- bullet atau projectile dengan texture sama;
- dekorasi statis;
- tile sederhana tanpa tilemap penuh;
- background sprite spam.

`render_batch` mengasumsikan material shared (texture, source, tint,
scale, rotation, origin, layer/state). Banyak `render_sprite` tetap masuk
FrameBuffer yang sama; flush UBR mengelompokkan run by `tex_id` (bukan
auto-batch submit-time). Untuk list posisi homogen, selalu prefer batch API.

## 7. Banyak `render_sprite` vs `render_batch`

Setiap `render_sprite` menulis satu baris SoA. Untuk ratusan–ribuan posisi
dengan material sama, pakai `render_batch` (+ `pos_xy` contiguous float32
untuk vectorized FrameBuffer copy).

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

## 8. Custom Drawing dengan `draw(canvas)`

`draw(canvas)` adalah escape hatch. Default `NodeUnit` tidak submit draw kosong. Jika ingin memakai `draw()`, aktifkan custom draw atau override `draw()` pada class.

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

Namun untuk shape sederhana, lebih baik submit primitive di `render_submit()`.

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

Pilih `render_submit()` untuk renderer typed karena engine masih bisa mengurutkan, mengelompokkan state, dan melakukan batching.

## 9. Layer dan Z-Index

`layer` menentukan kelompok besar urutan render. `z` atau `z_index` menentukan urutan di dalam layer.

```python
SpriteRenderer(
    texture=texture,
    layer=int(pu.Layer.ENTITIES),
    z_index=0,
)
```

Gunakan z unik hanya jika objek benar-benar harus punya urutan visual spesifik.

```python
# Baik untuk batching: semua dekorasi bisa digambar dalam urutan sama.
z_index = 0

# Pakai hanya jika perlu: objek harus selalu tersusun berdasarkan kedalaman manual.
z_index = object_depth
```

Jika butuh sorting berdasarkan posisi Y, gunakan y-sort layer atau `y_sort` sesuai fitur renderer. Perlu diingat y-sort biasanya memecah batching karena sort key berbeda.

## 10. Transform yang Disarankan

Gunakan setter transform supaya dirty tracking dan sinkronisasi world transform tetap benar.

```python
node.transform.set_position(100.0, 200.0)
node.transform.set_rotation(45.0)
node.transform.set_scale(2.0, 2.0)
```

Hindari assignment langsung untuk perubahan runtime:

```python
# Hindari untuk runtime update.
node.transform.local.position = (100.0, 200.0)
```

Assignment langsung masih bisa muncul di kode lama, tetapi setter lebih aman untuk optimasi runtime berikutnya.

## 11. Pola yang Direkomendasikan

### 11.1 Actor dengan Sprite

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

### 11.2 Static Decoration

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

### 11.3 Renderer Node untuk Banyak Data

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

## 12. Checklist Performa

Sebelum membuat banyak node atau banyak draw call, cek hal berikut:

- Apakah node statis tidak override `update()`?
- Apakah sprite biasa memakai `SpriteRenderer`, bukan `draw()`?
- Apakah banyak sprite identik memakai `render_batch()`?
- Apakah `z_index` bisa disamakan untuk sprite yang tidak perlu urutan unik?
- Apakah texture/source/tint/scale/layer/state dibuat sama untuk satu batch?
- Apakah transform runtime diubah lewat `set_position`, `set_rotation`, atau `set_scale`?
- Apakah y-sort, shader, scissor, blend mode, dan custom draw hanya dipakai saat perlu?

## 13. Ringkasan Praktis

- Untuk satu sprite node: `NodeUnit + SpriteRenderer`.
- Untuk banyak sprite data-oriented: satu node/system + `render_batch()`.
- Untuk shape/text/UI: typed renderer (`render_rect`, `Text.push`, `render_*` + `Layer.UI`).
- Untuk Canvas langsung: `draw(canvas)` hanya jika tidak ada typed renderer yang cocok.
- Untuk batch besar: `render_batch` + material shared; flush UBR group by `tex_id`.
