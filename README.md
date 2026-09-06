# plyunit

Lightweight 2D game engine units for Python (raylib/pymunk backends).

**Not published to PyPI (yet).** Install from source: clone the repository
and run the bootstrap script.

## Install & run

Prerequisites:

- [uv](https://docs.astral.sh/uv/)
- Python **≥ 3.13**
- A C compiler for the native sprite-batching extension — MSVC Build Tools
  **or** MinGW-w64 (`gcc` on `PATH`, e.g. MSYS2)

```bash
git clone https://github.com/ahmaadn/plyunit.git
cd plyunit
./init.sh               # uv sync + build native C extension + verify
./init.sh --shapes      # ... then run an example
./verify.sh             # re-check the install at any time
```

What `init.sh` does:

1. `uv sync` — installs all workspace deps (`plyunit[all]` + dev group).
   `plyunit-native` compiles `plyunit._plyunit_batch` / `plyunit._fb_fast`
   (auto-picks MinGW gcc when MSVC is absent) and copies the built
   `.pyd`/`.so` into `packages/plyunit/src/plyunit/` so the editable install
   can import them.
2. Verifies the env via `scripts/verify_install.py` — fails loudly with fix
   hints if the C extension is missing.

Without bash (e.g. plain PowerShell), the equivalent commands:

```powershell
uv sync
uv run python scripts/verify_install.py
uv run python examples/cli.py --shapes
```

If the extension is missing after a sync (e.g. a compiler was installed
afterwards), force a rebuild:

```bash
uv sync --reinstall-package plyunit-native
```

## Create a new project

Scaffold a project inside the workspace at `projects/<name>`:

```bash
./new_project.sh my_game
uv run python projects/my_game/main.py
```

Standard structure (a virtual uv workspace member; deps `plyunit[raylib,native]`
resolved from the workspace — engine changes are picked up immediately):

```
projects/my_game/
  main.py                 # entrypoint — run with uv from repo root
  scripts/                # all Python scripts here (scenes, units, components)
  data/                   # assets
  pyproject.toml          # deps: plyunit[raylib,native] (workspace)
```

Isolated plyunit setup — embed a copy of the engine (source + built C
extension) so the project runs against its own plyunit, insulated from
workspace engine changes:

```bash
./new_project.sh my_game --isolated
```

```
projects/my_game/
  main.py                 # entrypoint — prefers scripts/plyunit at runtime
  scripts/                # all Python scripts here
  scripts/plyunit/        # isolated plyunit engine copy (+ .pyd/.so)
  data/                   # assets
  pyproject.toml
```

## Documentation

Bilingual documentation lives in `docs/` (separated per language):

- `docs/id/` — Indonesian documentation
- `docs/en/` — English documentation

Run the documentation site (MkDocs + Material, with a language switcher):

```bash
uv run --group docs mkdocs serve   # http://localhost:8000
uv run --group docs mkdocs build   # static output to site/
```

## Structure in use

- Root project: plyunit-workspace
- Workspace members: `packages/plyunit` (engine), `packages/plyunit-native`
  (C extension), `projects/*` (your games/projects)

## Initial setup

```bash
uv sync
```

(Or run `./init.sh`, which also builds and verifies the native extension —
see [Install & run](#install--run).)

Also install the dev dependency group when needed:

```bash
uv sync --group dev
```

## Dependency management at the root

Add a runtime dependency:

```bash
uv add <package-name>
```

Add a dev dependency:

```bash
uv add --group dev <package-name>
```

Remove a dependency:

```bash
uv remove <package-name>
```

Upgrade a specific dependency and update the lockfile:

```bash
uv lock --upgrade-package <package-name>
uv sync
```

## Workspace package management

Synchronize all packages in the workspace:

```bash
uv sync --all-packages
```

Synchronize a single package only:

```bash
uv sync --package plyunit
```

Note: `uv sync --package <name>` aligns the environment for the target package only. To return to full workspace mode, run `uv sync --all-packages`.

Add a dependency to a specific workspace package:

```bash
uv add --package plyunit <package-name>
```

Remove a dependency from a specific workspace package:

```bash
uv remove --package plyunit <package-name>
```

## Running tests

Root project tests:

```bash
uv run pytest
```

Tests for the plyunit package:

```bash
uv run --package plyunit pytest
```

## Examples (CLI)

`examples/` lives at the monorepo root. Run via flags:

```bash
uv run plyunit-example --list
uv run plyunit-example --shapes
uv run plyunit-example --physics
uv run python examples/cli.py --tilemap
```

## Benchmarks

`benchmarks/` is also at the monorepo root:

```bash
uv run python benchmarks/bunny_benchmark.py --help
uv run python benchmarks/bunny_benchmark.py --bunnies 5000 --target-bunnies 5000 --target-fps 60 --fps-mode capped --duration-seconds 10
```
