"""CLI launcher for plyunit examples.

Usage (from monorepo root):

    uv run python examples/cli.py --list
    uv run python examples/cli.py --shapes
    uv run python examples/cli.py --example shapes
    uv run plyunit-example --physics
"""

from __future__ import annotations

import argparse
import importlib
import runpy
import sys
from pathlib import Path

# Ensure monorepo root is on sys.path when invoked as a script path.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# flag_name -> import target (module:attr or module path for runpy packages)
# flag is the short CLI name used as --<flag>
EXAMPLES: dict[str, str] = {
    "shapes": "examples.example_shapes:main",
    "ysort": "examples.example_ysort:main",
    "blend-modes": "examples.example_blend_modes:main",
    "shader": "examples.example_shader:main",
    "scissor": "examples.test_scissor:main",
    "scissor-camera": "examples.example_scissor_camera:main",
    "render-target": "examples.example_render_target:main",
    "stencil": "examples.example_stencil:main",
    "streaming-texture": "examples.example_streaming_texture:main",
    "text-font": "examples.test_text_font.main:main",
    "particles": "examples.example_particles:main",
    "input": "examples.input_service:main",
    "event-bus-input": "examples.example_event_bus_input:main",
    "gamepad": "examples.example_gamepad:main",
    "imgui": "examples.example_imgui:main",
    "physics": "examples.example_physics:main",
    "assets": "examples.test_assets:main",
    "texture-atlas": "examples.example_texture_atlas:main",
    "transition-scene": "examples.transition_scene:main",
    "tween": "examples.example_tween:main",
}


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").removeprefix("example-")


def _resolve_target(name: str) -> str:
    key = _normalize_name(name)
    if key not in EXAMPLES:
        known = ", ".join(sorted(EXAMPLES))
        raise SystemExit(f"Unknown example {name!r}. Known: {known}")
    return EXAMPLES[key]


def _run_target(target: str) -> None:
    if ":" in target:
        module_name, attr = target.split(":", 1)
        module = importlib.import_module(module_name)
        fn = getattr(module, attr, None)
        if not callable(fn):
            raise SystemExit(f"{target} is not callable")
        fn()
        return

    # Module without main — execute as __main__
    runpy.run_module(target, run_name="__main__")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plyunit-example",
        description="Run plyunit examples from the monorepo root.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available example flags",
    )
    parser.add_argument(
        "--example",
        metavar="NAME",
        help="Example short name (e.g. shapes, physics, tilemap)",
    )
    for flag in sorted(EXAMPLES):
        parser.add_argument(
            f"--{flag}",
            dest="flag_example",
            action="store_const",
            const=flag,
            help=f"Run example '{flag}'",
        )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        width = max(len(k) for k in EXAMPLES)
        for name in sorted(EXAMPLES):
            print(f"  --{name:<{width}}  ->  {EXAMPLES[name]}")
        return

    chosen = args.example or args.flag_example
    if not chosen:
        parser.print_help()
        raise SystemExit(2)

    target = _resolve_target(chosen)
    _run_target(target)


if __name__ == "__main__":
    main()
