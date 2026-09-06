"""Profiling harness to isolate CPU vs GPU cost in primitive drawing.

Three microbenchmarks:
1. GPU-only: Pre-converted data, measure draw throughput (fill rate)
2. CPU-only: Full pipeline without actual GPU draw (conversion overhead)
3. Full: End-to-end with cProfile hotspot analysis
"""

from __future__ import annotations

import cProfile
import gc
import pstats
import sys
import time
from io import StringIO

import numpy as np
import pyray as pr

import plyunit as pu
from plyunit.rendering import Layer

SHAPES = 1500
WARMUP_FRAMES = 60
MEASURE_FRAMES = 300


def setup_app():
    """Minimal app setup for profiling."""
    pr.init_window(1280, 720, "Profile Shapes")
    pr.set_target_fps(0)  # Uncapped

    # Import canvas and UBR
    from plyunit.backends.integrations.raylib.drawing import (
        get_batching_backend,
        get_canvas,
    )

    canvas = get_canvas()
    ubr = get_batching_backend()

    renderer = pu.Renderer(canvas=canvas, ubr=ubr, max_sprites=4096)
    renderer.init()
    return renderer


def teardown_app():
    pr.close_window()


def generate_test_data(n: int):
    """Generate test SoA buffers."""
    pos = np.random.uniform(50, 1200, (n, 2)).astype(np.float32)
    size = np.random.uniform(10, 30, (n, 2)).astype(np.float32)
    rgba = np.random.randint(50, 255, (n, 4), dtype=np.uint8)

    # Triangle vertices
    half_w = size[:, 0] * 0.5
    v1 = pos
    v2 = np.empty_like(pos)
    v3 = np.empty_like(pos)
    v2[:, 0] = pos[:, 0] - half_w
    v2[:, 1] = pos[:, 1] + size[:, 1]
    v3[:, 0] = pos[:, 0] + half_w
    v3[:, 1] = pos[:, 1] + size[:, 1]

    return {"pos": pos, "size": size, "rgba": rgba, "v1": v1, "v2": v2, "v3": v3}


def bench_gpu_only(data, renderer):
    """GPU-only: Pre-convert once, then measure raw draw throughput."""
    from plyunit.backends.integrations.raylib.drawing.canvas import to_color, to_vec2

    # Pre-convert all data once (amortized cost)
    v1_list = [to_vec2(data["v1"][i]) for i in range(SHAPES)]
    v2_list = [to_vec2(data["v2"][i]) for i in range(SHAPES)]
    v3_list = [to_vec2(data["v3"][i]) for i in range(SHAPES)]
    col_list = [to_color(data["rgba"][i]) for i in range(SHAPES)]

    gc.collect()

    # Warmup
    for _ in range(WARMUP_FRAMES):
        pr.begin_drawing()
        pr.clear_background(pr.RAYWHITE)
        for i in range(SHAPES):
            pr.draw_triangle(v1_list[i], v2_list[i], v3_list[i], col_list[i])
        pr.end_drawing()

    # Measure
    start = time.perf_counter()
    for _ in range(MEASURE_FRAMES):
        pr.begin_drawing()
        pr.clear_background(pr.RAYWHITE)
        for i in range(SHAPES):
            pr.draw_triangle(v1_list[i], v2_list[i], v3_list[i], col_list[i])
        pr.end_drawing()
    elapsed = time.perf_counter() - start

    avg_fps = MEASURE_FRAMES / elapsed
    return {
        "name": "GPU-only (pre-converted)",
        "elapsed": elapsed,
        "frames": MEASURE_FRAMES,
        "avg_fps": avg_fps,
        "ms_per_frame": (elapsed / MEASURE_FRAMES) * 1000,
    }


def bench_cpu_only(data, renderer):
    """CPU-only: Full submit pipeline without actual GPU draw."""
    from plyunit.backends.integrations.raylib.drawing.canvas import to_color, to_vec2

    gc.collect()

    # Warmup
    for _ in range(WARMUP_FRAMES):
        for i in range(SHAPES):
            to_vec2(data["v1"][i])
            to_vec2(data["v2"][i])
            to_vec2(data["v3"][i])
            to_color(data["rgba"][i])
            # Intentionally skip pr.draw_triangle

    # Measure
    start = time.perf_counter()
    for _ in range(MEASURE_FRAMES):
        for i in range(SHAPES):
            to_vec2(data["v1"][i])
            to_vec2(data["v2"][i])
            to_vec2(data["v3"][i])
            to_color(data["rgba"][i])
    elapsed = time.perf_counter() - start

    avg_fps = MEASURE_FRAMES / elapsed if elapsed > 0 else 0
    return {
        "name": "CPU-only (convert, no draw)",
        "elapsed": elapsed,
        "frames": MEASURE_FRAMES,
        "avg_fps": avg_fps,
        "ms_per_frame": (elapsed / MEASURE_FRAMES) * 1000,
    }


def bench_full_pipeline(data, renderer):
    """Full pipeline: submit -> dispatch -> convert -> draw."""
    gc.collect()

    # Warmup
    for _ in range(WARMUP_FRAMES):
        pr.begin_drawing()
        pr.clear_background(pr.RAYWHITE)
        for i in range(SHAPES):
            renderer.render_triangle(
                z=0,
                layer=Layer.ENTITIES,
                v1=data["v1"][i],
                v2=data["v2"][i],
                v3=data["v3"][i],
                color=data["rgba"][i],
            )
        renderer.flush_all()
        pr.end_drawing()

    # Measure
    start = time.perf_counter()
    for _ in range(MEASURE_FRAMES):
        pr.begin_drawing()
        pr.clear_background(pr.RAYWHITE)
        for i in range(SHAPES):
            renderer.render_triangle(
                z=0,
                layer=Layer.ENTITIES,
                v1=data["v1"][i],
                v2=data["v2"][i],
                v3=data["v3"][i],
                color=data["rgba"][i],
            )
        renderer.flush_all()
        pr.end_drawing()
    elapsed = time.perf_counter() - start

    avg_fps = MEASURE_FRAMES / elapsed
    return {
        "name": "Full pipeline (submit+render)",
        "elapsed": elapsed,
        "frames": MEASURE_FRAMES,
        "avg_fps": avg_fps,
        "ms_per_frame": (elapsed / MEASURE_FRAMES) * 1000,
    }


def run_cprofile_full(data, renderer):
    """Run cProfile on full pipeline and return top hotspots."""
    profiler = cProfile.Profile()

    profiler.enable()
    for _ in range(100):  # Shorter for profiling
        pr.begin_drawing()
        pr.clear_background(pr.RAYWHITE)
        for i in range(SHAPES):
            renderer.render_triangle(
                z=0,
                layer=Layer.ENTITIES,
                v1=data["v1"][i],
                v2=data["v2"][i],
                v3=data["v3"][i],
                color=data["rgba"][i],
            )
        renderer.flush_all()
        pr.end_drawing()
    profiler.disable()

    # Extract stats
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs()
    stats.sort_stats("cumulative")
    stats.print_stats(30)

    return stream.getvalue()


def main():
    print("=== Shapes Drawing Profiler ===")
    print(f"Shapes: {SHAPES}")
    print(f"Warmup: {WARMUP_FRAMES} frames")
    print(f"Measure: {MEASURE_FRAMES} frames")
    print()

    renderer = setup_app()
    data = generate_test_data(SHAPES)

    try:
        # 1. GPU-only (fill rate)
        print("[1/4] Running GPU-only benchmark...")
        result_gpu = bench_gpu_only(data, renderer)
        print(f"  {result_gpu['name']}")
        print(f"    FPS: {result_gpu['avg_fps']:.2f}")
        print(f"    ms/frame: {result_gpu['ms_per_frame']:.2f}")
        print()

        # 2. CPU-only (conversion overhead)
        print("[2/4] Running CPU-only benchmark...")
        result_cpu = bench_cpu_only(data, renderer)
        print(f"  {result_cpu['name']}")
        print(f"    Equiv FPS: {result_cpu['avg_fps']:.2f}")
        print(f"    ms/frame: {result_cpu['ms_per_frame']:.2f}")
        print()

        # 3. Full pipeline
        print("[3/4] Running full pipeline benchmark...")
        result_full = bench_full_pipeline(data, renderer)
        print(f"  {result_full['name']}")
        print(f"    FPS: {result_full['avg_fps']:.2f}")
        print(f"    ms/frame: {result_full['ms_per_frame']:.2f}")
        print()

        # 4. cProfile hotspots
        print("[4/4] Running cProfile analysis...")
        profile_output = run_cprofile_full(data, renderer)
        print("  Top hotspots (cumulative time):")
        print()
        for line in profile_output.split("\n")[:40]:
            if line.strip():
                print(f"    {line}")
        print()

        # Analysis
        print("=== Analysis ===")
        gpu_cost = result_gpu["ms_per_frame"]
        cpu_cost = result_cpu["ms_per_frame"]
        full_cost = result_full["ms_per_frame"]
        overhead = full_cost - gpu_cost

        print(f"GPU draw cost:     {gpu_cost:.2f} ms/frame")
        print(f"CPU convert cost:  {cpu_cost:.2f} ms/frame")
        print(f"Full pipeline:     {full_cost:.2f} ms/frame")
        print(f"Overhead:          {overhead:.2f} ms/frame")
        print()

        if overhead > cpu_cost * 1.5:
            print("Bottleneck: Renderer dispatch/submit overhead")
            print("  -> Native batch submit would help most")
        elif cpu_cost > gpu_cost:
            print("Bottleneck: CPU conversion (numpy->cffi)")
            print("  -> Native conversion or rlgl batch would help")
        else:
            print("Bottleneck: GPU fill rate")
            print("  -> CPU optimization won't help much; GPU-bound")

    finally:
        teardown_app()

    return 0


if __name__ == "__main__":
    sys.exit(main())
