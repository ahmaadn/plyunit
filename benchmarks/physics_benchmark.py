from __future__ import annotations

import argparse
import gc
import random
import statistics
import time
from dataclasses import dataclass

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
_BODY_COLORS = [
    (64, 156, 255, 255),
    (88, 202, 122, 255),
    (244, 190, 72, 255),
    (224, 92, 92, 255),
    (164, 112, 232, 255),
]


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

    scenario: str
    initial_bodies: int
    target_bodies: int
    max_bodies: int
    add_step: int
    remove_step: int
    auto_add_per_second: float
    shape: str
    body_mode: str
    render_mode: str
    dynamic_collisions: bool

    gravity_x: float
    gravity_y: float
    spatial_hash_dim: float
    spatial_hash_count: int
    sleep_time_threshold: float
    idle_speed_threshold: float
    pymunk_iterations: int
    pymunk_damping: float
    spatial_hash_enabled: bool

    obstacle_count: int
    sensor_count: int
    queries_per_frame: int
    debug_draw: bool
    overlay: bool

    warmup_seconds: float
    duration_seconds: float
    stability_seconds: float
    max_frames: int
    auto_stop_on_target: bool
    physics_ms_budget: float | None

    report_interval: float
    report_file: str
    profile: str
    pass_ratio: float | None
    seed: int | None

    keyboard_controls: bool
    add_key: str
    add_alt_key: str
    remove_key: str
    remove_alt_key: str
    debug_key: str
    overlay_key: str


@dataclass(slots=True)
class BodyRecord:
    node: pu.NodeUnit | None
    component: pu.PhysicsBody | None
    handle: pu.PhysicsHandle | None
    shape: str
    radius: float
    width: float
    height: float
    color: tuple[int, int, int, int]


class BenchmarkBodyRenderer(pu.Component):
    def __init__(self, record: BodyRecord) -> None:
        super().__init__(name="BenchmarkBodyRenderer")
        self.record = record

    def render_submit(self, renderer, context=None) -> None:
        _ = context
        node = self.record.node
        if node is None:
            return
        world = node.world_transform_lerp()
        x, y = world.position
        if self.record.shape == "circle":
            renderer.render_circle(
                z=0,
                layer=Layer.ENTITIES,
                center=(x, y),
                radius=self.record.radius,
                color=self.record.color,
            )
            return
        renderer.render_rect(
            z=0,
            layer=Layer.ENTITIES,
            rect=(x, y, self.record.width, self.record.height),
            origin=(self.record.width * 0.5, self.record.height * 0.5),
            rotation=world.rotation,
            color=self.record.color,
        )


@dataclass(slots=True)
class BenchmarkResult:
    config: BenchmarkConfig
    stop_reason: str
    elapsed_seconds: float
    rendered_frames: int
    bodies_final: int
    bodies_peak: int
    active_sensors: int
    active_overlaps: int
    query_count: int
    query_hits: int

    avg_fps: float
    min_fps: float
    max_fps: float
    avg_fps_target_phase: float
    min_fps_target_phase: float
    max_fps_target_phase: float
    target_phase_seconds: float
    target_phase_frames: int

    avg_physics_step_ms: float
    max_physics_step_ms: float
    p95_physics_step_ms: float
    avg_pre_sync_ms: float
    avg_pymunk_step_ms: float
    avg_post_sync_ms: float
    avg_collision_dispatch_ms: float
    avg_scene_update_sync_ms: float
    avg_scene_update_nodes_ms: float
    avg_render_submit_ms: float
    avg_render_sort_ms: float
    avg_render_flush_ms: float
    avg_render_item_count: float
    avg_sleeping_body_count: float

    def format_report(self) -> str:
        lines = [
            "=== Plyunit Physics Benchmark Result ===",
            f"stop_reason              : {self.stop_reason}",
            f"elapsed_seconds          : {self.elapsed_seconds:.2f}",
            f"rendered_frames          : {self.rendered_frames}",
            f"scenario                 : {self.config.scenario}",
            f"shape                    : {self.config.shape}",
            f"body_mode                : {self.config.body_mode}",
            f"render_mode              : {self.config.render_mode}",
            f"dynamic_collisions       : {self.config.dynamic_collisions}",
            f"pymunk_iterations        : {self.config.pymunk_iterations}",
            f"spatial_hash_enabled     : {self.config.spatial_hash_enabled}",
            f"bodies_final             : {self.bodies_final}",
            f"bodies_peak              : {self.bodies_peak}",
            f"active_sensors           : {self.active_sensors}",
            f"active_overlaps          : {self.active_overlaps}",
            f"query_count              : {self.query_count}",
            f"query_hits               : {self.query_hits}",
            f"avg_fps                  : {self.avg_fps:.2f}",
            f"min_fps                  : {self.min_fps:.2f}",
            f"max_fps                  : {self.max_fps:.2f}",
            f"avg_fps_target_phase     : {self.avg_fps_target_phase:.2f}",
            f"min_fps_target_phase     : {self.min_fps_target_phase:.2f}",
            f"max_fps_target_phase     : {self.max_fps_target_phase:.2f}",
            f"target_phase_seconds     : {self.target_phase_seconds:.2f}",
            f"target_phase_frames      : {self.target_phase_frames}",
            f"avg_physics_step_ms      : {self.avg_physics_step_ms:.3f}",
            f"max_physics_step_ms      : {self.max_physics_step_ms:.3f}",
            f"p95_physics_step_ms      : {self.p95_physics_step_ms:.3f}",
            f"avg_pre_sync_ms          : {self.avg_pre_sync_ms:.3f}",
            f"avg_pymunk_step_ms       : {self.avg_pymunk_step_ms:.3f}",
            f"avg_post_sync_ms         : {self.avg_post_sync_ms:.3f}",
            f"avg_collision_dispatch_ms: {self.avg_collision_dispatch_ms:.3f}",
            f"avg_scene_update_sync_ms : {self.avg_scene_update_sync_ms:.3f}",
            f"avg_scene_update_nodes_ms: {self.avg_scene_update_nodes_ms:.3f}",
            f"avg_render_submit_ms     : {self.avg_render_submit_ms:.3f}",
            f"avg_render_sort_ms       : {self.avg_render_sort_ms:.3f}",
            f"avg_render_flush_ms      : {self.avg_render_flush_ms:.3f}",
            f"avg_render_item_count    : {self.avg_render_item_count:.1f}",
            f"avg_sleeping_body_count  : {self.avg_sleeping_body_count:.1f}",
            f"physics_ms_budget        : {self.config.physics_ms_budget}",
            f"target_bodies            : {self.config.target_bodies}",
            f"target_fps               : {self.config.target_fps}",
            f"required_min_fps         : {self.required_min_fps():.2f}",
            f"profile                  : {self.config.profile}",
            f"pass_ratio               : {self.selected_pass_ratio():.2f}",
            f"fps_mode                 : {self.config.fps_mode}",
            f"debug_draw               : {self.config.debug_draw}",
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
        if self.bodies_peak < self.config.target_bodies:
            return False
        if self.config.target_fps > 0:
            if self.target_phase_frames <= 0:
                return False
            if self.avg_fps_target_phase < self.required_min_fps():
                return False
        if self.config.physics_ms_budget is not None:
            return self.p95_physics_step_ms <= self.config.physics_ms_budget
        return True


class PhysicsBenchmarkScene(pu.SceneUnit):
    def __init__(self, app: pu.App, config: BenchmarkConfig) -> None:
        super().__init__(name="physics-benchmark-scene")
        self.app = app
        self.config = config
        self._physics: pu.Physics | None = None
        self._debug_draw: pu.PhysicsDebugDraw | None = None
        self._debug_node: pu.NodeUnit | None = None
        self._text: pu.Text | None = None

        self._bodies: list[BodyRecord] = []
        self._static_rects: list[tuple[float, float, float, float]] = []
        self._static_colors: list[tuple[int, int, int, int]] = []
        self._auto_add_accumulator = 0.0

        self._benchmark_start = 0.0
        self._last_frame_time: float | None = None
        self._last_report_time = 0.0
        self._last_fps = 0.0
        self._rendered_frames = 0
        self._peak_bodies = 0
        self._stop_reason = "window_closed"

        self._measured_time = 0.0
        self._measured_frames = 0
        self._min_fps = float("inf")
        self._max_fps = 0.0
        self._target_measured_time = 0.0
        self._target_measured_frames = 0
        self._target_min_fps = float("inf")
        self._target_max_fps = 0.0
        self._target_reached_at: float | None = None

        self._physics_step_samples_ms: list[float] = []
        self._pre_sync_samples_ms: list[float] = []
        self._pymunk_step_samples_ms: list[float] = []
        self._post_sync_samples_ms: list[float] = []
        self._collision_dispatch_samples_ms: list[float] = []
        self._sleeping_body_samples: list[float] = []
        self._scene_profile_samples: dict[str, list[float]] = {
            "update_sync_ms": [],
            "update_nodes_ms": [],
            "render_submit_ms": [],
        }
        self._renderer_profile_samples: dict[str, list[float]] = {
            "render_sort_ms": [],
            "render_flush_ms": [],
            "render_item_count": [],
        }
        self._query_count = 0
        self._query_hits = 0
        self._active_overlaps = 0

    @property
    def body_count(self) -> int:
        return len(self._bodies)

    def on_load(self) -> None:
        if self.config.seed is not None:
            random.seed(self.config.seed)

        self._physics = self.one_or_none("@Physics", scope="global")
        if self.config.overlay:
            self._text = pu.Text()
        self._build_world()
        self._add_sensors(self.config.sensor_count)
        self._add_bodies(self.config.initial_bodies, source="initial")
        self._setup_debug_draw()

        gc.collect()
        gc.freeze()

        now = time.perf_counter()
        self._benchmark_start = now
        self._last_report_time = now

        print("=== Plyunit Physics Benchmark Started ===")
        print(f"scenario       : {self.config.scenario}")
        print(f"body_mode      : {self.config.body_mode}")
        print(f"render_mode    : {self.config.render_mode}")
        print(f"initial_bodies : {self.body_count}")
        print(f"target_bodies  : {self.config.target_bodies}")
        print(f"target_fps     : {self.config.target_fps}")
        print(f"fps_mode       : {self.config.fps_mode}")
        print(f"debug_draw     : {self.config.debug_draw}")

    def on_unload(self) -> None:
        if self._physics is not None:
            self._physics.clear_statics()
        gc.unfreeze()

    def update(self, dt: float) -> None:
        self._handle_keyboard()
        self._handle_auto_add(dt)

        if self._physics is None:
            return

        # Physics auto-steps via App.on_fixed_update (subscribes on attach).
        # Sample the profile of the most recent step instead of stepping
        # manually here — a manual step() would double-step the simulation.
        elapsed = time.perf_counter() - self._benchmark_start
        if elapsed >= self.config.warmup_seconds:
            profile = self._physics.last_step_profile
            step_ms = (
                profile.pre_sync_ms + profile.pymunk_step_ms + profile.post_sync_ms
            )
            self._physics_step_samples_ms.append(step_ms)
            self._pre_sync_samples_ms.append(profile.pre_sync_ms)
            self._pymunk_step_samples_ms.append(profile.pymunk_step_ms)
            self._post_sync_samples_ms.append(profile.post_sync_ms)
            self._collision_dispatch_samples_ms.append(profile.collision_dispatch_ms)
            self._sleeping_body_samples.append(float(profile.sleeping_body_count))

        self._run_queries()
        self._active_overlaps = sum(
            len(area.get_overlapping_bodies()) for area in self._physics.get_areas()
        )
        if self.body_count > self._peak_bodies:
            self._peak_bodies = self.body_count

    def render_submit(self, renderer) -> None:
        now = time.perf_counter()
        if self._last_frame_time is not None:
            frame_dt = max(_EPSILON, now - self._last_frame_time)
            self._collect_fps_metrics(now, frame_dt)
        self._last_frame_time = now

        self._submit_world(renderer)
        if self.config.overlay:
            self._submit_overlay(renderer)

        self._collect_render_profiles(now)

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
        samples = self._physics_step_samples_ms
        avg_step = statistics.fmean(samples) if samples else 0.0
        max_step = max(samples) if samples else 0.0
        p95_step = _percentile(samples, 0.95)
        active_sensors = self._physics.area_count if self._physics is not None else 0

        return BenchmarkResult(
            config=self.config,
            stop_reason=self._stop_reason,
            elapsed_seconds=elapsed_seconds,
            rendered_frames=self._rendered_frames,
            bodies_final=self.body_count,
            bodies_peak=self._peak_bodies,
            active_sensors=active_sensors,
            active_overlaps=self._active_overlaps,
            query_count=self._query_count,
            query_hits=self._query_hits,
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
            avg_physics_step_ms=avg_step,
            max_physics_step_ms=max_step,
            p95_physics_step_ms=p95_step,
            avg_pre_sync_ms=_avg(self._pre_sync_samples_ms),
            avg_pymunk_step_ms=_avg(self._pymunk_step_samples_ms),
            avg_post_sync_ms=_avg(self._post_sync_samples_ms),
            avg_collision_dispatch_ms=_avg(self._collision_dispatch_samples_ms),
            avg_scene_update_sync_ms=_avg(
                self._scene_profile_samples["update_sync_ms"]
            ),
            avg_scene_update_nodes_ms=_avg(
                self._scene_profile_samples["update_nodes_ms"]
            ),
            avg_render_submit_ms=_avg(self._scene_profile_samples["render_submit_ms"]),
            avg_render_sort_ms=_avg(self._renderer_profile_samples["render_sort_ms"]),
            avg_render_flush_ms=_avg(self._renderer_profile_samples["render_flush_ms"]),
            avg_render_item_count=_avg(
                self._renderer_profile_samples["render_item_count"]
            ),
            avg_sleeping_body_count=_avg(self._sleeping_body_samples),
        )

    def _build_world(self) -> None:
        if self._physics is None:
            return
        width = float(self.config.window_width)
        height = float(self.config.window_height)
        thickness = 48.0
        boundary_color = (44, 52, 64, 255)
        statics = [
            (width * 0.5, height + thickness * 0.5, width, thickness),
            (-thickness * 0.5, height * 0.5, thickness, height * 2.0),
            (width + thickness * 0.5, height * 0.5, thickness, height * 2.0),
            (width * 0.5, -thickness * 0.5, width, thickness),
        ]
        for cx, cy, w, h in statics:
            self._add_static_box(cx, cy, w, h, boundary_color)

        obstacle_count = self.config.obstacle_count
        if self.config.scenario in {"mixed", "queries"}:
            obstacle_count = max(obstacle_count, 8)
        if self.config.scenario == "pile":
            obstacle_count = max(obstacle_count, 4)
        for index in range(obstacle_count):
            x = width * (0.18 + 0.64 * ((index % 5) / 4.0))
            y = height * (0.35 + 0.30 * ((index // 5) % 3) / 2.0)
            w = random.uniform(80.0, 150.0)
            h = random.uniform(12.0, 28.0)
            self._add_static_box(x, y, w, h, (58, 68, 82, 255))

    def _add_static_box(
        self,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        color: tuple[int, int, int, int],
    ) -> None:
        if self._physics is None:
            return
        static = pu.StaticBody(
            position=(center_x, center_y),
            shapes=[pu.BoxShape(width=width, height=height, friction=0.9)],
            filter=pu.CollisionFilter.world_static(),
        )
        self._physics.add_static(static)
        self._static_rects.append((
            center_x - width * 0.5,
            center_y - height * 0.5,
            width,
            height,
        ))
        self._static_colors.append(color)

    def _add_sensors(self, count: int) -> None:
        if count <= 0:
            return
        width = float(self.config.window_width)
        height = float(self.config.window_height)
        for index in range(count):
            area_node = pu.NodeUnit(name="BenchmarkSensor")
            area = area_node.add_component(
                pu.PhysicsArea.sensor(name="BenchmarkSensor")
            )
            x = width * (0.2 + 0.6 * ((index % 4) / 3.0))
            y = height * (0.32 + 0.38 * ((index // 4) % 3) / 2.0)
            area_node.transform.set_position(x, y)
            area.filter = pu.CollisionFilter.sensor()
            area.add_shape(pu.CircleShape(radius=54.0))
            self.root.attach(area_node)

    def _add_bodies(self, count: int, *, source: str = "auto") -> int:
        _ = source
        if count <= 0:
            return 0
        allowed = max(0, self.config.max_bodies - self.body_count)
        to_add = min(count, allowed)
        for _index in range(to_add):
            x, y = self._spawn_position()
            shape_name = self._select_shape()
            color = random.choice(_BODY_COLORS)
            shapes = []
            fixed_rotation = False
            if shape_name == "circle":
                radius = random.uniform(8.0, 16.0)
                shapes.append(
                    pu.CircleShape(radius=radius, friction=0.45, elasticity=0.25)
                )
                shape_data = ("circle", radius, radius * 2.0, radius * 2.0)
            else:
                width = random.uniform(16.0, 30.0)
                height = random.uniform(16.0, 30.0)
                fixed_rotation = self.config.scenario != "pile"
                shapes.append(
                    pu.BoxShape(
                        width=width, height=height, friction=0.55, elasticity=0.15
                    )
                )
                shape_data = ("box", 0.0, width, height)
            body_filter = pu.CollisionFilter.dynamic_actor(
                collide_with_dynamic=self.config.dynamic_collisions
            )
            if self.config.body_mode == "bulk":
                if self._physics is None:
                    continue
                handle = self._physics.create_body(
                    position=(x, y),
                    body_type=pu.BodyType.DYNAMIC,
                    shapes=shapes,
                    mass=1.0,
                    filter=body_filter,
                    fixed_rotation=fixed_rotation,
                )
                record = BodyRecord(None, None, handle, *shape_data, color)
            else:
                body_node = pu.NodeUnit(name="BenchmarkBody")
                body_node.transform.set_position(x, y)
                body = body_node.add_component(pu.PhysicsBody.dynamic(mass=1.0))
                body.fixed_rotation = fixed_rotation
                body.filter = body_filter
                for shape in shapes:
                    body.add_shape(shape)
                record = BodyRecord(body_node, body, None, *shape_data, color)
                if self.config.render_mode == "primitive":
                    body_node.add_component(BenchmarkBodyRenderer(record))
                self.root.attach(body_node)
            if self.config.scenario in {"rain", "mixed"}:
                velocity = (random.uniform(-40.0, 40.0), random.uniform(-20.0, 20.0))
                if record.handle is not None and self._physics is not None:
                    self._physics.set_body_state(record.handle, velocity=velocity)
                elif record.component is not None:
                    record.component.velocity = velocity
            self._bodies.append(record)
        return to_add

    def _remove_bodies(self, count: int) -> int:
        to_remove = min(count, self.body_count)
        if to_remove <= 0:
            return 0
        for record in self._bodies[-to_remove:]:
            if record.handle is not None and self._physics is not None:
                self._physics.destroy_body(record.handle)
            elif record.node is not None:
                record.node.destroy()
        del self._bodies[-to_remove:]
        return to_remove

    def _spawn_position(self) -> tuple[float, float]:
        width = float(self.config.window_width)
        if self.config.scenario == "pile":
            return (
                random.uniform(width * 0.42, width * 0.58),
                random.uniform(20.0, 180.0),
            )
        if self.config.scenario == "rain":
            return (random.uniform(64.0, width - 64.0), random.uniform(-260.0, 80.0))
        if self.config.scenario == "sensors":
            return (
                random.uniform(width * 0.2, width * 0.8),
                random.uniform(20.0, 220.0),
            )
        return (random.uniform(64.0, width - 64.0), random.uniform(20.0, 260.0))

    def _select_shape(self) -> str:
        if self.config.shape in {"circle", "box"}:
            return self.config.shape
        if self.config.scenario == "pile":
            return "box" if random.random() < 0.65 else "circle"
        return "circle" if random.random() < 0.65 else "box"

    def _setup_debug_draw(self) -> None:
        self._debug_node = pu.NodeUnit(name="PhysicsBenchmarkDebug")
        self._debug_draw = pu.PhysicsDebugDraw(
            draw_bodies=True,
            draw_statics=True,
            draw_areas=True,
            draw_contacts=True,
        )
        self._debug_draw.enabled = self.config.debug_draw
        self._debug_node.add_component(self._debug_draw)
        self.root.attach(self._debug_node)

    def _handle_keyboard(self) -> None:
        if not self.config.keyboard_controls:
            return
        kb = self.one_or_none("@Input", scope="global")
        if kb is None:
            return
        if kb.is_pressed("add"):
            self._add_bodies(self.config.add_step, source="keyboard")
        if self.config.remove_step > 0 and kb.is_pressed("remove"):
            self._remove_bodies(self.config.remove_step)
        if kb.is_pressed("toggle_debug") and self._debug_draw is not None:
            self._debug_draw.enabled = not self._debug_draw.enabled
        if kb.is_pressed("toggle_overlay"):
            self.config.overlay = not self.config.overlay

    def _handle_auto_add(self, dt: float) -> None:
        if self.config.auto_add_per_second <= 0.0:
            return
        self._auto_add_accumulator += dt * self.config.auto_add_per_second
        to_add = int(self._auto_add_accumulator)
        if to_add <= 0:
            return
        self._auto_add_accumulator -= to_add
        self._add_bodies(to_add, source="auto")

    def _run_queries(self) -> None:
        if self._physics is None or self.config.queries_per_frame <= 0:
            return
        width = float(self.config.window_width)
        height = float(self.config.window_height)
        for index in range(self.config.queries_per_frame):
            if index % 2 == 0:
                x = random.uniform(0.0, width)
                y = random.uniform(0.0, height)
                hits = self._physics.point_query(x, y, max_distance=12.0)
            else:
                y = random.uniform(0.0, height)
                hits = self._physics.ray_cast((0.0, y), (width, y), radius=1.0)
            self._query_count += 1
            self._query_hits += len(hits)

    def _collect_render_profiles(self, now: float) -> None:
        elapsed = now - self._benchmark_start
        if elapsed < self.config.warmup_seconds:
            return
        for key, bucket in self._scene_profile_samples.items():
            bucket.append(float(self.last_frame_profile.get(key, 0.0)))
        renderer_profile = getattr(self.app.renderer, "frame_profile", {})
        for key, bucket in self._renderer_profile_samples.items():
            bucket.append(float(renderer_profile.get(key, 0.0)))

    def _submit_world(self, renderer) -> None:
        if self.config.render_mode == "none":
            return
        sprite_mode = self.config.render_mode == "sprite"
        if self._static_rects:
            renderer.render_rects(
                z=-10,
                layer=Layer.WORLD,
                rects=self._static_rects,
                colors=self._static_colors,
            )

        circles_pos = []
        circles_rad = []
        circles_col = []
        rects = []
        rect_cols = []

        if self.config.body_mode == "component":
            return

        for record in self._bodies:
            if record.handle is not None and self._physics is not None:
                state = self._physics.get_body_state(record.handle)
                if state is None:
                    continue
                x, y, rotation = state
            elif record.node is not None:
                world = record.node.world_transform_lerp()
                x, y = world.position
                rotation = world.rotation
            else:
                continue
            if record.shape == "circle":
                if sprite_mode:
                    renderer.render_circle(
                        z=0,
                        layer=Layer.ENTITIES,
                        center=(x, y),
                        radius=record.radius,
                        color=record.color,
                    )
                else:
                    circles_pos.append((x, y))
                    circles_rad.append(record.radius)
                    circles_col.append(record.color)
            elif abs(rotation) < 0.001:
                rects.append((
                    x - record.width * 0.5,
                    y - record.height * 0.5,
                    record.width,
                    record.height,
                ))
                rect_cols.append(record.color)
            else:
                renderer.render_rect(
                    z=0,
                    layer=Layer.ENTITIES,
                    rect=(x, y, record.width, record.height),
                    origin=(record.width * 0.5, record.height * 0.5),
                    rotation=rotation,
                    color=record.color,
                )

        if circles_pos:
            renderer.render_circles(
                z=0,
                layer=Layer.ENTITIES,
                centers=circles_pos,
                radii=circles_rad,
                colors=circles_col,
            )
        if rects:
            renderer.render_rects(
                z=0,
                layer=Layer.ENTITIES,
                rects=rects,
                colors=rect_cols,
            )

    def _submit_overlay(self, renderer) -> None:
        _ = renderer
        if self._text is None:
            return
        debug_on = self._debug_draw.enabled if self._debug_draw is not None else False
        self._text.push(
            (
                f"Physics bodies: {self.body_count}/{self.config.target_bodies} | "
                f"FPS: {self._last_fps:.1f} | "
                f"Physics p95: {_percentile(self._physics_step_samples_ms, 0.95):.2f} ms | "  # noqa: E501
                f"Sensors: {self.config.sensor_count} overlaps: {self._active_overlaps} | "  # noqa: E501
                f"Queries: {self._query_count} hits: {self._query_hits} | "
                f"Debug: {debug_on}"
            ),
            pos=(12.0, 12.0),
            color=(24, 28, 36, 255),
            font_size=18,
            spacing=1.0,
            z=0,
            layer=Layer.UI,
        )

    def _collect_fps_metrics(self, now: float, frame_dt: float) -> None:
        elapsed = now - self._benchmark_start
        if elapsed < self.config.warmup_seconds:
            return
        fps = 1.0 / frame_dt
        self._last_fps = fps
        self._measured_frames += 1
        self._measured_time += frame_dt
        self._min_fps = min(self._min_fps, fps)
        self._max_fps = max(self._max_fps, fps)

        if self.body_count >= self.config.target_bodies:
            if self._target_reached_at is None:
                self._target_reached_at = now
                print(f"target reached: bodies={self.body_count} at {elapsed:.2f}s")
            self._target_measured_frames += 1
            self._target_measured_time += frame_dt
            self._target_min_fps = min(self._target_min_fps, fps)
            self._target_max_fps = max(self._target_max_fps, fps)

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
        avg_step = (
            statistics.fmean(self._physics_step_samples_ms)
            if self._physics_step_samples_ms
            else 0.0
        )
        print(
            f"[progress] t={elapsed:6.2f}s bodies={self.body_count:6d} "
            f"fps_now={self._last_fps:7.2f} fps_avg={avg_fps:7.2f} "
            f"physics_avg_ms={avg_step:6.3f}"
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


class PhysicsBenchmarkApp(pu.App):
    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__()
        self.benchmark_config = config
        self.scene: PhysicsBenchmarkScene | None = None
        self.physics: pu.Physics | None = None

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
        self.input.map("toggle_debug", _resolve_key(cfg.debug_key))
        self.input.map("toggle_overlay", _resolve_key(cfg.overlay_key))

        self.physics = pu.Physics(
            gravity=(cfg.gravity_x, cfg.gravity_y),
            world_bounds=(
                -2000.0,
                -2000.0,
                cfg.window_width + 2000.0,
                cfg.window_height + 2000.0,
            ),
            spatial_hash_dim=cfg.spatial_hash_dim,
            spatial_hash_count=cfg.spatial_hash_count,
            sleep_time_threshold=cfg.sleep_time_threshold,
            idle_speed_threshold=cfg.idle_speed_threshold,
            iterations=cfg.pymunk_iterations,
            damping=cfg.pymunk_damping,
            enable_spatial_hash=cfg.spatial_hash_enabled,
        )
        self.physics.profile_enabled = True
        self.scene = PhysicsBenchmarkScene(self, cfg)
        self.scene.profile_enabled = True
        self.renderer.profile_enabled = True
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


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = round((len(sorted_values) - 1) * max(0.0, min(1.0, quantile)))
    return sorted_values[index]


def _avg(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _resolve_key(name: str) -> int:
    normalized = name.strip().upper()
    key_name = normalized if normalized.startswith("KEY_") else f"KEY_{normalized}"
    key_value = getattr(pr, key_name, None)
    if key_value is None:
        raise ValueError(f"Unknown key name: {name}")
    return int(key_value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plyunit rendered pymunk physics benchmark"
    )
    parser.add_argument("--title", default="Plyunit Physics Benchmark")
    parser.add_argument("--window-width", type=int, default=1280)
    parser.add_argument("--window-height", type=int, default=720)
    parser.add_argument("--target-fps", type=int, default=60)
    parser.add_argument("--fps-mode", choices=["capped", "uncapped"], default="capped")
    parser.add_argument("--fixed-update-hz", type=int, default=60)
    parser.add_argument("--max-substeps-per-frame", type=int, default=1)
    parser.add_argument("--max-frame-delta-time", type=float, default=0.25)

    parser.add_argument(
        "--scenario",
        choices=["baseline", "mixed", "pile", "rain", "sensors", "queries"],
        default="baseline",
    )
    parser.add_argument("--initial-bodies", type=int, default=500)
    parser.add_argument("--target-bodies", type=int, default=1000)
    parser.add_argument("--max-bodies", type=int, default=5000)
    parser.add_argument("--add-step", type=int, default=100)
    parser.add_argument("--remove-step", type=int, default=100)
    parser.add_argument("--auto-add-per-second", type=float, default=0.0)
    parser.add_argument("--shape", choices=["mixed", "circle", "box"], default="mixed")
    parser.add_argument("--body-mode", choices=["bulk", "component"], default="bulk")
    parser.add_argument(
        "--render-mode", choices=["primitive", "sprite", "none"], default="primitive"
    )
    parser.add_argument(
        "--dynamic-collisions", action=argparse.BooleanOptionalAction, default=False
    )

    parser.add_argument("--gravity-x", type=float, default=0.0)
    parser.add_argument("--gravity-y", type=float, default=900.0)
    parser.add_argument("--spatial-hash-dim", type=float, default=80.0)
    parser.add_argument("--spatial-hash-count", type=int, default=20000)
    parser.add_argument("--sleep-time-threshold", type=float, default=0.5)
    parser.add_argument("--idle-speed-threshold", type=float, default=10.0)
    parser.add_argument("--pymunk-iterations", type=int, default=10)
    parser.add_argument("--pymunk-damping", type=float, default=1.0)
    parser.add_argument(
        "--spatial-hash", action=argparse.BooleanOptionalAction, default=True
    )

    parser.add_argument("--obstacle-count", type=int, default=0)
    parser.add_argument("--sensor-count", type=int, default=8)
    parser.add_argument("--queries-per-frame", type=int, default=0)
    parser.add_argument(
        "--debug-draw", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument(
        "--overlay", action=argparse.BooleanOptionalAction, default=True
    )

    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--stability-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument(
        "--auto-stop-on-target", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--physics-ms-budget", type=float, default=None)

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
            "benchmarks/report/physics_benchmark_<timestamp>.txt"
        ),
    )
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument(
        "--keyboard-controls", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--add-key", default="EQUAL")
    parser.add_argument("--add-alt-key", default="KP_ADD")
    parser.add_argument("--remove-key", default="MINUS")
    parser.add_argument("--remove-alt-key", default="KP_SUBTRACT")
    parser.add_argument("--debug-key", default="D")
    parser.add_argument("--overlay-key", default="O")

    parser.add_argument("--bg-r", type=int, default=238)
    parser.add_argument("--bg-g", type=int, default=241)
    parser.add_argument("--bg-b", type=int, default=245)
    parser.add_argument("--bg-a", type=int, default=255)
    return parser


def _normalize_config(args: argparse.Namespace) -> BenchmarkConfig:
    pass_ratio = None
    if args.pass_ratio is not None:
        pass_ratio = max(0.0, min(1.0, float(args.pass_ratio)))
    physics_budget = None
    if args.physics_ms_budget is not None:
        physics_budget = max(0.0, float(args.physics_ms_budget))
    sensor_count = max(0, int(args.sensor_count))
    queries_per_frame = max(0, int(args.queries_per_frame))
    if args.scenario == "sensors":
        sensor_count = max(sensor_count, 24)
    if args.scenario == "queries":
        queries_per_frame = max(queries_per_frame, 128)
    if args.scenario == "baseline":
        sensor_count = 0

    return BenchmarkConfig(
        title=str(args.title),
        window_width=max(240, int(args.window_width)),
        window_height=max(180, int(args.window_height)),
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
        scenario=str(args.scenario),
        initial_bodies=max(0, int(args.initial_bodies)),
        target_bodies=max(1, int(args.target_bodies)),
        max_bodies=max(1, int(args.max_bodies)),
        add_step=max(1, int(args.add_step)),
        remove_step=max(0, int(args.remove_step)),
        auto_add_per_second=max(0.0, float(args.auto_add_per_second)),
        shape=str(args.shape),
        body_mode=str(args.body_mode),
        render_mode=str(args.render_mode),
        dynamic_collisions=bool(args.dynamic_collisions),
        gravity_x=float(args.gravity_x),
        gravity_y=float(args.gravity_y),
        spatial_hash_dim=max(1.0, float(args.spatial_hash_dim)),
        spatial_hash_count=max(1, int(args.spatial_hash_count)),
        sleep_time_threshold=max(0.0, float(args.sleep_time_threshold)),
        idle_speed_threshold=max(0.0, float(args.idle_speed_threshold)),
        pymunk_iterations=max(1, int(args.pymunk_iterations)),
        pymunk_damping=max(0.0, float(args.pymunk_damping)),
        spatial_hash_enabled=bool(args.spatial_hash),
        obstacle_count=max(0, int(args.obstacle_count)),
        sensor_count=sensor_count,
        queries_per_frame=queries_per_frame,
        debug_draw=bool(args.debug_draw),
        overlay=bool(args.overlay),
        warmup_seconds=max(0.0, float(args.warmup_seconds)),
        duration_seconds=max(0.0, float(args.duration_seconds)),
        stability_seconds=max(0.0, float(args.stability_seconds)),
        max_frames=max(0, int(args.max_frames)),
        auto_stop_on_target=bool(args.auto_stop_on_target),
        physics_ms_budget=physics_budget,
        report_interval=max(0.0, float(args.report_interval)),
        report_file=str(
            resolve_report_path(args.report_file, default_stem="physics_benchmark")
        ),
        profile=str(args.profile),
        pass_ratio=pass_ratio,
        seed=args.seed,
        keyboard_controls=bool(args.keyboard_controls),
        add_key=str(args.add_key),
        add_alt_key=str(args.add_alt_key),
        remove_key=str(args.remove_key),
        remove_alt_key=str(args.remove_alt_key),
        debug_key=str(args.debug_key),
        overlay_key=str(args.overlay_key),
    )


def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    app = PhysicsBenchmarkApp(config)
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
    print(result.format_report())
    path = write_text_report(config.report_file, result.format_report())
    print(f"report_file              : {path}")
    return 0 if result.passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
