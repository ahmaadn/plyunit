from __future__ import annotations

import argparse
import gc
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pyray as pr

import plyunit as pu
from benchmarks.report_paths import (
    resolve_report_json_path,
    resolve_report_path,
    write_text_report,
)
from plyunit.core.components.builtin import SpriteRenderer

PROFILE_PASS_RATIO = {"strict": 0.95, "balanced": 0.90, "igpu": 0.80}
_EPSILON = 1e-6
_DEFAULT_TEXTURE = Path(__file__).resolve().parent / "data" / "test.png"


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
    nodes: int
    depth: int
    branching: int
    layout_spacing_x: float
    layout_spacing_y: float
    animate: bool
    speed_min: float
    speed_max: float
    sprite_size: int
    texture_path: str
    warmup_seconds: float
    duration_seconds: float
    stability_seconds: float
    max_frames: int
    auto_stop_on_target: bool
    report_interval: float
    report_file: str
    report_json: str
    profile_engine: bool
    print_breakdown: bool
    profile: str
    pass_ratio: float | None
    seed: int | None
    overlay: bool


@dataclass(slots=True)
class BenchmarkResult:
    config: BenchmarkConfig
    stop_reason: str
    elapsed_seconds: float
    rendered_frames: int
    nodes_final: int
    depth_actual: int
    avg_fps: float
    min_fps: float
    max_fps: float
    avg_fps_target_phase: float
    min_fps_target_phase: float
    max_fps_target_phase: float
    target_phase_seconds: float
    target_phase_frames: int
    engine_profile: dict[str, float]

    def selected_pass_ratio(self) -> float:
        ratio = self.config.pass_ratio
        if ratio is None:
            ratio = PROFILE_PASS_RATIO[self.config.profile]
        return max(0.0, min(1.0, ratio))

    def required_min_fps(self) -> float:
        return self.config.target_fps * self.selected_pass_ratio()

    def passed(self) -> bool:
        if self.config.target_fps <= 0:
            return True
        return (
            self.target_phase_frames > 0
            and self.avg_fps_target_phase >= self.required_min_fps()
        )

    def format_report(self) -> str:
        lines = [
            "=== Plyunit Node Tree Benchmark Result ===",
            f"stop_reason              : {self.stop_reason}",
            f"elapsed_seconds          : {self.elapsed_seconds:.2f}",
            f"rendered_frames          : {self.rendered_frames}",
            f"nodes_final              : {self.nodes_final}",
            f"depth_requested          : {self.config.depth}",
            f"depth_actual             : {self.depth_actual}",
            f"branching                : {self.config.branching}",
            f"avg_fps                  : {self.avg_fps:.2f}",
            f"min_fps                  : {self.min_fps:.2f}",
            f"max_fps                  : {self.max_fps:.2f}",
            f"avg_fps_target_phase     : {self.avg_fps_target_phase:.2f}",
            f"min_fps_target_phase     : {self.min_fps_target_phase:.2f}",
            f"max_fps_target_phase     : {self.max_fps_target_phase:.2f}",
            f"target_phase_seconds     : {self.target_phase_seconds:.2f}",
            f"target_phase_frames      : {self.target_phase_frames}",
            f"target_fps               : {self.config.target_fps}",
            f"required_min_fps         : {self.required_min_fps():.2f}",
            f"profile                  : {self.config.profile}",
            f"pass_ratio               : {self.selected_pass_ratio():.2f}",
            f"fps_mode                 : {self.config.fps_mode}",
            f"animate                  : {self.config.animate}",
            f"pass                     : {self.passed()}",
        ]
        if self.engine_profile:
            lines.append("--- Engine Profile Averages ---")
            for key in sorted(self.engine_profile):
                value = self.engine_profile[key]
                suffix = "ms" if key.endswith("_ms") else ""
                lines.append(f"{key:25}: {value:.3f}{suffix}")
        return "\n".join(lines)

    def to_json_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["pass"] = self.passed()
        data["required_min_fps"] = self.required_min_fps()
        data["pass_ratio_selected"] = self.selected_pass_ratio()
        return data

    def print_report(self) -> None:
        print(self.format_report())


class BenchNode(pu.NodeUnit):
    def __init__(
        self,
        name: str,
        *,
        local_position: tuple[float, float],
        velocity: tuple[float, float],
        bounds: tuple[float, float],
        animate: bool,
    ) -> None:
        super().__init__(name=name)
        self.transform.set_position(*local_position)
        self.velocity = velocity
        self.bounds = bounds
        self.animate = animate

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        vx, vy = self.velocity
        x += vx * dt
        y += vy * dt
        max_x, max_y = self.bounds
        if x < -max_x or x > max_x:
            vx = -vx
            x = max(-max_x, min(max_x, x))
        if y < -max_y or y > max_y:
            vy = -vy
            y = max(-max_y, min(max_y, y))
        self.velocity = (vx, vy)
        self.transform.set_position(x, y)


class StaticBenchNode(pu.NodeUnit):
    def __init__(self, name: str, *, local_position: tuple[float, float]) -> None:
        super().__init__(name=name)
        self.transform.set_position(*local_position)


class NodeBenchmarkScene(pu.SceneUnit):
    def __init__(self, app: pu.App, config: BenchmarkConfig) -> None:
        super().__init__(name="node-tree-benchmark-scene")
        self.app = app
        self.config = config
        self.texture = None
        self._text: pu.Text | None = None
        self.nodes_created = 0
        self.depth_actual = 0
        self._benchmark_start = 0.0
        self._last_frame_time: float | None = None
        self._last_report_time = 0.0
        self._last_fps = 0.0
        self._measured_time = 0.0
        self._measured_frames = 0
        self._min_fps = float("inf")
        self._max_fps = 0.0
        self._target_reached_at: float | None = None
        self._target_measured_time = 0.0
        self._target_measured_frames = 0
        self._target_min_fps = float("inf")
        self._target_max_fps = 0.0
        self._rendered_frames = 0
        self._stop_reason = "window_closed"
        self._engine_profile_totals: dict[str, float] = {}
        self._engine_profile_frames = 0

    def on_load(self) -> None:
        if self.config.seed is not None:
            random.seed(self.config.seed)
        self.texture = pr.load_texture(self.config.texture_path)
        if self.config.overlay:
            self._text = pu.Text()
        self.profile_enabled = self.config.profile_engine
        self.app.renderer.profile_enabled = self.config.profile_engine
        self._build_tree()
        gc.collect()
        gc.freeze()
        now = time.perf_counter()
        self._benchmark_start = now
        self._last_report_time = now
        print("=== Plyunit Node Tree Benchmark Started ===")
        print(f"nodes          : {self.nodes_created}")
        print(f"depth_requested: {self.config.depth}")
        print(f"depth_actual   : {self.depth_actual}")
        print(f"branching      : {self.config.branching}")
        print(f"fps_mode       : {self.config.fps_mode}")
        print(f"animate        : {self.config.animate}")

    def on_unload(self) -> None:
        if self.texture is not None:
            pr.unload_texture(self.texture)
            self.texture = None
        gc.unfreeze()

    def render_submit(self, renderer) -> None:
        now = time.perf_counter()
        if self._last_frame_time is not None:
            self._collect_metrics(now, max(_EPSILON, now - self._last_frame_time))
        self._last_frame_time = now

        if self.config.overlay and self._text is not None:
            self._text.push(
                (
                    f"Nodes: {self.nodes_created} | Depth: {self.depth_actual} | "
                    f"FPS: {self._last_fps:.1f}"
                ),
                pos=(12.0, 12.0),
                color=(30, 30, 30, 255),
                font_size=20,
                spacing=1.0,
                z=0,
                layer=pu.Layer.UI,
            )

        self._rendered_frames += 1
        self._maybe_print_progress(now)
        self._maybe_stop(now)

    def build_result(self, elapsed_seconds: float) -> BenchmarkResult:
        avg_fps = self._measured_frames / max(_EPSILON, self._measured_time)
        target_avg = self._target_measured_frames / max(
            _EPSILON, self._target_measured_time
        )
        return BenchmarkResult(
            config=self.config,
            stop_reason=self._stop_reason,
            elapsed_seconds=elapsed_seconds,
            rendered_frames=self._rendered_frames,
            nodes_final=self.nodes_created,
            depth_actual=self.depth_actual,
            avg_fps=avg_fps if self._measured_frames else 0.0,
            min_fps=0.0 if self._measured_frames == 0 else self._min_fps,
            max_fps=self._max_fps,
            avg_fps_target_phase=target_avg if self._target_measured_frames else 0.0,
            min_fps_target_phase=(
                0.0 if self._target_measured_frames == 0 else self._target_min_fps
            ),
            max_fps_target_phase=self._target_max_fps,
            target_phase_seconds=self._target_measured_time,
            target_phase_frames=self._target_measured_frames,
            engine_profile=self._engine_profile_average(),
        )

    def collect_engine_profile(self) -> None:
        if not self.config.profile_engine:
            return
        profile = {
            **self.last_frame_profile,
            **self.app.renderer.last_frame_profile,
        }
        if not profile:
            return
        for key, value in profile.items():
            self._engine_profile_totals[key] = self._engine_profile_totals.get(
                key, 0.0
            ) + float(value)
        self._engine_profile_frames += 1

        if self.config.print_breakdown and self._rendered_frames % 60 == 0:
            details = " ".join(
                f"{key}={value:.2f}" for key, value in sorted(profile.items())
            )
            print(f"[engine] frame={self._rendered_frames} {details}")

    def _engine_profile_average(self) -> dict[str, float]:
        if self._engine_profile_frames <= 0:
            return {}
        return {
            key: value / self._engine_profile_frames
            for key, value in self._engine_profile_totals.items()
        }

    def _build_tree(self) -> None:
        if self.texture is None:
            raise RuntimeError("benchmark texture was not initialized")
        root = self._create_node(
            depth=0,
            index=0,
            position=(self.config.window_width * 0.5, self.config.window_height * 0.5),
        )
        self.root.attach(root)
        queue: list[tuple[pu.NodeUnit, int, int]] = [(root, 1, 0)]
        head = 0
        while head < len(queue) and self.nodes_created < self.config.nodes:
            parent, depth, sibling_index = queue[head]
            head += 1
            if depth >= self.config.depth:
                continue
            for child_index in range(self.config.branching):
                if self.nodes_created >= self.config.nodes:
                    break
                spread = (self.config.branching - 1) * self.config.layout_spacing_x
                local_x = child_index * self.config.layout_spacing_x - spread * 0.5
                local_x += math.sin((sibling_index + child_index) * 0.73) * 4.0
                child = self._create_node(
                    depth=depth,
                    index=child_index,
                    position=(local_x, self.config.layout_spacing_y),
                )
                parent.attach(child)
                queue.append((child, depth + 1, child_index))

    def _create_node(
        self, *, depth: int, index: int, position: tuple[float, float]
    ) -> pu.NodeUnit:
        speed = random.uniform(self.config.speed_min, self.config.speed_max)
        angle = random.uniform(0.0, math.tau)
        if self.config.animate:
            node = BenchNode(
                name=f"bench-node-{self.nodes_created}",
                local_position=position,
                velocity=(math.cos(angle) * speed, math.sin(angle) * speed),
                bounds=(
                    self.config.layout_spacing_x * 0.35,
                    self.config.layout_spacing_y * 0.35,
                ),
                animate=self.config.animate,
            )
        else:
            node = StaticBenchNode(
                name=f"bench-node-{self.nodes_created}",
                local_position=position,
            )
        node.layer = int(pu.Layer.ENTITIES)
        node.z_index = 0
        # pyrefly: ignore [missing-attribute]
        scale = self.config.sprite_size / max(1.0, float(self.texture.width))
        node.add_component(
            SpriteRenderer(
                texture=self.texture,
                layer=int(pu.Layer.ENTITIES),
                z_index=0,
                scale=scale,
                use_interpolation=True,
            )
        )
        self.nodes_created += 1
        self.depth_actual = max(self.depth_actual, depth + 1)
        return node

    def _collect_metrics(self, now: float, frame_dt: float) -> None:
        elapsed = now - self._benchmark_start
        if elapsed < self.config.warmup_seconds:
            return
        fps = 1.0 / frame_dt
        self._last_fps = fps
        self._measured_frames += 1
        self._measured_time += frame_dt
        self._min_fps = min(self._min_fps, fps)
        self._max_fps = max(self._max_fps, fps)
        if self._target_reached_at is None:
            self._target_reached_at = now
            print(f"target reached: nodes={self.nodes_created} at {elapsed:.2f}s")
        self._target_measured_frames += 1
        self._target_measured_time += frame_dt
        self._target_min_fps = min(self._target_min_fps, fps)
        self._target_max_fps = max(self._target_max_fps, fps)

    def _maybe_print_progress(self, now: float) -> None:
        if self.config.report_interval <= 0.0:
            return
        if now - self._last_report_time < self.config.report_interval:
            return
        avg_fps = self._measured_frames / max(_EPSILON, self._measured_time)
        print(
            f"[progress] t={now - self._benchmark_start:6.2f}s "
            f"nodes={self.nodes_created:6d} "
            f"fps_now={self._last_fps:7.2f} "
            f"fps_avg={avg_fps if self._measured_frames else 0.0:7.2f}"
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


class NodeBenchmarkApp(pu.App):
    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__()
        self.benchmark_config = config
        self.scene: NodeBenchmarkScene | None = None

    def on_load(self) -> None:
        self.scene = NodeBenchmarkScene(self, self.benchmark_config)
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

    def _end_frame(self) -> None:
        if self.scene is not None:
            self.scene.collect_engine_profile()
        super()._end_frame()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plyunit node tree benchmark: one node draws one sprite."
    )
    parser.add_argument("--title", default="Plyunit Node Tree Benchmark")
    parser.add_argument("--window-width", type=int, default=1280)
    parser.add_argument("--window-height", type=int, default=720)
    parser.add_argument("--target-fps", type=int, default=60)
    parser.add_argument(
        "--fps-mode", choices=["capped", "uncapped"], default="uncapped"
    )
    parser.add_argument("--fixed-update-hz", type=int, default=60)
    parser.add_argument("--max-substeps-per-frame", type=int, default=1)
    parser.add_argument("--max-frame-delta-time", type=float, default=0.25)
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--branching", type=int, default=4)
    parser.add_argument("--layout-spacing-x", type=float, default=28.0)
    parser.add_argument("--layout-spacing-y", type=float, default=36.0)
    parser.add_argument(
        "--animate", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument("--speed-min", type=float, default=8.0)
    parser.add_argument("--speed-max", type=float, default=32.0)
    parser.add_argument("--sprite-size", type=int, default=16)
    parser.add_argument("--texture", default=str(_DEFAULT_TEXTURE))
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
            "benchmarks/report/node_benchmark_<timestamp>.txt"
        ),
    )
    parser.add_argument(
        "--report-json",
        default="",
        help=(
            "Optional JSON report path. Relative names go under "
            "benchmarks/report/ (timestamped or sibling of --report-file)."
        ),
    )
    parser.add_argument("--profile-engine", action="store_true")
    parser.add_argument("--print-breakdown", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--overlay", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--bg-r", type=int, default=245)
    parser.add_argument("--bg-g", type=int, default=245)
    parser.add_argument("--bg-b", type=int, default=245)
    parser.add_argument("--bg-a", type=int, default=255)
    return parser


def _normalize_config(args: argparse.Namespace) -> BenchmarkConfig:
    texture_path = Path(str(args.texture)).resolve()
    if not texture_path.exists():
        raise FileNotFoundError(f"benchmark texture not found: {texture_path}")
    pass_ratio = None
    if args.pass_ratio is not None:
        pass_ratio = max(0.0, min(1.0, float(args.pass_ratio)))
    speed_min = max(0.0, float(args.speed_min))
    speed_max = max(speed_min, float(args.speed_max))
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
        nodes=max(1, int(args.nodes)),
        depth=max(1, int(args.depth)),
        branching=max(1, int(args.branching)),
        layout_spacing_x=max(1.0, float(args.layout_spacing_x)),
        layout_spacing_y=max(1.0, float(args.layout_spacing_y)),
        animate=bool(args.animate),
        speed_min=speed_min,
        speed_max=speed_max,
        sprite_size=max(1, int(args.sprite_size)),
        texture_path=str(texture_path),
        warmup_seconds=max(0.0, float(args.warmup_seconds)),
        duration_seconds=max(0.0, float(args.duration_seconds)),
        stability_seconds=max(0.0, float(args.stability_seconds)),
        max_frames=max(0, int(args.max_frames)),
        auto_stop_on_target=bool(args.auto_stop_on_target),
        report_interval=max(0.0, float(args.report_interval)),
        report_file=str(
            resolve_report_path(args.report_file, default_stem="node_benchmark")
        ),
        report_json=str(args.report_json),
        profile_engine=bool(args.profile_engine),
        print_breakdown=bool(args.print_breakdown),
        profile=str(args.profile),
        pass_ratio=pass_ratio,
        seed=args.seed,
        overlay=bool(args.overlay),
    )


def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    app = NodeBenchmarkApp(config)
    target_fps = 0 if config.fps_mode == "uncapped" else config.target_fps
    pu.init(
        app,
        pu.AppConfig(
            title=config.title,
            window_width=config.window_width,
            window_height=config.window_height,
            target_fps=target_fps,
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
    config = _normalize_config(parser.parse_args())
    result = run_benchmark(config)
    result.print_report()
    path = write_text_report(config.report_file, result.format_report())
    print(f"report_file              : {path}")
    json_path = resolve_report_json_path(
        config.report_json, text_report=Path(config.report_file)
    )
    if json_path is not None:
        with open(json_path, "w", encoding="utf-8") as report_file:
            json.dump(result.to_json_dict(), report_file, indent=2)
            report_file.write("\n")
        print(f"report_json              : {json_path}")
    return 0 if result.passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
