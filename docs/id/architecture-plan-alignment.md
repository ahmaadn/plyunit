# Ringkasan arsitektur engine

Apa yang sudah ada di plyunit, dalam bahasa praktis (bukan nomor fitur internal).

## Sudah tersedia

| Kebutuhan | Di mana |
| --- | --- |
| Cari service / unit global | `UnitRegistry`, `ServiceUnit`, query `"@Nama"` |
| Registry scene | registry per `SceneUnit` |
| Komponen per node | `add_component`, satu tipe per node |
| Transform cepat (banyak node) | `TransformStore` per scene |
| Pool entitas | `EntityPool` + handle generation |
| Event | `Signal`, `@on`, `EventBus` (dua dispatch per step bila terdaftar) |
| Banyak sprite satu texture | `render_batch` → FrameBuffer → `ubr_submit_frame` (`plyunit-native` wajib) |
| Urutan gambar | pass/layer, lalu depth/y-sort atau texture grouping sesuai layer |
| Index spasial | `SpatialIndex` (opt-in; construct manual, refresh incremental oleh scene) |
| Culling luar kamera | lewat SpatialIndex atau AABB |
| Urutan frame | update → sync transform → apply scene transition → physics → late event → render |

## Target performa (bunny)

- 8000 sprite @ ~60 FPS (profil strict)
- 10000 sprite @ ~30 FPS (profil strict)

Perintah dan native: [batch-render.md](batch-render.md).

## Sengaja belum / di luar scope

- Ganti pymunk dengan broadphase SpatialIndex
- Menyimpan semua sprite game dalam satu registry array permanen
- SpatialIndex bukan service bootstrap default; buat setelah App aktif
- Matrix world penuh di transform store
- Rename `NodeUnit` → `Unit`

## Kebijakan data

- **Transform:** data datar cepat saat node di scene
- **Sprite batch:** disusun per frame saat digambar (bukan registry sprite global)
- **Particle:** explicit `ParticlePool`; `ParticleEmitter` belum auto-update/render

## Physics → transform

Body dynamic menulis pose lewat `apply_physics_state` agar transform tetap selaras.

## Peta dokumen

| Topik | Dokumen |
| --- | --- |
| Mulai | [getting-started.md](getting-started.md) |
| Core | [engine-core.md](engine-core.md) |
| Frame | [frame-execution-order.md](frame-execution-order.md) |
| Render | [rendering/index.md](rendering/index.md) |
| Physics | [physics.md](physics.md) |
