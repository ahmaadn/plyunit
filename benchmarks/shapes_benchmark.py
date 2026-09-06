from __future__ import annotations

import argparse
import gc
import math
import random
import time
from dataclasses import dataclass

import numpy as np
import pyray as pr

import plyunit as pu
from benchmarks.report_paths import resolve_report_path, write_text_report
from plyunit.rendering import Layer

PROFILE_PASS_RATIO = {
    "strict": 0.95,
    "balanced": 0.90,
    "igpu": 0.80,
}

_EPSILON = 1e-6

SHAPE_CIRCLE = 0
SHAPE_RECTANGLE = 1
SHAPE_LINE = 2
SHAPE_TRIANGLE = 3
_SHAPE_CHOICES = (
    SHAPE_CIRCLE,
    SHAPE_RECTANGLE,
    SHAPE_LINE,
    SHAPE_TRIANGLE,
)

# Fixed palette (100) — typical game palette; avoids color-cache thrash.
_PALETTE_RGBA = np.array(
    [
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 255)
        for _ in range(100)
    ],
    dtype=np.uint8,
)


@dataclass(slots=True)
class BenchmarkConfig:
    title: str
    window_width: int
    window_height: int
    target_fps: int
    fps_mode: str
    fixed_update_hz: int
    max_substeps_per_frame: int
    max_frame_delta_time: float
    background_color: tuple[int, int, int, int]

    initial_entities: int
    target_entities: int
    max_entities: int
    add_step: int
    remove_step: int
    auto_add_per_second: float

    speed_min: float
    speed_max: float
    shape_size_min: int
    shape_size_max: int

    warmup_seconds: float
    duration_seconds: float
    stability_seconds: float
    max_frames: int
    auto_stop_on_target: bool

    report_interval: float
    report_file: str
    profile: str
    pass_ratio: float | None
    seed: int | None

    keyboard_controls: bool
    overlay: bool
    add_key: str
    add_alt_key: str
    remove_key: str
    remove_alt_key: str
    use_batching: bool
    use_atlas: bool


@dataclass(slots=True)
class BenchmarkResult:
    config: BenchmarkConfig
    stop_reason: str
    elapsed_seconds: float
    rendered_frames: int
    entities_final: int
    entities_peak: int

    avg_fps: float
    min_fps: float
    max_fps: float

    avg_fps_target_pass: float
    min_fps_target_pass: float
    max_fps_target_pass: float
    target_phase_seconds: float
    target_phase_frames: int

    def format_report(self) -> str:
        lines = [
            "=== Plyunit Shapes Benchmark Result ===",
            f"stop_reason              : {self.stop_reason}",
            f"elapsed_seconds          : {self.elapsed_seconds:.2f}",
            f"rendered_frames          : {self.rendered_frames}",
            f"entities_final           : {self.entities_final}",
            f"entities_peak            : {self.entities_peak}",
            f"avg_fps                  : {self.avg_fps:.2f}",
            f"min_fps                  : {self.min_fps:.2f}",
            f"max_fps                  : {self.max_fps:.2f}",
            f"avg_fps_target_phase     : {self.avg_fps_target_pass:.2f}",
            f"min_fps_target_phase     : {self.min_fps_target_pass:.2f}",
            f"max_fps_target_phase     : {self.max_fps_target_pass:.2f}",
            f"target_phase_seconds     : {self.target_phase_seconds:.2f}",
            f"target_phase_frames      : {self.target_phase_frames}",
            f"target_entities          : {self.config.target_entities}",
            f"target_fps               : {self.config.target_fps}",
            f"required_min_fps         : {self.required_min_fps():.2f}",
            f"profile                  : {self.config.profile}",
            f"pass_ratio               : {self.selected_pass_ratio():.2f}",
            f"fps_mode                 : {self.config.fps_mode}",
            f"pass                     : {self.passed()}",
        ]
        return "\n".join(lines)

    def selected_pass_ratio(self) -> float:
        ratio = (
            self.config.pass_ratio
            if self.config.pass_ratio is not None
            else PROFILE_PASS_RATIO[self.config.profile]
        )
        return max(0.0, min(1.0, ratio))

    def required_min_fps(self) -> float:
        if self.config.target_fps <= 0:
            return 0.0
        return self.config.target_fps * self.selected_pass_ratio()

    def passed(self) -> bool:
        if self.config.target_fps <= 0:
            return True
        if self.entities_peak < self.config.target_entities:
            return False
        if self.target_phase_frames <= 0:
            return False
        return self.avg_fps_target_pass >= self.required_min_fps()


class ShapesBenchmarkScene(pu.SceneUnit):
    def __init__(self, app: pu.App, config: BenchmarkConfig) -> None:
        super().__init__(name="shapes-benchmark-scene")
        self.app = app
        self.config = config

        # Contiguous SoA — sim + batch share buffers (zero-copy style hot path).
        self.pos_xy = np.empty((0, 2), dtype=np.float32)
        self.vel_xy = np.empty((0, 2), dtype=np.float32)
        self.size_wh = np.empty((0, 2), dtype=np.float32)
        self.rgba = np.empty((0, 4), dtype=np.uint8)
        self.shape_kind = np.empty((0,), dtype=np.int8)
        self._shape_textures: list[object] = []
        self._shape_sources: list[tuple[float, float, float, float]] | None = None
        self._entity_textures: list[object] = []
        self._entity_sources: list[tuple[float, float, float, float]] | None = None
        self._render_scales = np.empty((0,), dtype=np.float32)
        self._render_origins = np.empty((0, 2), dtype=np.float32)
        self._render_offsets = np.empty((0, 2), dtype=np.float32)

        self._benchmark_start = 0.0
        self._last_frame_time: float | None = None
        self._last_report_time = 0.0
        self._last_fps = 0.0

        self._measured_time = 0.0
        self._measured_frames = 0
        self._min_fps = float("inf")
        self._max_fps = 0.0

        self._target_measured_time = 0.0
        self._target_measured_frames = 0
        self._target_min_fps = float("inf")
        self._target_max_fps = 0.0
        self._target_reached_at: float | None = None

        self._rendered_frames = 0
        self._peak_entities = 0
        self._stop_reason = "window_closed"
        self._text: pu.Text | None = None

    @property
    def entity_count(self) -> int:
        return int(self.pos_xy.shape[0])

    def on_load(self) -> None:
        if self.config.seed is not None:
            random.seed(self.config.seed)

        if self.config.overlay:
            self._text = pu.Text()
        self._prepare_shape_textures()
        self._add_entities(self.config.initial_entities)

        gc.collect()
        gc.freeze()

        now = time.perf_counter()
        self._benchmark_start = now
        self._last_report_time = now

        print("=== Plyunit Shapes Benchmark Started ===")
        print(f"initial_entities: {self.entity_count}")
        print(f"target_entities : {self.config.target_entities}")
        print(f"target_fps      : {self.config.target_fps}")
        print(f"fps_mode        : {self.config.fps_mode}")

    def _prepare_shape_textures(self) -> None:
        """Bake reusable white shapes and optionally pack them into an atlas."""
        canvas = self.one("@Renderer").canvas
        assets = self.one("@Assets")
        white = (255, 255, 255, 255)
        textures = {
            "benchmark_circle": canvas.create_circle(radius=16.0, color=white),
            "benchmark_rect": canvas.create_rect(rect=(0, 0, 32, 32), color=white),
            "benchmark_line": canvas.create_line(
                start=(0, 0), end=(32, 32), color=white, thickness=2.0
            ),
            "benchmark_triangle": canvas.create_triangle(
                v1=(16, 0), v2=(0, 32), v3=(32, 32), color=white
            ),
        }
        assets.store_textures(textures)
        if self.config.use_atlas:
            assets.build_texture_atlas(list(textures))

        self._shape_textures = []
        sources: list[tuple[float, float, float, float]] = []
        for asset_id in textures:
            data = assets.get_texture_data(asset_id)
            self._shape_textures.append(data.texture)
            sources.append(data.source_rect)
        self._shape_sources = sources if self.config.use_atlas else None

    def _rebuild_render_arrays(self) -> None:
        """Resolve baked material and per-entity sprite geometry."""
        n = self.entity_count
        if n <= 0:
            self._entity_textures = []
            self._entity_sources = [] if self._shape_sources is not None else None
            self._render_scales = np.empty((0,), dtype=np.float32)
            self._render_origins = np.empty((0, 2), dtype=np.float32)
            self._render_offsets = np.empty((0, 2), dtype=np.float32)
            return

        kinds = self.shape_kind.astype(np.int32, copy=False)
        size = self.size_wh[:, 0]
        base_size = np.array((16.0, 32.0, 32.0, 32.0), dtype=np.float32)
        self._render_scales = size / base_size[kinds]
        self._entity_textures = [self._shape_textures[int(k)] for k in kinds]
        self._entity_sources = (
            [self._shape_sources[int(k)] for k in kinds]
            if self._shape_sources is not None
            else None
        )

        self._render_origins = np.zeros((n, 2), dtype=np.float32)
        circle_mask = kinds == SHAPE_CIRCLE
        self._render_origins[circle_mask] = (
            self._render_scales[circle_mask, None] * 16.0
        )
        line_mask = kinds == SHAPE_LINE
        self._render_origins[line_mask] = self._render_scales[line_mask, None]
        triangle_mask = kinds == SHAPE_TRIANGLE
        self._render_origins[triangle_mask, 0] = (
            self._render_scales[triangle_mask] * 16.0
        )
        self._render_offsets = np.zeros((n, 2), dtype=np.float32)

    def on_unload(self) -> None:
        gc.unfreeze()

    def update(self, dt: float) -> None:
        self._handle_keyboard()
        self._handle_auto_add(dt)

        _simulate_shapes(
            self.pos_xy,
            self.vel_xy,
            self.size_wh,
            float(self.config.window_width),
            float(self.config.window_height),
        )

        if self.entity_count > self._peak_entities:
            self._peak_entities = self.entity_count

    def render_submit(self, renderer) -> None:
        now = time.perf_counter()
        if self._last_frame_time is not None:
            frame_dt = max(_EPSILON, now - self._last_frame_time)
            self._collect_metrics(now, frame_dt)

        self._last_frame_time = now

        if self.config.use_batching:
            self._submit_batched(renderer)
        else:
            self._submit_individual(renderer)

        if self.config.overlay and self._text is not None:
            self._text.push(
                (
                    f"Shapes: {self.entity_count} | Target: "
                    f"{self.config.target_entities} | FPS: {self._last_fps:.1f}"
                ),
                pos=(12.0, 12.0),
                color=(30, 30, 30, 255),
                font_size=20,
                spacing=1.0,
                z=0,
                layer=Layer.UI,
            )

        self._rendered_frames += 1
        self._maybe_print_progress(now)
        self._maybe_stop(now)

    def _submit_batched(self, renderer) -> None:
        n = self.entity_count
        if n <= 0:
            return

        render_pos = self.pos_xy + self._render_offsets
        renderer.render_sprites(
            textures=self._entity_textures,
            positions=render_pos,
            pos_xy=render_pos,
            sources=self._entity_sources,
            origins=self._render_origins,
            scales=self._render_scales,
            tints=self.rgba,
            z=0,
            layer=Layer.ENTITIES,
        )

    def _submit_individual(self, renderer) -> None:
        # Per-entity sprite submit — baseline against render_sprites.
        n = self.entity_count
        pos = self.pos_xy + self._render_offsets
        sources = self._entity_sources
        for i in range(n):
            renderer.render_sprite(
                texture=self._entity_textures[i],
                source=sources[i] if sources is not None else None,
                pos=pos[i],
                origin=self._render_origins[i],
                scale=float(self._render_scales[i]),
                tint=self.rgba[i],
                z=0,
                layer=Layer.ENTITIES,
            )

    def _add_entities(self, count: int) -> int:
        if count <= 0:
            return 0
        allowed = max(0, self.config.max_entities - self.entity_count)
        to_add = min(count, allowed)
        if to_add <= 0:
            return 0

        max_x = max(0.0, float(self.config.window_width - 50))
        max_y = max(0.0, float(self.config.window_height - 50))
        smin = float(self.config.shape_size_min)
        smax = float(self.config.shape_size_max)

        new_pos = np.empty((to_add, 2), dtype=np.float32)
        new_vel = np.empty((to_add, 2), dtype=np.float32)
        new_size = np.empty((to_add, 2), dtype=np.float32)
        new_rgba = np.empty((to_add, 4), dtype=np.uint8)
        new_kind = np.empty((to_add,), dtype=np.int8)

        for i in range(to_add):
            new_pos[i, 0] = random.uniform(0.0, max_x)
            new_pos[i, 1] = random.uniform(0.0, max_y)
            vx, vy = _random_velocity(self.config.speed_min, self.config.speed_max)
            new_vel[i, 0] = vx
            new_vel[i, 1] = vy
            shape_size = random.uniform(smin, smax)
            new_size[i, 0] = shape_size
            new_size[i, 1] = shape_size
            new_rgba[i] = _PALETTE_RGBA[random.randrange(_PALETTE_RGBA.shape[0])]
            new_kind[i] = random.choice(_SHAPE_CHOICES)

        if self.pos_xy.shape[0] == 0:
            self.pos_xy = new_pos
            self.vel_xy = new_vel
            self.size_wh = new_size
            self.rgba = new_rgba
            self.shape_kind = new_kind
        else:
            self.pos_xy = np.vstack((self.pos_xy, new_pos))
            self.vel_xy = np.vstack((self.vel_xy, new_vel))
            self.size_wh = np.vstack((self.size_wh, new_size))
            self.rgba = np.vstack((self.rgba, new_rgba))
            self.shape_kind = np.concatenate((self.shape_kind, new_kind))

        self._rebuild_render_arrays()
        return to_add

    def _remove_entities(self, count: int) -> int:
        to_remove = min(count, self.entity_count)
        if to_remove <= 0:
            return 0
        keep = self.entity_count - to_remove
        self.pos_xy = self.pos_xy[:keep].copy()
        self.vel_xy = self.vel_xy[:keep].copy()
        self.size_wh = self.size_wh[:keep].copy()
        self.rgba = self.rgba[:keep].copy()
        self.shape_kind = self.shape_kind[:keep].copy()
        self._rebuild_render_arrays()
        return to_remove

    def _handle_keyboard(self) -> None:
        if not self.config.keyboard_controls:
            return
        kb = self.one_or_none("@Input", scope="global")
        if kb is None:
            return
        if kb.is_pressed("add"):
            self._add_entities(self.config.add_step)
        if self.config.remove_step > 0 and kb.is_pressed("remove"):
            self._remove_entities(self.config.remove_step)

    def _handle_auto_add(self, dt: float) -> None:
        if self.config.auto_add_per_second <= 0:
            return
        # Basic auto add logic if configured
        pass

    def _collect_metrics(self, now: float, frame_dt: float) -> None:
        elapsed = now - self._benchmark_start
        if elapsed < self.config.warmup_seconds:
            return

        fps = 1.0 / frame_dt
        self._last_fps = fps

        self._measured_frames += 1
        self._measured_time += frame_dt
        if fps < self._min_fps:
            self._min_fps = fps
        if fps > self._max_fps:
            self._max_fps = fps

        if self.entity_count >= self.config.target_entities:
            if self._target_reached_at is None:
                self._target_reached_at = now
                print(f"target reached: shapes={self.entity_count} at {elapsed:.2f}s")

            self._target_measured_frames += 1
            self._target_measured_time += frame_dt
            if fps < self._target_min_fps:
                self._target_min_fps = fps
            if fps > self._target_max_fps:
                self._target_max_fps = fps

    def _maybe_print_progress(self, now: float) -> None:
        if self.config.report_interval <= 0.0:
            return
        if now - self._last_report_time < self.config.report_interval:
            return
        elapsed = now - self._benchmark_start
        avg_fps = (
            self._measured_frames / max(_EPSILON, self._measured_time)
            if self._measured_frames > 0
            else 0.0
        )
        print(
            f"[progress] t={elapsed:6.2f}s shapes={self.entity_count:6d} "
            f"fps_now={self._last_fps:7.2f} fps_avg={avg_fps:7.2f}"
        )
        self._last_report_time = now

    def _maybe_stop(self, now: float) -> None:
        if (
            self.config.max_frames > 0
            and self._rendered_frames >= self.config.max_frames
        ):
            self._stop_reason = "max_frames"
            self.app.running = False
            return
        elapsed = now - self._benchmark_start
        if (
            self.config.duration_seconds > 0.0
            and elapsed >= self.config.duration_seconds
        ):
            self._stop_reason = "duration"
            self.app.running = False
            return
        if (
            self.config.auto_stop_on_target
            and self._target_reached_at is not None
            and self.config.stability_seconds > 0.0
            and now - self._target_reached_at >= self.config.stability_seconds
        ):
            self._stop_reason = "target_stability_window"
            self.app.running = False
            return

    def build_result(self, elapsed_seconds: float) -> BenchmarkResult:
        avg_fps = (
            self._measured_frames / max(_EPSILON, self._measured_time)
            if self._measured_frames > 0
            else 0.0
        )
        avg_fps_target = (
            self._target_measured_frames / max(_EPSILON, self._target_measured_time)
            if self._target_measured_frames > 0
            else 0.0
        )
        return BenchmarkResult(
            config=self.config,
            stop_reason=self._stop_reason,
            elapsed_seconds=elapsed_seconds,
            rendered_frames=self._rendered_frames,
            entities_final=self.entity_count,
            entities_peak=self._peak_entities,
            avg_fps=avg_fps,
            min_fps=0.0 if self._measured_frames == 0 else self._min_fps,
            max_fps=self._max_fps,
            avg_fps_target_pass=avg_fps_target,
            min_fps_target_pass=0.0
            if self._target_measured_frames == 0
            else self._target_min_fps,
            max_fps_target_pass=self._target_max_fps,
            target_phase_seconds=self._target_measured_time,
            target_phase_frames=self._target_measured_frames,
        )


class ShapesBenchmarkApp(pu.App):
    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__()
        self.benchmark_config = config
        self.scene: ShapesBenchmarkScene | None = None

    def on_load(self) -> None:
        cfg = self.benchmark_config
        self.input = pu.Input()
        self.input.map(
            "add",
            _resolve_key(cfg.add_key),
            _resolve_key(cfg.add_alt_key),
        )
        self.input.map(
            "remove",
            _resolve_key(cfg.remove_key),
            _resolve_key(cfg.remove_alt_key),
        )
        self.scene = ShapesBenchmarkScene(self, cfg)
        self.scene_manager.push(self.scene)

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def _simulate_shapes(
    pos_xy: np.ndarray,
    vel_xy: np.ndarray,
    size_wh: np.ndarray,
    window_width: float,
    window_height: float,
) -> None:
    """Vectorized bounce sim on float32 SoA (per-entity size limits)."""
    n = int(pos_xy.shape[0])
    if n <= 0:
        return

    pos_xy += vel_xy

    x = pos_xy[:, 0]
    y = pos_xy[:, 1]
    vx = vel_xy[:, 0]
    vy = vel_xy[:, 1]
    limit_x = np.maximum(0.0, window_width - size_wh[:, 0])
    limit_y = np.maximum(0.0, window_height - size_wh[:, 1])

    hit_left = x < 0.0
    hit_right = x > limit_x
    hit_top = y < 0.0
    hit_bottom = y > limit_y

    if hit_left.any():
        x[hit_left] = 0.0
        vx[hit_left] = np.abs(vx[hit_left])
    if hit_right.any():
        x[hit_right] = limit_x[hit_right]
        vx[hit_right] = -np.abs(vx[hit_right])
    if hit_top.any():
        y[hit_top] = 0.0
        vy[hit_top] = np.abs(vy[hit_top])
    if hit_bottom.any():
        y[hit_bottom] = limit_y[hit_bottom]
        vy[hit_bottom] = -np.abs(vy[hit_bottom])


def _random_velocity(speed_min: float, speed_max: float) -> tuple[float, float]:
    speed = random.uniform(speed_min, speed_max)
    angle = random.uniform(0.0, math.tau)
    return (math.cos(angle) * speed, math.sin(angle) * speed)


def _resolve_key(name: str) -> int:
    normalized = name.strip().upper()
    key_name = normalized if normalized.startswith("KEY_") else f"KEY_{normalized}"
    key_value = getattr(pr, key_name, None)
    if key_value is None:
        raise ValueError(f"Unknown key name: {name}")
    return int(key_value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plyunit shapes benchmark")
    parser.add_argument("--title", default="Plyunit Shapes Benchmark")
    parser.add_argument("--window-width", type=int, default=1280)
    parser.add_argument("--window-height", type=int, default=720)
    parser.add_argument("--target-fps", type=int, default=60)
    parser.add_argument("--fps-mode", choices=["capped", "uncapped"], default="capped")
    parser.add_argument("--fixed-update-hz", type=int, default=60)
    parser.add_argument("--max-substeps-per-frame", type=int, default=1)
    parser.add_argument("--max-frame-delta-time", type=float, default=0.25)

    parser.add_argument(
        "--initial-entities",
        "--entities",
        dest="initial_entities",
        type=int,
        default=1500,
    )
    parser.add_argument("--target-entities", type=int, default=1500)
    parser.add_argument("--max-entities", type=int, default=10000)
    parser.add_argument("--add-step", type=int, default=100)
    parser.add_argument("--remove-step", type=int, default=100)
    parser.add_argument("--auto-add-per-second", type=float, default=0.0)

    parser.add_argument("--speed-min", type=float, default=1.0)
    parser.add_argument("--speed-max", type=float, default=4.0)
    parser.add_argument("--shape-size-min", type=int, default=10)
    parser.add_argument("--shape-size-max", type=int, default=30)

    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--stability-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument(
        "--auto-stop-on-target", action=argparse.BooleanOptionalAction, default=True
    )

    parser.add_argument(
        "--profile", choices=["strict", "balanced", "igpu"], default="strict"
    )
    parser.add_argument("--pass-ratio", type=float, default=None)
    parser.add_argument("--report-interval", type=float, default=1.0)
    parser.add_argument(
        "--report-file",
        default="",
        help=(
            "Report filename or path. Default: "
            "benchmarks/report/shapes_benchmark_<timestamp>.txt"
        ),
    )
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument(
        "--keyboard-controls", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--overlay", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--add-key", default="EQUAL")
    parser.add_argument("--add-alt-key", default="KP_ADD")
    parser.add_argument("--remove-key", default="MINUS")
    parser.add_argument("--remove-alt-key", default="KP_SUBTRACT")

    parser.add_argument("--bg-r", type=int, default=245)
    parser.add_argument("--bg-g", type=int, default=245)
    parser.add_argument("--bg-b", type=int, default=245)
    parser.add_argument("--bg-a", type=int, default=255)

    parser.add_argument(
        "--batching",
        "--use-batching",
        action=argparse.BooleanOptionalAction,
        default=False,
        dest="use_batching",
    )
    parser.add_argument(
        "--atlas",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="use_atlas",
        help="Pack baked shape textures into an Assets texture atlas.",
    )

    args = parser.parse_args()

    config = BenchmarkConfig(
        title=str(args.title),
        window_width=max(200, int(args.window_width)),
        window_height=max(120, int(args.window_height)),
        target_fps=max(0, int(args.target_fps)),
        fps_mode=str(args.fps_mode),
        fixed_update_hz=max(1, int(args.fixed_update_hz)),
        max_substeps_per_frame=max(1, int(args.max_substeps_per_frame)),
        max_frame_delta_time=max(0.01, float(args.max_frame_delta_time)),
        background_color=(
            max(0, min(255, int(args.bg_r))),
            max(0, min(255, int(args.bg_g))),
            max(0, min(255, int(args.bg_b))),
            max(0, min(255, int(args.bg_a))),
        ),
        initial_entities=max(0, int(args.initial_entities)),
        target_entities=max(1, int(args.target_entities)),
        max_entities=max(1, int(args.max_entities)),
        add_step=max(1, int(args.add_step)),
        remove_step=max(0, int(args.remove_step)),
        auto_add_per_second=max(0.0, float(args.auto_add_per_second)),
        speed_min=max(0.01, float(args.speed_min)),
        speed_max=max(0.01, float(args.speed_max)),
        shape_size_min=max(1, int(args.shape_size_min)),
        shape_size_max=max(1, int(args.shape_size_max)),
        warmup_seconds=max(0.0, float(args.warmup_seconds)),
        duration_seconds=max(0.0, float(args.duration_seconds)),
        stability_seconds=max(0.0, float(args.stability_seconds)),
        max_frames=max(0, int(args.max_frames)),
        auto_stop_on_target=bool(args.auto_stop_on_target),
        report_interval=max(0.0, float(args.report_interval)),
        report_file=str(
            resolve_report_path(args.report_file, default_stem="shapes_benchmark")
        ),
        profile=str(args.profile),
        pass_ratio=args.pass_ratio,
        seed=args.seed,
        keyboard_controls=bool(args.keyboard_controls),
        overlay=bool(args.overlay),
        add_key=str(args.add_key),
        add_alt_key=str(args.add_alt_key),
        remove_key=str(args.remove_key),
        remove_alt_key=str(args.remove_alt_key),
        use_batching=bool(args.use_batching),
        use_atlas=bool(args.use_atlas),
    )

    app = ShapesBenchmarkApp(config)
    runtime_target_fps = config.target_fps if config.fps_mode == "capped" else 0
    pu.init(
        app,
        pu.AppConfig(
            title=config.title,
            window_width=config.window_width,
            window_height=config.window_height,
            target_fps=runtime_target_fps,
            fixed_update_hz=config.fixed_update_hz,
            max_frame_delta_time=config.max_frame_delta_time,
            max_substeps_per_frame=config.max_substeps_per_frame,
            background_color=config.background_color,
        ),
    )
    start = time.perf_counter()
    app.run()
    elapsed = max(_EPSILON, time.perf_counter() - start)

    if app.scene is None:
        raise RuntimeError("Benchmark scene was not initialized")

    result = app.scene.build_result(elapsed)
    print(result.format_report())
    path = write_text_report(config.report_file, result.format_report())
    print(f"report_file              : {path}")

    return 0 if result.passed() else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
