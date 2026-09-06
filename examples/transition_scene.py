"""Example: Scene transition + loading di background thread.

Menunjukkan:
1. Fade transition bawaan ``SceneManager`` lewat ``request_push`` /
   ``request_pop`` / ``request_change`` (dieksekusi di tengah fade).
2. ``LoadingScene``: pekerjaan berat (simulasi load level) dijalankan di
   background thread sementara loading screen tetap dirender — progress
   bar, status per-langkah, dan spinner tetap beranimasi mulus.
3. Staged asset loading untuk 10.000 aset dalam dua fase:
   - Fase 1 (worker thread): decode/bangkit image CPU
     (``loader.load_image`` / ``gen_image_color``) → disimpan di
     ``LoadResult.raw_images``. Hanya data CPU — aman di thread.
    - Fase 2 (main thread): upload ke GPU dalam batch per frame
      (``loader.load_texture_from_image`` + ``Assets.store_texture``),
      lalu image CPU dibebaskan (``loader.unload_image``).

ATURAN THREAD-SAFETY (raylib/OpenGL):
- Worker thread HANYA boleh memanggil fungsi *image* (CPU-only):
  ``load_image``, ``gen_image_color``, ``unload_image``.
- SEMUA fungsi *texture* (``load_texture*``, ``unload_texture``,
  ``set_texture_filter``) wajib main thread — OpenGL context hanya
  dimiliki main thread.
- Worker tidak menyentuh renderer/window/scene; hasil akhirnya berupa
  data Python murni di ``LoadResult``.

Kontrol:
- SPACE: push scene ringan (transisi fade langsung)
- ENTER: ganti ke scene berat via loading screen (background thread)
- BACKSPACE: kembali / batalkan loading
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import pyray as pr

import plyunit as pu
from plyunit.backends.integrations import AssetsLoader

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600

ASSET_COUNT = 10_000
TILE_SIZE = 16
UPLOAD_BATCH = 500

STAR_COLORS: tuple[tuple[int, int, int, int], ...] = (
    (155, 180, 255, 255),
    (255, 230, 160, 255),
    (160, 255, 200, 255),
    (255, 160, 160, 255),
    (200, 200, 215, 255),
)

Star = tuple[float, float, float, float, tuple[int, int, int, int]]

# Bobot progress: dekode CPU (worker) 70%, upload GPU (main) 30%.
_DECODE_WEIGHT = 0.7
_UPLOAD_WEIGHT = 0.3


def _cpu_burn(seconds: float) -> None:
    """Beban CPU murni untuk simulasi proses berat (bukan I/O)."""
    deadline = time.perf_counter() + seconds
    value = 1
    while time.perf_counter() < deadline:
        for i in range(500):
            value = (value * 31 + i) % 1_000_003


@dataclass(frozen=True)
class LoadResult:
    """Data hasil load berat — dibuat worker, dikonsumsi scene target.

    ``raw_images`` menampung image CPU (belum jadi texture GPU) untuk
    di-upload main thread pada fase 2. Texture GPU TIDAK PERNAH dibuat
    di worker thread.
    """

    stars: list[Star]
    grid: dict[tuple[int, int], list[int]]
    raw_images: list[tuple[str, Any]] = field(default_factory=list)
    asset_prefix: str = "tile"
    elapsed: float = 0.0


class LoadJob:
    """Pekerjaan berat yang aman dijalankan di background thread.

    Worker memanggil :meth:`run` dan hanya menulis state job lewat lock.
    Main thread membaca ``progress`` / ``status`` / ``done`` / ``result``
    dari property yang juga dilindungi lock.
    """

    def __init__(self, star_count: int = 700, loader: Any = None) -> None:
        self._lock = threading.Lock()
        self._progress = 0.0
        self._status = "Menyiapkan..."
        self._done = False
        self._error: BaseException | None = None
        self._cancel = threading.Event()
        self._star_count = star_count
        self._loader = loader if loader is not None else AssetsLoader()
        self.result: LoadResult | None = None

    @property
    def progress(self) -> float:
        with self._lock:
            return self._progress

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done

    @property
    def error(self) -> BaseException | None:
        with self._lock:
            return self._error

    def cancel(self) -> None:
        """Minta worker berhenti (dicek antar langkah, bukan mid-langkah)."""
        self._cancel.set()

    def _report(self, progress: float, status: str) -> None:
        with self._lock:
            self._progress = progress
            self._status = status

    def run(self) -> None:
        """Body worker thread: eksekusi langkah-langkah load berat."""
        start = time.perf_counter()
        try:
            steps: tuple[tuple[str, Callable[[dict], None]], ...] = (
                ("Membaca konfigurasi level", self._step_config),
                ("Membangkitkan starfield", self._step_stars),
                ("Membangun spatial grid", self._step_grid),
                ("Memuat aset (simulasi I/O)", self._step_assets),
                ("Finalisasi", self._step_finalize),
            )
            payload: dict = {}
            for index, (label, step_fn) in enumerate(steps):
                if self._cancel.is_set():
                    return
                self._report(index / len(steps), label)
                step_fn(payload)
                self._report((index + 1) / len(steps), f"{label} — OK")

            self.result = LoadResult(
                stars=payload["stars"],
                grid=payload["grid"],
                raw_images=payload.get("raw_images", []),
                elapsed=time.perf_counter() - start,
            )
        except BaseException as exc:  # worker tidak boleh mematikan app
            with self._lock:
                self._error = exc
        finally:
            with self._lock:
                self._done = True

    def _step_config(self, payload: dict) -> None:
        _cpu_burn(0.10)
        payload["config"] = {"seed": 20260902, "grid_cell": 64}

    def _step_stars(self, payload: dict) -> None:
        config = payload["config"]
        rng = random.Random(config["seed"])
        stars: list[Star] = []
        for _ in range(self._star_count):
            stars.append((
                rng.uniform(0.0, float(WINDOW_WIDTH)),
                rng.uniform(0.0, float(WINDOW_HEIGHT)),
                rng.uniform(1.5, 3.5),
                rng.uniform(6.0, 42.0),
                rng.choice(STAR_COLORS),
            ))
        _cpu_burn(0.20)
        payload["stars"] = stars

    def _step_grid(self, payload: dict) -> None:
        cell = payload["config"]["grid_cell"]
        grid: dict[tuple[int, int], list[int]] = {}
        for index, (x, y, _size, _speed, _color) in enumerate(payload["stars"]):
            grid.setdefault((int(x // cell), int(y // cell)), []).append(index)
        _cpu_burn(0.15)
        payload["grid"] = grid

    def _step_assets(self, payload: dict) -> None:
        """Bangkitkan 10.000 image CPU (fase 1 — aman di worker thread).

        Di game nyata, ganti dengan ``self._loader.load_image(path)`` per
        file aset. ``gen_image_color`` dipakai di sini sebagai simulasi
        decode yang tidak butuh file di disk.
        """
        rng = random.Random(99)
        raw_images: list[tuple[str, Any]] = []
        for index in range(ASSET_COUNT):
            if self._cancel.is_set():
                return
            base = rng.choice(STAR_COLORS)
            color = (
                max(0, base[0] - rng.randint(0, 60)),
                max(0, base[1] - rng.randint(0, 60)),
                max(0, base[2] - rng.randint(0, 60)),
                255,
            )
            image = self._loader.gen_image_color(TILE_SIZE, TILE_SIZE, color)
            raw_images.append((f"tile_{index:05d}", image))
            if index % 1000 == 0:
                # Beri kesempatan progress terlihat menaik (dan GIL pindah).
                self._report(
                    self._progress + 0.0,
                    f"Decode aset {index}/{ASSET_COUNT}",
                )
        payload["raw_images"] = raw_images

    def _step_finalize(self, payload: dict) -> None:
        _ = payload
        _cpu_burn(0.08)


class MovingShapeUnit(pu.NodeUnit):
    """Bentuk yang memantul di batas layar (kinematika manual)."""

    def __init__(
        self,
        *,
        name: str,
        shape_kind: str,
        start_pos: tuple[float, float],
        velocity: tuple[float, float],
        size: tuple[float, float],
        color: tuple[int, int, int, int],
    ) -> None:
        super().__init__(name=name)
        self.shape_kind = shape_kind
        self.width = float(size[0])
        self.height = float(size[1])
        self.color = color
        self.velocity: list[float] = [velocity[0], velocity[1]]
        self.transform.set_position(start_pos[0], start_pos[1])

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        vx, vy = self.velocity
        x += vx * dt
        y += vy * dt

        if x < 0.0:
            x = 0.0
            vx = abs(vx)
        elif (x + self.width) > WINDOW_WIDTH:
            x = WINDOW_WIDTH - self.width
            vx = -abs(vx)

        if y < 0.0:
            y = 0.0
            vy = abs(vy)
        elif (y + self.height) > WINDOW_HEIGHT:
            y = WINDOW_HEIGHT - self.height
            vy = -abs(vy)

        self.velocity = [vx, vy]
        self.transform.set_position(x, y)

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        x, y = self.world_transform_lerp().position
        if self.shape_kind == "circle":
            radius = min(self.width, self.height) * 0.5
            canvas.draw_circle(
                center=(x + radius, y + radius), radius=radius, color=self.color
            )
        else:
            canvas.draw_rectangle(
                rect=(x, y, self.width, self.height), color=self.color
            )


class StarfieldNode(pu.NodeUnit):
    """Menggambar starfield hasil background load (drift parallax ringan)."""

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="Starfield")
        self.layer = pu.Layer.BACKGROUND
        self.stars = result.stars
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        for x, y, size, speed, color in self.stars:
            dx = (x + self._time * speed) % WINDOW_WIDTH
            canvas.draw_rectangle(rect=(dx, y, size, size), color=color)


class _LoadingState:
    """State loading screen yang dibagikan scene (penulis) dan overlay (pembaca)."""

    def __init__(self) -> None:
        self.progress = 0.0
        self.status = "Menyiapkan..."


class LoadingOverlay(pu.NodeUnit):
    """UI loading screen: progress bar, status, dan spinner."""

    def __init__(self, state: _LoadingState) -> None:
        super().__init__(name="LoadingOverlay")
        self.layer = pu.Layer.OVERLAY
        self.state = state
        self._time = 0.0
        self._display_progress = 0.0

    def update(self, dt: float) -> None:
        self._time += dt
        target = self.state.progress
        self._display_progress += (target - self._display_progress) * min(1.0, dt * 8.0)

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        w = float(WINDOW_WIDTH)
        h = float(WINDOW_HEIGHT)
        px = w / 2 - 230
        py = h / 2 - 95
        progress = self._display_progress

        # Gelapkan layar + panel
        canvas.draw_rectangle(rect=(0, 0, w, h), color=(8, 10, 18, 235))
        canvas.draw_rectangle(
            rect=(px, py, 460, 190), color=(26, 30, 48, 255), roundness=0.06, segments=8
        )
        canvas.draw_rectangle(
            rect=(px, py, 460, 190),
            color=(90, 110, 190, 255),
            outline_only=True,
            thickness=2.0,
        )

        # Judul + spinner
        canvas.draw_text(
            text="MEMUAT LEVEL",
            pos=(px + 24, py + 20),
            font_size=24,
            color=(235, 240, 255, 255),
        )
        angle = self._time * 6.0
        cx = px + 460 - 40
        cy = py + 34
        dx = math.cos(angle) * 12.0
        dy = math.sin(angle) * 12.0
        canvas.draw_line(
            start=(cx - dx, cy - dy), end=(cx + dx, cy + dy), color=(120, 190, 255, 255)
        )

        # Status langkah
        canvas.draw_text(
            text=self.state.status,
            pos=(px + 24, py + 64),
            font_size=15,
            color=(160, 175, 210, 255),
        )

        # Progress bar
        bar = (px + 24, py + 104, 412, 16)
        canvas.draw_rectangle(
            rect=bar, color=(90, 110, 190, 255), outline_only=True, thickness=2.0
        )
        if progress > 0.0:
            canvas.draw_rectangle(
                rect=(bar[0], bar[1], bar[2] * progress, bar[3]),
                color=(90, 200, 140, 255),
            )
        canvas.draw_text(
            text=f"{progress * 100:.0f}%",
            pos=(px + 24, py + 128),
            font_size=13,
            color=(140, 150, 180, 255),
        )

        canvas.draw_text(
            text="BACKSPACE: batalkan",
            pos=(px + 24, py + 158),
            font_size=13,
            color=(110, 120, 150, 255),
        )


class LoadingScene(pu.SceneUnit):
    """Loading screen dua fase: decode CPU di thread, upload GPU di main.

    Fase 1 (``"loading"``): worker thread menjalankan ``LoadJob`` —
    decode image CPU. Progress = ``_DECODE_WEIGHT * job.progress``.

    Fase 2 (``"uploading"``): main thread meng-upload image CPU ke GPU
    dalam batch ``UPLOAD_BATCH`` per fixed step lewat
    ``loader.load_texture_from_image`` + ``Assets.store_texture``,
    lalu membebaskan image CPU (``loader.unload_image``). Fungsi texture
    wajib main thread — inilah alasan upload tidak dilakukan worker.

    Saat semua aset ter-upload, request ``change`` ke scene target.
    Jika scene ini di-unload lebih awal (dibatalkan), worker di-cancel,
    di-join, dan aset yang sudah ter-upload dibersihkan dari cache.
    """

    def __init__(self, target_factory: Callable[[LoadResult], pu.SceneUnit]) -> None:
        super().__init__(name="LoadingScene")
        self._target_factory = target_factory
        self._job: LoadJob | None = None
        self._thread: threading.Thread | None = None
        self._state = _LoadingState()
        self._phase = "loading"
        self._raw_images: list[tuple[str, Any]] = []
        self._uploaded: list[str] = []
        self._switching = False

    def on_load(self) -> None:
        print("LoadingScene: worker thread dimulai")
        self._job = LoadJob()
        self._thread = threading.Thread(
            target=self._job.run, name="scene-loader", daemon=True
        )
        self._thread.start()
        self.root.attach(LoadingOverlay(self._state))

    def update(self, dt: float) -> None:
        _ = dt
        if self._switching:
            return

        if self._phase == "loading":
            self._update_loading()
        elif self._phase == "uploading":
            self._update_uploading()

    def _update_loading(self) -> None:
        job = self._job
        if job is None or not job.done:
            if job is not None:
                self._state.progress = _DECODE_WEIGHT * job.progress
                self._state.status = job.status
            return

        manager = self.one_or_none("@SceneManager", scope="global")
        if manager is None:
            return

        if job.error is not None or job.result is None:
            print(f"LoadingScene: load gagal ({job.error!r}) — kembali ke menu")
            self._switching = True
            manager.request_change(MenuScene)
            return

        result = job.result
        if not result.raw_images:
            # Tidak ada aset untuk di-upload — langsung pindah.
            self._switching = True
            manager.request_change(partial(self._target_factory, result))
            return

        self._raw_images = result.raw_images
        self._phase = "uploading"

    def _update_uploading(self) -> None:
        job = self._job
        if job is None or job.result is None:
            return

        assets = self.one_or_none("@Assets", scope="global")
        if assets is None:
            print("LoadingScene: service Assets tidak ditemukan — langsung pindah")
            self._switching = True
            self._request_target()
            return

        total = len(self._raw_images)
        batch = self._raw_images[
            len(self._uploaded) : len(self._uploaded) + UPLOAD_BATCH
        ]

        for asset_id, image in batch:
            # GPU upload — main thread saja (OpenGL context).
            texture = job._loader.load_texture_from_image(image)
            assets.store_texture(asset_id, texture)
            # Image CPU sudah tidak terpakai — bebaskan memorinya.
            job._loader.unload_image(image)
            self._uploaded.append(asset_id)

        uploaded_count = len(self._uploaded)
        self._state.progress = _DECODE_WEIGHT + _UPLOAD_WEIGHT * (
            uploaded_count / max(1, total)
        )
        self._state.status = f"Upload GPU {uploaded_count}/{total}"

        if uploaded_count >= total:
            print(
                f"LoadingScene: {total} aset ter-upload ke GPU ({UPLOAD_BATCH}/frame)"
            )
            self._switching = True
            self._request_target()

    def _request_target(self) -> None:
        manager = self.one_or_none("@SceneManager", scope="global")
        if manager is None:
            return
        result = self._job.result if self._job is not None else None
        if result is None:
            manager.request_change(MenuScene)
        else:
            manager.request_change(partial(self._target_factory, result))

    def on_unload(self) -> None:
        if self._job is not None:
            self._job.cancel()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._uploaded and not self._switching:
            # Dibatalkan di tengah upload — bersihkan aset yang sudah masuk.
            assets = self.one_or_none("@Assets", scope="global")
            if assets is not None:
                for asset_id in self._uploaded:
                    assets.unload_asset(asset_id)
            print(f"LoadingScene: {len(self._uploaded)} aset dibersihkan (cancel)")
        print("LoadingScene: worker dihentikan")


class MenuScene(pu.SceneUnit):
    """Scene menu awal."""

    def __init__(self) -> None:
        super().__init__(name="MenuScene")

    def on_load(self) -> None:
        print("MenuScene loaded")
        self.root.attach(
            MovingShapeUnit(
                name="MenuRect",
                shape_kind="rectangle",
                start_pos=(120.0, 120.0),
                velocity=(170.0, 130.0),
                size=(150.0, 110.0),
                color=(70, 130, 200, 255),
            )
        )
        self.root.attach(
            MovingShapeUnit(
                name="MenuCircle",
                shape_kind="circle",
                start_pos=(500.0, 300.0),
                velocity=(-140.0, 170.0),
                size=(120.0, 120.0),
                color=(90, 190, 150, 255),
            )
        )

    def on_unload(self) -> None:
        print("MenuScene unloaded")


class LightScene(pu.SceneUnit):
    """Scene ringan — transisi fade langsung tanpa loading."""

    def __init__(self) -> None:
        super().__init__(name="LightScene")

    def on_load(self) -> None:
        print("LightScene loaded")
        self.root.attach(
            MovingShapeUnit(
                name="LightRect",
                shape_kind="rectangle",
                start_pos=(100.0, 100.0),
                velocity=(210.0, 160.0),
                size=(200.0, 150.0),
                color=(200, 80, 90, 255),
            )
        )
        self.root.attach(
            MovingShapeUnit(
                name="LightCircle",
                shape_kind="circle",
                start_pos=(100.0, 100.0),
                velocity=(150.0, 220.0),
                size=(160.0, 160.0),
                color=(255, 150, 80, 255),
            )
        )

    def on_unload(self) -> None:
        print("LightScene unloaded")


class TileMosaicNode(pu.NodeUnit):
    """Mosaik bukti 10.000 texture GPU sudah terdaftar di service Assets."""

    COLS = 40
    ROWS = 25
    CELL = 16
    GAP = 2

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="TileMosaic")
        self.layer = pu.Layer.WORLD
        self.asset_ids = [asset_id for asset_id, _image in result.raw_images]
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def render_submit(self, renderer) -> None:
        # Sampling grid berputar dari 10.000 aset ter-register.
        offset = int(self._time * 30) % len(self.asset_ids)
        cell = self.CELL + self.GAP
        origin_x = (WINDOW_WIDTH - self.COLS * cell) * 0.5
        origin_y = (WINDOW_HEIGHT - self.ROWS * cell) * 0.5 + 30

        assets = self.one_or_none("@Assets", scope="global")
        if assets is None:
            return
        for row in range(self.ROWS):
            for col in range(self.COLS):
                index = (offset + row * self.COLS + col) % len(self.asset_ids)
                t_data = assets.get_texture_data(self.asset_ids[index])
                renderer.render_sprite(
                    texture=t_data.texture,
                    z=0,
                    layer=pu.Layer.WORLD,
                    dest=(
                        origin_x + col * cell,
                        origin_y + row * cell,
                        float(self.CELL),
                        float(self.CELL),
                    ),
                )


class HeavyScene(pu.SceneUnit):
    """Scene hasil load berat — dibangun setelah worker + upload selesai."""

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="HeavyScene")
        self.result = result
        self.load_stats = (
            f"Level termuat: {len(result.stars)} bintang, "
            f"{len(result.grid)} sel grid, {len(result.raw_images)} aset GPU "
            f"dalam {result.elapsed:.2f}s (background)"
        )

    def on_load(self) -> None:
        print("HeavyScene loaded")
        self.root.attach(StarfieldNode(self.result))
        self.root.attach(TileMosaicNode(self.result))
        self.root.attach(
            MovingShapeUnit(
                name="HeavyRect",
                shape_kind="rectangle",
                start_pos=(80.0, 80.0),
                velocity=(190.0, 140.0),
                size=(180.0, 120.0),
                color=(120, 110, 220, 255),
            )
        )

    def on_unload(self) -> None:
        # Aset milik scene ini — bebaskan dari cache saat keluar.
        assets = self.one_or_none("@Assets", scope="global")
        if assets is not None:
            for asset_id, _image in self.result.raw_images:
                assets.unload_asset(asset_id)
        print("HeavyScene unloaded")


class TransitionApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.input.map("push_light", pr.KeyboardKey.KEY_SPACE)
        self.input.map("load_heavy", pr.KeyboardKey.KEY_ENTER)
        self.input.map("back", pr.KeyboardKey.KEY_BACKSPACE)

        self.scene_manager.push(MenuScene())
        self.scene_manager.apply_pending()
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        manager = self.scene_manager
        current = manager.current

        if self.input.is_pressed("push_light"):
            manager.request_push(LightScene)
        elif self.input.is_pressed("load_heavy"):
            manager.request_change(lambda: LoadingScene(HeavyScene))
        elif self.input.is_pressed("back") and not isinstance(current, MenuScene):
            if manager.depth > 1:
                manager.request_pop()
            else:
                manager.request_change(MenuScene)

        manager.update(dt)
        manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)

        behavior = self.scene_manager.transition_behavior
        lines = [
            "SPACE: scene ringan | ENTER: scene berat (loading di background)"
            " | BACKSPACE: kembali",
            f"stack depth: {self.scene_manager.depth}"
            f" | transisi: {behavior.state if behavior is not None else 'idle'}",
        ]
        stats = getattr(self.scene_manager.current, "load_stats", None)
        if stats:
            lines.append(stats)
        for i, line in enumerate(lines):
            self.text.render(
                z=0,
                layer=pu.Layer.UI,
                text=line,
                pos=(12.0, 12.0 + i * 20.0),
                font_size=15,
                color=(225, 228, 240, 255),
            )

        # Fade overlay dari transition behavior (digambar di atas UI)
        if behavior is not None and behavior.alpha > 0.0:
            alpha = int(min(255.0, behavior.alpha))
            self.renderer.render_rect(
                z=0,
                layer=pu.Layer.OVERLAY,
                rect=(0.0, 0.0, float(WINDOW_WIDTH), float(WINDOW_HEIGHT)),
                color=(0, 0, 0, alpha),
            )

        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        TransitionApp(),
        pu.AppConfig(
            title="Transition Scene + Background Loading",
            window_width=WINDOW_WIDTH,
            window_height=WINDOW_HEIGHT,
            background_color=(16, 18, 28, 255),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
