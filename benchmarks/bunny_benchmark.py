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

    initial_bunnies: int
    target_bunnies: int
    max_bunnies: int
    add_step: int
    remove_step: int
    auto_add_per_second: float

    speed_min: float
    speed_max: float
    sprite_size: int

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


@dataclass(slots=True)
class BenchmarkResult:
    config: BenchmarkConfig
    stop_reason: str
    elapsed_seconds: float
    rendered_frames: int
    bunnies_final: int
    bunnies_peak: int

    avg_fps: float
    min_fps: float
    max_fps: float

    avg_fps_target_phase: float
    min_fps_target_phase: float
    max_fps_target_phase: float
    target_phase_seconds: float
    target_phase_frames: int

    keyboard_additions: int
    keyboard_removals: int
    auto_additions: int

    def format_report(self) -> str:
        lines = [
            "=== plyunit Bunny Benchmark Result ===",
            f"stop_reason              : {self.stop_reason}",
            f"elapsed_seconds          : {self.elapsed_seconds:.2f}",
            f"rendered_frames          : {self.rendered_frames}",
            f"bunnies_final            : {self.bunnies_final}",
            f"bunnies_peak             : {self.bunnies_peak}",
            f"avg_fps                  : {self.avg_fps:.2f}",
            f"min_fps                  : {self.min_fps:.2f}",
            f"max_fps                  : {self.max_fps:.2f}",
            f"avg_fps_target_phase     : {self.avg_fps_target_phase:.2f}",
            f"min_fps_target_phase     : {self.min_fps_target_phase:.2f}",
            f"max_fps_target_phase     : {self.max_fps_target_phase:.2f}",
            f"target_phase_seconds     : {self.target_phase_seconds:.2f}",
            f"target_phase_frames      : {self.target_phase_frames}",
            f"target_bunnies           : {self.config.target_bunnies}",
            f"target_fps               : {self.config.target_fps}",
            f"required_min_fps         : {self.required_min_fps():.2f}",
            f"profile                  : {self.config.profile}",
            f"pass_ratio               : {self.selected_pass_ratio():.2f}",
            f"fps_mode                 : {self.config.fps_mode}",
            f"keyboard_additions       : {self.keyboard_additions}",
            f"keyboard_removals        : {self.keyboard_removals}",
            f"auto_additions           : {self.auto_additions}",
            f"pass                     : {self.passed()}",
        ]
        return "\n".join(lines)

    def selected_pass_ratio(self) -> float:
        ratio = self.pass_ratio_override()
        return max(0.0, min(1.0, ratio))

    def pass_ratio_override(self) -> float:
        if self.config.pass_ratio is not None:
            return self.config.pass_ratio
        return PROFILE_PASS_RATIO[self.config.profile]

    def required_min_fps(self) -> float:
        if self.config.target_fps <= 0:
            return 0.0
        return self.config.target_fps * self.selected_pass_ratio()

    def passed(self) -> bool:
        if self.config.target_fps <= 0:
            return True
        if self.bunnies_peak < self.config.target_bunnies:
            return False
        if self.target_phase_frames <= 0:
            return False
        return self.avg_fps_target_phase >= self.required_min_fps()

    def print_report(self) -> None:
        print(self.format_report())


class BunnyBenchmarkScene(pu.SceneUnit):
    def __init__(self, app: pu.App, config: BenchmarkConfig) -> None:
        super().__init__(name="bunny-benchmark-scene")
        self.app = app
        self.config = config

        # Contiguous float32 SoA — sim + draw share the same buffers (zero-copy pack).
        self.pos_xy = np.empty((0, 2), dtype=np.float32)
        self.vel_xy = np.empty((0, 2), dtype=np.float32)
        # Legacy aliases kept for any external tooling that inspected lists.
        self.positions = self.pos_xy
        self.velocities = self.vel_xy
        self._texture = None

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
        self._peak_bunnies = 0

        self._keyboard_added = 0
        self._keyboard_removed = 0
        self._auto_added = 0

        self._auto_add_accumulator = 0.0

        self._stop_reason = "window_closed"

    @property
    def bunny_count(self) -> int:
        return int(self.pos_xy.shape[0])

    def on_load(self) -> None:
        if self.config.seed is not None:
            random.seed(self.config.seed)

        self._create_texture()
        if self.config.overlay:
            self._text = pu.Text()
        self._add_bunnies(self.config.initial_bunnies, source="initial")

        # Fix #5: Minimalisir GC pause selama benchmark.
        # gc.collect() bersihkan semua garbage sekarang, gc.freeze() membekukan
        # semua objek yang sudah ada agar tidak di-scan oleh GC generational —
        # ini mencegah pause periodik yang menyebabkan spike frame time.
        gc.collect()
        gc.freeze()

        now = time.perf_counter()
        self._benchmark_start = now
        self._last_report_time = now

        print("=== Plyunit Bunny Benchmark Started ===")
        print(f"initial_bunnies: {self.bunny_count}")
        print(f"target_bunnies : {self.config.target_bunnies}")
        print(f"target_fps     : {self.config.target_fps}")
        print(f"fps_mode       : {self.config.fps_mode}")
        print(
            f"keyboard       : +({self.config.add_key}/{self.config.add_alt_key})"
            f" -({self.config.remove_key}/{self.config.remove_alt_key})"
        )

    def on_unload(self) -> None:
        if self._texture is not None:
            pr.unload_texture(self._texture)
        self._texture = None
        self._text = None
        # Pulihkan GC ke kondisi normal setelah benchmark selesai
        gc.unfreeze()

    def update(self, dt: float) -> None:
        self._handle_keyboard()
        self._handle_auto_add(dt)

        width_limit = max(
            0.0, float(self.config.window_width - self.config.sprite_size)
        )
        height_limit = max(
            0.0,
            float(self.config.window_height - self.config.sprite_size),
        )
        _simulate_bunnies(self.pos_xy, self.vel_xy, width_limit, height_limit)

        if self.bunny_count > self._peak_bunnies:
            self._peak_bunnies = self.bunny_count

    def render_submit(self, renderer) -> None:
        now = time.perf_counter()
        if self._last_frame_time is not None:
            frame_dt = max(_EPSILON, now - self._last_frame_time)
            self._collect_metrics(now, frame_dt)

        self._last_frame_time = now

        renderer.render_batch(
            texture=self._texture,
            positions=self.pos_xy,
            pos_xy=self.pos_xy,
            z=0,
            layer=Layer.ENTITIES,
            tint=(255, 255, 255, 255),
        )

        if self.config.overlay:
            self._submit_overlay(renderer)

        self._rendered_frames += 1
        self._maybe_print_progress(now)
        self._maybe_stop(now)

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
            bunnies_final=self.bunny_count,
            bunnies_peak=self._peak_bunnies,
            avg_fps=avg_fps,
            min_fps=0.0 if self._measured_frames == 0 else self._min_fps,
            max_fps=self._max_fps,
            avg_fps_target_phase=avg_fps_target,
            min_fps_target_phase=(
                0.0 if self._target_measured_frames == 0 else self._target_min_fps
            ),
            max_fps_target_phase=self._target_max_fps,
            target_phase_seconds=self._target_measured_time,
            target_phase_frames=self._target_measured_frames,
            keyboard_additions=self._keyboard_added,
            keyboard_removals=self._keyboard_removed,
            auto_additions=self._auto_added,
        )

    def _create_texture(self) -> None:
        # Canvas is a free-function module (factory returns the module).
        canvas = pu.Canvas() if callable(pu.Canvas) else pu.Canvas
        image = pr.gen_image_color(
            self.config.sprite_size,
            self.config.sprite_size,
            canvas.color((235, 235, 235, 255)),
        )
        self._texture = pr.load_texture_from_image(image)
        pr.unload_image(image)

    def _add_bunnies(self, count: int, *, source: str = "auto") -> int:
        if count <= 0:
            return 0

        current = self.bunny_count
        allowed = max(0, self.config.max_bunnies - current)
        to_add = min(count, allowed)
        if to_add <= 0:
            return 0

        max_x = max(0.0, self.config.window_width - self.config.sprite_size)
        max_y = max(0.0, self.config.window_height - self.config.sprite_size)

        new_pos = np.empty((to_add, 2), dtype=np.float32)
        new_vel = np.empty((to_add, 2), dtype=np.float32)
        for i in range(to_add):
            new_pos[i, 0] = random.uniform(0.0, max_x)
            new_pos[i, 1] = random.uniform(0.0, max_y)
            vx, vy = _random_velocity(self.config.speed_min, self.config.speed_max)
            new_vel[i, 0] = vx
            new_vel[i, 1] = vy

        if self.pos_xy.shape[0] == 0:
            self.pos_xy = new_pos
            self.vel_xy = new_vel
        else:
            self.pos_xy = np.vstack((self.pos_xy, new_pos))
            self.vel_xy = np.vstack((self.vel_xy, new_vel))
        self.positions = self.pos_xy
        self.velocities = self.vel_xy

        if source == "keyboard":
            self._keyboard_added += to_add
        elif source == "auto":
            self._auto_added += to_add
        return to_add

    def _remove_bunnies(self, count: int) -> int:
        if count <= 0 or self.bunny_count <= 0:
            return 0

        to_remove = min(count, self.bunny_count)
        keep = self.bunny_count - to_remove
        self.pos_xy = self.pos_xy[:keep].copy()
        self.vel_xy = self.vel_xy[:keep].copy()
        self.positions = self.pos_xy
        self.velocities = self.vel_xy
        self._keyboard_removed += to_remove
        return to_remove

    def _handle_keyboard(self) -> None:
        if not self.config.keyboard_controls:
            return
        kb = self.one_or_none("%Input", scope="global")
        if kb is None:
            return
        if kb.is_pressed("add"):
            self._add_bunnies(self.config.add_step, source="keyboard")
        if self.config.remove_step > 0 and kb.is_pressed("remove"):
            self._remove_bunnies(self.config.remove_step)

    def _handle_auto_add(self, dt: float) -> None:
        if self.config.auto_add_per_second <= 0.0:
            return

        self._auto_add_accumulator += dt * self.config.auto_add_per_second
        to_add = int(self._auto_add_accumulator)
        if to_add <= 0:
            return

        self._auto_add_accumulator -= to_add
        self._add_bunnies(to_add, source="auto")

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

        if self.bunny_count >= self.config.target_bunnies:
            if self._target_reached_at is None:
                self._target_reached_at = now
                print(f"target reached: bunnies={self.bunny_count} at {elapsed:.2f}s")

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
            f"[progress] t={elapsed:6.2f}s "
            f"bunnies={self.bunny_count:6d} "
            f"fps_now={self._last_fps:7.2f} "
            f"fps_avg={avg_fps:7.2f}"
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

    def _submit_overlay(self, renderer) -> None:
        _ = renderer
        self._text.push(
            (
                f"Bunnies: {self.bunny_count} | "
                f"Target: {self.config.target_bunnies} | "
                f"FPS: {self._last_fps:.1f}"
            ),
            pos=(12.0, 12.0),
            color=(30, 30, 30, 255),
            font_size=20,
            spacing=1.0,
            z=0,
            layer=Layer.UI,
        )


class BunnyBenchmarkApp(pu.App):
    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__()
        self.benchmark_config = config
        self.scene: BunnyBenchmarkScene | None = None

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
        self.scene = BunnyBenchmarkScene(self, cfg)
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


def _simulate_bunnies(
    pos_xy: np.ndarray,
    vel_xy: np.ndarray,
    width_limit: float,
    height_limit: float,
) -> None:
    """Vectorized bounce sim on contiguous float32 (n,2) arrays."""
    n = int(pos_xy.shape[0])
    if n <= 0:
        return

    pos_xy += vel_xy

    x = pos_xy[:, 0]
    y = pos_xy[:, 1]
    vx = vel_xy[:, 0]
    vy = vel_xy[:, 1]

    hit_left = x < 0.0
    hit_right = x > width_limit
    hit_top = y < 0.0
    hit_bottom = y > height_limit

    if hit_left.any():
        x[hit_left] = 0.0
        vx[hit_left] = np.abs(vx[hit_left])
    if hit_right.any():
        x[hit_right] = width_limit
        vx[hit_right] = -np.abs(vx[hit_right])
    if hit_top.any():
        y[hit_top] = 0.0
        vy[hit_top] = np.abs(vy[hit_top])
    if hit_bottom.any():
        y[hit_bottom] = height_limit
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plyunit bunny benchmark with keyboard scaling and terminal report."
    )

    parser.add_argument("--title", default="plyunit Bunny Benchmark")
    parser.add_argument("--window-width", type=int, default=1280)
    parser.add_argument("--window-height", type=int, default=720)
    parser.add_argument("--target-fps", type=int, default=60)
    parser.add_argument(
        "--fps-mode",
        choices=["capped", "uncapped"],
        default="capped",
        help="capped: enforce target-fps. uncapped: no runtime cap.",
    )
    parser.add_argument("--fixed-update-hz", type=int, default=60)
    # Fix #1: default 1 substep/frame untuk benchmark — mencegah "catch-up spike"
    # saat frame sebelumnya lambat (misal GC pause) agar tidak memicu simulasi
    # 2-5x dalam satu frame berikutnya yang menghancurkan min_fps.
    parser.add_argument("--max-substeps-per-frame", type=int, default=1)
    parser.add_argument("--max-frame-delta-time", type=float, default=0.25)

    parser.add_argument(
        "--initial-bunnies",
        "--bunnies",
        dest="initial_bunnies",
        type=int,
        default=1000,
        help="Initial bunny count when benchmark starts.",
    )
    parser.add_argument(
        "--target-bunnies",
        type=int,
        default=8000,
        help="Target bunny count used for stability pass/fail metrics.",
    )
    parser.add_argument("--max-bunnies", type=int, default=50000)
    parser.add_argument("--add-step", type=int, default=250)
    parser.add_argument("--remove-step", type=int, default=250)
    parser.add_argument("--auto-add-per-second", type=float, default=0.0)

    parser.add_argument("--speed-min", type=float, default=1.0)
    parser.add_argument("--speed-max", type=float, default=4.0)
    parser.add_argument("--sprite-size", type=int, default=16)

    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--stability-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument(
        "--auto-stop-on-target",
        action=argparse.BooleanOptionalAction,
        default=True,
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
            "benchmarks/report/bunny_benchmark_<timestamp>.txt. "
            "Relative names are always stored under benchmarks/report/ "
            "with a timestamp suffix."
        ),
    )
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument(
        "--keyboard-controls",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--overlay",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--add-key", default="EQUAL")
    parser.add_argument("--add-alt-key", default="KP_ADD")
    parser.add_argument("--remove-key", default="MINUS")
    parser.add_argument("--remove-alt-key", default="KP_SUBTRACT")

    parser.add_argument("--bg-r", type=int, default=245)
    parser.add_argument("--bg-g", type=int, default=245)
    parser.add_argument("--bg-b", type=int, default=245)
    parser.add_argument("--bg-a", type=int, default=255)

    return parser


def _normalize_config(args: argparse.Namespace) -> BenchmarkConfig:
    speed_min = max(0.01, float(args.speed_min))
    speed_max = max(speed_min, float(args.speed_max))

    pass_ratio = None
    if args.pass_ratio is not None:
        pass_ratio = max(0.0, min(1.0, float(args.pass_ratio)))

    return BenchmarkConfig(
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
        initial_bunnies=max(0, int(args.initial_bunnies)),
        target_bunnies=max(1, int(args.target_bunnies)),
        max_bunnies=max(1, int(args.max_bunnies)),
        add_step=max(1, int(args.add_step)),
        remove_step=max(0, int(args.remove_step)),
        auto_add_per_second=max(0.0, float(args.auto_add_per_second)),
        speed_min=speed_min,
        speed_max=speed_max,
        sprite_size=max(1, int(args.sprite_size)),
        warmup_seconds=max(0.0, float(args.warmup_seconds)),
        duration_seconds=max(0.0, float(args.duration_seconds)),
        stability_seconds=max(0.0, float(args.stability_seconds)),
        max_frames=max(0, int(args.max_frames)),
        auto_stop_on_target=bool(args.auto_stop_on_target),
        report_interval=max(0.0, float(args.report_interval)),
        report_file=str(
            resolve_report_path(args.report_file, default_stem="bunny_benchmark")
        ),
        profile=str(args.profile),
        pass_ratio=pass_ratio,
        seed=args.seed,
        keyboard_controls=bool(args.keyboard_controls),
        overlay=bool(args.overlay),
        add_key=str(args.add_key),
        add_alt_key=str(args.add_alt_key),
        remove_key=str(args.remove_key),
        remove_alt_key=str(args.remove_alt_key),
    )


def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    app = BunnyBenchmarkApp(config)
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
        raise RuntimeError("benchmark scene was not initialized")

    return app.scene.build_result(elapsed)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    config = _normalize_config(args)

    result = run_benchmark(config)
    result.print_report()
    path = write_text_report(config.report_file, result.format_report())
    print(f"report_file              : {path}")
    return 0 if result.passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
