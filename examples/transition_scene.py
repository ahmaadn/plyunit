"""Demonstrate scene transitions with background CPU image loading.

``SceneManager`` applies push, pop, and change requests during a fade.
``LoadingScene`` keeps its progress display animated while a worker generates
10,000 image handles. The main thread uploads them with ``Assets.load_from_image``
in bounded batches and releases the CPU images after each upload.

Only CPU image operations run in the worker. Textures, rendering, window access,
and scene changes stay on the main thread that owns the OpenGL context.

Controls:
    Space: Push a lightweight scene with a fade.
    Enter: Load the heavy scene through a loading screen.
    Backspace: Go back or cancel loading.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import pyray as pr

import plyunit as pu
from plyunit.backends.ports.assets import IAssets, IImageProcessor
from plyunit.backends.ports.handler import ImageHandle
from plyunit.backends.ports.renderer import ICanvas2D

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

# Progress weights: CPU decoding (worker) 70%, GPU upload (main thread) 30%.
_DECODE_WEIGHT = 0.7
_UPLOAD_WEIGHT = 0.3


def _cpu_burn(seconds: float) -> None:
    """Simulate CPU-bound loading work without performing I/O."""
    deadline = time.perf_counter() + seconds
    value = 1
    while time.perf_counter() < deadline:
        for i in range(500):
            value = (value * 31 + i) % 1_000_003


@dataclass(frozen=True)
class LoadResult:
    """Transfer CPU loading results from the worker to the target scene.

    Attributes:
        stars: Generated starfield data.
        grid: Spatial cells containing star indices.
        images: Asset IDs and CPU image handles awaiting main-thread upload.
            Released images are replaced with ``None`` to prevent double frees.
        asset_prefix: Prefix identifying assets created for this scene.
        elapsed: Worker execution time in seconds.
    """

    stars: list[Star]
    grid: dict[tuple[int, int], list[int]]
    images: list[tuple[str, ImageHandle | None]] = field(default_factory=list)
    asset_prefix: str = "tile"
    elapsed: float = 0.0


class LoadJob:
    """Run CPU loading work in a worker and publish progress under a lock.

    The main thread reads ``result`` only after ``done`` becomes true.
    """

    def __init__(
        self, star_count: int = 700, image_processor: IImageProcessor | None = None
    ) -> None:
        self._lock = threading.Lock()
        self._progress = 0.0
        self._status = "Preparing..."
        self._done = False
        self._error: BaseException | None = None
        self._cancel = threading.Event()
        self._star_count = star_count
        if image_processor is None:
            from plyunit.backends.integrations.raylib.assets import ImageProcessor

            image_processor = ImageProcessor()
        self.image_processor: IImageProcessor = image_processor
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
        """Request cancellation and release images if the worker already finished."""
        with self._lock:
            self._cancel.set()
            if self._done and self.result is not None:
                self.release_images(self.result.images)

    def _report(self, progress: float, status: str) -> None:
        with self._lock:
            self._progress = progress
            self._status = status

    def run(self) -> None:
        """Execute CPU loading and release partial images on cancellation or error."""
        start = time.perf_counter()
        payload: dict = {}
        try:
            steps: tuple[tuple[str, Callable[[dict], None]], ...] = (
                ("Reading level configuration", self._step_config),
                ("Generating starfield", self._step_stars),
                ("Building spatial grid", self._step_grid),
                ("Decoding assets", self._step_assets),
                ("Finalizing", self._step_finalize),
            )
            for index, (label, step_fn) in enumerate(steps):
                if self._cancel.is_set():
                    return
                self._report(index / len(steps), label)
                step_fn(payload)
                self._report((index + 1) / len(steps), f"{label} — OK")

            if self._cancel.is_set():
                return
            self.result = LoadResult(
                stars=payload["stars"],
                grid=payload["grid"],
                images=payload.get("images", []),
                elapsed=time.perf_counter() - start,
            )
        except BaseException as exc:  # Report worker failures to the main thread.
            with self._lock:
                self._error = exc
        finally:
            # Synchronize publication with cancel() so even a timed-out join
            # leaves exactly one owner responsible for pending CPU images.
            with self._lock:
                if self.result is None or self._cancel.is_set():
                    self.release_images(payload.get("images", []))
                self._done = True

    def release_images(self, images: list[tuple[str, ImageHandle | None]]) -> None:
        """Release pending CPU images after their worker has stopped.

        Args:
            images: Owned image handles, replaced with ``None`` after release.
        """
        for index, (asset_id, image) in enumerate(images):
            if image is not None:
                self.image_processor.unload_image(image)
                images[index] = (asset_id, None)

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
        """Generate CPU image handles without accessing the graphics context.

        A real game can call ``image_processor.load_image(path)`` here instead
        of generating solid colors. Every partial result remains owned by the
        job until it is published or released.
        """
        rng = random.Random(99)
        images: list[tuple[str, ImageHandle | None]] = []
        payload["images"] = images
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
            image = self.image_processor.gen_image_color(TILE_SIZE, TILE_SIZE, color)
            images.append((f"tile_{index:05d}", image))
            if index % 1000 == 0:
                self._report(self.progress, f"Decoding assets {index}/{ASSET_COUNT}")

    def _step_finalize(self, payload: dict) -> None:
        _ = payload
        _cpu_burn(0.08)


class MovingShapeUnit(pu.NodeUnit):
    """Bounce a shape against the screen boundaries using manual motion."""

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

    def draw(self, canvas: ICanvas2D) -> None:
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
    """Draw the background-loaded starfield with a gentle parallax drift."""

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="Starfield")
        self.layer = pu.Layer.BACKGROUND
        self.stars = result.stars
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        for x, y, size, speed, color in self.stars:
            dx = (x + self._time * speed) % WINDOW_WIDTH
            canvas.draw_rectangle(rect=(dx, y, size, size), color=color)


class _LoadingState:
    """Share loading progress between the scene and its overlay."""

    def __init__(self) -> None:
        self.progress = 0.0
        self.status = "Preparing..."


class LoadingOverlay(pu.NodeUnit):
    """Display loading progress, status, and an animated spinner."""

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

    def draw(self, canvas: ICanvas2D) -> None:
        w = float(WINDOW_WIDTH)
        h = float(WINDOW_HEIGHT)
        px = w / 2 - 230
        py = h / 2 - 95
        progress = self._display_progress

        # Dim the screen beneath the loading panel.
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

        # Title and spinner
        canvas.draw_text(
            text="LOADING LEVEL",
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

        # Current loading step
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
            text="BACKSPACE: cancel",
            pos=(px + 24, py + 158),
            font_size=13,
            color=(110, 120, 150, 255),
        )


class LoadingScene(pu.SceneUnit):
    """Decode images in a worker, then upload bounded GPU batches on the main thread.

    CPU decoding contributes ``_DECODE_WEIGHT`` to progress. Uploading contributes
    ``_UPLOAD_WEIGHT`` and uses ``Assets.load_from_image`` with ownership transfer.
    On cancellation, pending images and already-uploaded assets are released.
    """

    def __init__(self, target_factory: Callable[[LoadResult], pu.SceneUnit]) -> None:
        super().__init__(name="LoadingScene")
        self._target_factory = target_factory
        self._job: LoadJob | None = None
        self._thread: threading.Thread | None = None
        self._state = _LoadingState()
        self._phase = "loading"
        self._images: list[tuple[str, ImageHandle | None]] = []
        self._uploaded: list[str] = []
        self._switching = False

    def on_load(self) -> None:
        print("LoadingScene: worker started")
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
            print(f"LoadingScene: load failed ({job.error!r}); returning to menu")
            self._switching = True
            manager.request_change(MenuScene)
            return

        result = job.result
        if not result.images:
            # No GPU uploads are needed; request the target immediately.
            self._switching = True
            manager.request_change(partial(self._target_factory, result))
            return

        self._images = result.images
        self._phase = "uploading"

    def _update_uploading(self) -> None:
        job = self._job
        if job is None or job.result is None:
            return

        assets: IAssets = self.one("@Assets", scope="global")
        total = len(self._images)
        start = len(self._uploaded)
        for index in range(start, min(start + UPLOAD_BATCH, total)):
            asset_id, image = self._images[index]
            if image is None:
                raise RuntimeError(f"Image for {asset_id!r} was released before upload")
            try:
                # Ownership includes releasing the CPU image if uploading fails.
                assets.load_from_image(asset_id, image, take_ownership=True)
            finally:
                self._images[index] = (asset_id, None)
            self._uploaded.append(asset_id)

        uploaded_count = len(self._uploaded)
        self._state.progress = _DECODE_WEIGHT + _UPLOAD_WEIGHT * (
            uploaded_count / max(1, total)
        )
        self._state.status = f"Upload GPU {uploaded_count}/{total}"

        if uploaded_count >= total:
            print(f"LoadingScene: uploaded {total} GPU assets ({UPLOAD_BATCH}/step)")
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
            # Cancelled uploads retain no scene-owned GPU resources.
            assets = self.one_or_none("@Assets", scope="global")
            if assets is not None:
                for asset_id in self._uploaded:
                    assets.unload_asset(asset_id)
            print(f"LoadingScene: released {len(self._uploaded)} assets after cancel")
        print("LoadingScene: worker cancellation requested")


class MenuScene(pu.SceneUnit):
    """Display the initial menu scene."""

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
    """Display a lightweight scene with no background loading."""

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
    """Display a rotating sample of the 10,000 registered GPU assets."""

    COLS = 40
    ROWS = 25
    CELL = 16
    GAP = 2

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="TileMosaic")
        self.layer = pu.Layer.WORLD
        self.asset_ids = [asset_id for asset_id, _image in result.images]
        self._time = 0.0

    def update(self, dt: float) -> None:
        self._time += dt

    def render_submit(self, renderer, context=None) -> None:
        if not self.asset_ids:
            return
        # Rotate the visible sample across the registered assets.
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
                texture = assets.get_asset(self.asset_ids[index])
                renderer.render_sprite(
                    texture=texture,
                    source=texture.source_rect,
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
    """Build the heavy scene after CPU loading and GPU uploads complete."""

    def __init__(self, result: LoadResult) -> None:
        super().__init__(name="HeavyScene")
        self.result = result
        self.load_stats = (
            f"Level loaded: {len(result.stars)} stars, "
            f"{len(result.grid)} grid cells, {len(result.images)} GPU assets "
            f"in {result.elapsed:.2f}s (background)"
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
        # Release assets owned by this scene when leaving it.
        assets = self.one_or_none("@Assets", scope="global")
        if assets is not None:
            for asset_id, _image in self.result.images:
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
        self.window.clear_background((16, 18, 28, 255))
        self.scene_manager.render(self.renderer)

        behavior = self.scene_manager.transition_behavior
        lines = [
            "SPACE: light scene | ENTER: heavy scene (background loading)"
            " | BACKSPACE: back",
            f"stack depth: {self.scene_manager.depth}"
            f" | transition: {behavior.state if behavior is not None else 'idle'}",
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

        # Draw the transition fade above the UI.
        if behavior is not None and behavior.alpha > 0.0:
            alpha = int(min(255.0, behavior.alpha))
            self.renderer.render_custom(
                z=0,
                layer=pu.Layer.OVERLAY,
                draw_func=lambda canvas: canvas.draw_rectangle(
                    rect=(0.0, 0.0, float(WINDOW_WIDTH), float(WINDOW_HEIGHT)),
                    color=(0, 0, 0, alpha),
                ),
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
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
