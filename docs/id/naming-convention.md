# plyunit Naming Convention

> Index: [index.md](index.md)

Dokumen ini adalah acuan penamaan untuk seluruh paket `plyunit`.
Tujuannya sederhana: satu konsep harus punya satu nama canonical, supaya API engine tidak membingungkan saat dipakai maupun dirawat.

## 1. Prinsip Dasar

- Pakai satu istilah untuk satu konsep. Jangan campur sinonim untuk hal yang sama.
- Nama public harus mencerminkan perilaku dari sisi pengguna engine.
- Helper internal wajib dibedakan dengan prefix `_`.
- Hindari nama yang terlalu umum seperti `data`, `value`, `temp`, atau `current` kalau konteksnya belum jelas.
- Kalau ada typo atau ejaan yang meragukan, perbaiki sekarang. Nama API yang salah eja akan dibawa terus ke kode baru.

## 2. Lifecycle dan Hook

### 2.1 Hook berulang per frame

Pakai nama berikut untuk callback yang dipanggil terus-menerus setiap frame atau setiap fixed step:

- `update(dt)` for fixed-step node, component, scene, and application logic.
- `fixed_update(dt, step)` for application fixed-step simulation.
- `update(dt)` for application per-frame work (the render pipeline).
- `render_submit(queue)` untuk menaruh draw call ke render queue (node/scene level).
- `draw(canvas)` untuk operasi gambar final di level canvas / renderer.

Aturan praktis:

- Do not add alternate names such as `on_update` or `on_render_submit` when the canonical hook already exists.
- `update` adalah nama canonical untuk loop logic.
- `render_submit` adalah nama canonical untuk tahap submit render.

### 2.2 Callback satu kali atau event-style

Pakai prefix `on_` hanya untuk kejadian yang bersifat satu kali atau callback dari sistem event:

- `on_load`
- `on_unload`
- `on_enter_tree`
- `on_exit_tree`
- `on_attach`
- `on_start`
- `on_destroy`

Aturan praktis:

- Kalau method merepresentasikan kejadian, pakai `on_`.
- Kalau method merepresentasikan loop berulang, jangan pakai `on_`.
- Kalau method itu cuma dispatcher internal dari engine, lebih aman pakai prefix `_`.

### 2.3 Internal dispatcher

Kalau engine perlu memanggil hook publik sambil menjalankan traversal / orkestrasi internal, gunakan helper privat seperti:

- `_dispatch_update`
- `dispatch_render`
- `_attach_subtree`
- `_detach_subtree`
- `_destroy_subtree`
- `_apply_pending`

Tujuannya supaya API publik tetap bersih, sementara logika traversal tetap jelas milik engine.

## 3. Nama Variable dan Field

- Pakai noun yang spesifik, bukan sinonim acak.
- Kalau menyimpan nama animasi yang sedang aktif, pakai `current_clip_name`.
- Kalau menyimpan indeks frame, pakai `frame_index`.
- Kalau menyimpan posisi target, pakai `target_position`.
- Kalau menyimpan tree state, pakai nama yang menunjukkan domainnya, misalnya `active_tree` atau `visible_tree`.

Aturan praktis:

- Hindari pasangan seperti `current` dan `clip_name` dipakai bersamaan untuk konsep yang sama.
- Hindari campuran `index_frame` dan `frame_index`.
- Hindari `value` kalau nama domain yang lebih spesifik tersedia.
- Gunakan plural untuk koleksi: `children`, `clips`, `groups`, `actions`.

## 4. Nama Method

### 4.1 Mutator

Pakai prefix berikut untuk method yang mengubah state:

- `set_` untuk mengganti nilai.
- `add_` untuk menambahkan item.
- `remove_` untuk menghapus item.
- `load_` untuk memuat data.
- `save_` untuk menyimpan data.

### 4.2 Query

Pakai pola ini untuk method pencarian dan lookup:

- `get_` untuk mengambil satu nilai yang jelas.
- `find_` untuk pencarian yang mengembalikan list atau hasil lebih dari satu.
- `group` boleh dipakai sebagai query list jika sudah menjadi vocabulary domain yang konsisten.
- `one` untuk hasil tepat satu.
- `one_or_none` untuk hasil satu atau `None`.

### 4.3 Predicate

Pakai prefix berikut untuk method boolean:

- `is_` untuk status.
- `has_` untuk kepemilikan.
- `can_` untuk kemampuan.
- `should_` untuk keputusan berbasis aturan.

### 4.4 Helper internal

- Pakai prefix `_` untuk helper algoritmik, cache, traversal, dan bridge ke API publik.
- Jangan expose helper internal sebagai bagian dari contract user kecuali memang diperlukan.

## 5. Nama Parameter

Gunakan nama parameter yang konsisten lintas repo:

- `dt` untuk delta time.
- `queue` untuk render queue.
- `canvas` untuk canvas final.
- `unit` untuk node/unit yang sedang diproses.
- `component` untuk komponen.
- `scene_factory` untuk factory scene.

Aturan praktis:

- Jangan ganti nama parameter untuk konsep yang sama tanpa alasan yang kuat.
- Kalau nama parameter sudah punya makna yang mapan di engine, pertahankan.

## 6. Standard plyunit

- `NodeUnit`, `SceneUnit`, and `Component` use `update` and `render_submit` as recurring hooks.
- `SceneUnit` uses `_dispatch_update` and `dispatch_render` for engine orchestration.
- `App` uses `_fixed_step` internally and exposes `fixed_update` and `update` as the two mandatory extension hooks.
- `SceneManager` hanya meneruskan lifecycle ke scene aktif.

## 7. Anti-Pattern yang Harus Dihindari

- `render_sumbit` harus selalu ditulis `render_submit`.
- `transision` harus selalu ditulis `transition`.
- Jangan campur Inggris dan Indonesia di identifier yang sama.
- Jangan pakai nama yang terlalu generik kalau konteks domain sudah jelas.

## 8. Checklist Sebelum Menamai Method atau Field Baru

- Apakah ini hook publik atau helper internal?
- Apakah ini per-frame hook, event satu kali, atau query?
- Apakah ini boolean, koleksi, atau nilai tunggal?
- Apakah konsep ini sudah punya nama canonical di kode lain?
- Apakah nama ini akan tetap jelas saat dibaca 6 bulan lagi?

Kalau jawabannya belum jelas, pilih nama yang lebih spesifik, bukan yang lebih pendek.
