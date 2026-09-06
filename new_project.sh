#!/usr/bin/env bash
# Scaffold a new project inside the workspace at projects/<name>.
#
# Usage:
#   ./new_project.sh <name>              # standard: plyunit from the workspace
#   ./new_project.sh <name> --isolated   # isolated plyunit setup
#
# Standard structure (virtual uv workspace member):
#   projects/<name>/pyproject.toml   # deps: plyunit[raylib,native] (workspace)
#   projects/<name>/main.py          # entrypoint — run with uv from repo root
#   projects/<name>/scripts/         # all Python scripts here
#   projects/<name>/data/            # assets
#
# Isolated plyunit setup (--isolated, adds):
#   projects/<name>/scripts/plyunit/*          # isolated plyunit scripts
#                                             # (engine source copy + built
#                                             # C extension); main.py prefers
#                                             # this copy over the workspace
#                                             # install at runtime
#
# Run the project from the monorepo root:
#   uv run python projects/<name>/main.py
set -euo pipefail
cd "$(dirname "$0")"

usage() {
    cat <<'EOF'
Usage: ./new_project.sh <name> [--isolated]

Creates a plyunit project scaffold at projects/<name>.
  --isolated  embed a plyunit engine copy at scripts/plyunit/
EOF
}

PROJECT_NAME=""
ISOLATED=0
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
            ;;
        --isolated)
            ISOLATED=1
            ;;
        -*)
            echo "error: unknown option '$arg'" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [ -n "$PROJECT_NAME" ]; then
                echo "error: unexpected argument '$arg'" >&2
                usage >&2
                exit 2
            fi
            PROJECT_NAME="$arg"
            ;;
    esac
done

if [ -z "$PROJECT_NAME" ]; then
    usage >&2
    exit 2
fi

if ! [[ "$PROJECT_NAME" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]]; then
    echo "error: invalid project name '$PROJECT_NAME'." >&2
    echo "Use letters, digits, '-' and '_'; must start with a letter." >&2
    exit 2
fi

PROJECT_DIR="projects/$PROJECT_NAME"
if [ -e "$PROJECT_DIR" ]; then
    echo "error: $PROJECT_DIR already exists." >&2
    exit 1
fi

# PEP 508 project name (lowercase).
PKG_NAME="$(echo "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]')"

mkdir -p "$PROJECT_DIR/scripts" "$PROJECT_DIR/data"

cat > "$PROJECT_DIR/pyproject.toml" <<EOF
[project]
name = "$PKG_NAME"
version = "0.1.0"
description = "$PROJECT_NAME - a plyunit project"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "plyunit[raylib,native]",
]

# The project itself is plain source code (run via \`uv run python\`), never
# built or installed as a package.
[tool.uv]
package = false

[tool.uv.sources]
plyunit = { workspace = true }
EOF

if [ "$ISOLATED" -eq 1 ]; then
    cat > "$PROJECT_DIR/main.py" <<EOF
"""$PROJECT_NAME - entrypoint (isolated plyunit setup).

Run from the monorepo root:

    uv run python projects/$PROJECT_NAME/main.py
"""

import sys
from pathlib import Path

# Prefer this project's engine copy at scripts/plyunit over the workspace
# editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

import plyunit as pu
from scripts.main_scene import MainScene


class GameApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        # Simulation: drive the scene tree every fixed substep.
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        # Per-frame render pipeline (fully user-owned).
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        GameApp(),
        pu.AppConfig(
            title="$PROJECT_NAME",
            window_width=1280,
            window_height=720,
            target_fps=60,
            fixed_update_hz=60,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
EOF
else
    cat > "$PROJECT_DIR/main.py" <<EOF
"""$PROJECT_NAME - entrypoint.

Run from the monorepo root:

    uv run python projects/$PROJECT_NAME/main.py
"""

import plyunit as pu
from scripts.main_scene import MainScene


class GameApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        # Simulation: drive the scene tree every fixed substep.
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        # Per-frame render pipeline (fully user-owned).
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        GameApp(),
        pu.AppConfig(
            title="$PROJECT_NAME",
            window_width=1280,
            window_height=720,
            target_fps=60,
            fixed_update_hz=60,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
EOF
fi

cat > "$PROJECT_DIR/scripts/main_scene.py" <<EOF
"""Main scene for $PROJECT_NAME."""

import plyunit as pu
from scripts.player import Player


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__(name="Main")

    def on_load(self) -> None:
        hero = Player()
        hero.transform.set_position(100.0, 100.0)
        self.root.attach(hero)

    def update(self, dt: float) -> None:
        _ = dt  # scene-level logic (optional)
EOF

cat > "$PROJECT_DIR/scripts/player.py" <<EOF
"""Player unit skeleton for $PROJECT_NAME."""

import plyunit as pu


class Player(pu.NodeUnit):
    """Attach to a scene: scene.root.attach(Player()) in on_load."""

    def __init__(self, name: str = "Player") -> None:
        super().__init__(name=name)
EOF

touch "$PROJECT_DIR/scripts/__init__.py" "$PROJECT_DIR/data/.gitkeep"

if [ "$ISOLATED" -eq 1 ]; then
    ENGINE_SRC="packages/plyunit/src/plyunit"
    if [ ! -d "$ENGINE_SRC" ]; then
        echo "error: engine source not found at $ENGINE_SRC." >&2
        echo "  Run ./init.sh first, then re-run ./new_project.sh $PROJECT_NAME --isolated" >&2
        rm -rf "$PROJECT_DIR"
        exit 1
    fi
    echo "==> Copying isolated plyunit engine -> $PROJECT_DIR/scripts/plyunit"
    cp -r "$ENGINE_SRC" "$PROJECT_DIR/scripts/plyunit"
    find "$PROJECT_DIR/scripts/plyunit" -name "__pycache__" -type d -exec rm -rf {} +
    find "$PROJECT_DIR/scripts/plyunit" -name "*.pyc" -delete
    EXT_COUNT="$(find "$PROJECT_DIR/scripts/plyunit" -maxdepth 1 \( -name '*.pyd' -o -name '*.so' \) | wc -l)"
    if [ "$EXT_COUNT" -eq 0 ]; then
        echo "WARNING: no built C extension (.pyd/.so) in the engine copy." >&2
        echo "  Run ./init.sh (or uv sync --reinstall-package plyunit-native) and" >&2
        echo "  re-scaffold; without it the project fails at Renderer init." >&2
    fi
fi

if [ "$ISOLATED" -eq 1 ]; then
    cat > "$PROJECT_DIR/README.md" <<EOF
# $PROJECT_NAME

A plyunit project (isolated plyunit setup: scripts/plyunit/ holds an engine
copy; main.py prefers it over the workspace install). Run from the monorepo
root:

    uv run python projects/$PROJECT_NAME/main.py

Layout: \`main.py\` (entrypoint) - \`scripts/\` (all Python scripts) -
\`scripts/plyunit/\` (isolated engine) - \`data/\` (assets).

Docs: \`docs/en/getting-started.md\`.
EOF
else
    cat > "$PROJECT_DIR/README.md" <<EOF
# $PROJECT_NAME

A plyunit project. Run from the monorepo root:

    uv run python projects/$PROJECT_NAME/main.py

Layout: \`main.py\` (entrypoint) - \`scripts/\` (all Python scripts) -
\`data/\` (assets).

Docs: \`docs/en/getting-started.md\`.
EOF
fi

SUFFIX=""
if [ "$ISOLATED" -eq 1 ]; then
    SUFFIX=" (isolated plyunit setup)"
fi

echo "Created $PROJECT_DIR$SUFFIX"
echo ""
echo "Run it from the monorepo root:"
echo "  uv run python $PROJECT_DIR/main.py"
