# plyunit

uv workspace monorepo for a 2D game engine (Python >=3.13; raylib/pymunk backends)
plus a native C sprite-batching extension. Windows is a first-class dev platform
(MSVC or MinGW-w64 gcc); bootstrap scripts are bash.

## Layout

- `packages/plyunit` — the engine, src layout. `plyunit/__init__.py` is a lazy
  facade (`__getattr__`): optional deps (raylib, pymunk, imgui) are not loaded
  by a plain `import plyunit`.
- `packages/plyunit-native` — builds `plyunit._plyunit_batch` / `plyunit._fb_fast`.
  Its setup.py copies the built `.pyd`/`.so` into `packages/plyunit/src/plyunit/`
  (workspace installs are editable, so they must land there; the binaries are
  gitignored).
- `projects/*` — scaffolded games (`./new_project.sh <name> [--isolated]`),
  gitignored. Run from repo root: `uv run python projects/<name>/main.py`.
- `docs/en` + `docs/id` — bilingual MkDocs (mkdocs-static-i18n). Keep both
  languages in sync when changing a page.
- `examples/`, `benchmarks/` — root-level; root pyproject exposes `examples/` as
  a package (`plyunit-example` console script).

## Native extension (critical)

- Compiles by default during `uv sync` when a compiler exists; opt out with
  `PLYUNIT_SKIP_NATIVE_BUILD=1`. On Windows, setup.py auto-picks MinGW gcc when
  MSVC is absent.
- `Renderer` fail-fasts at init without the `.pyd` — there is intentionally no
  pure-Python draw fallback. Do not add one.
- If a sync left the extension missing (e.g. a compiler was installed later):
  `uv sync --reinstall-package plyunit-native`.
- Bootstrap: `./init.sh` (sync + build + verify); re-check anytime: `./verify.sh`.

## Commands

- Tests, full suite: `uv run pytest` (headless — conftest MagicMock-mocks
  raylib/pyray, no GPU needed; ~600 tests, well under a minute).
- Single test file: `uv run pytest <path> --no-cov`. Paths inside
  `packages/plyunit` pick up that package's pytest addopts, which enforce
  `--cov-fail-under=85` — partial runs fail the gate without `--no-cov`.
- Lint: `uv run ruff check .` (ruff excludes `tests/` and
  `projects/*/scripts/plyunit/` from lint and format).
- Typecheck: `uv run pyrefly check` (pyrefly, not mypy; `bad-override` disabled
  globally; suppress with `# pyrefly: ignore [rule]`).
- Formatting: the repo is not `ruff format`-clean — format only files you touch.
- Examples: `uv run plyunit-example --list|--shapes|--physics`, or
  `uv run python examples/cli.py --tilemap`.
- Docs site: `uv run --group docs mkdocs serve` / `mkdocs build`.
- No CI exists — the commands above are the whole verification loop.

## Benchmarks / perf

- Bunny regression gates (exit non-zero below target): 8000 sprites @ >=60 FPS
  and 10000 @ >=30 FPS, e.g.
  `uv run python benchmarks/bunny_benchmark.py --bunnies 8000 --target-bunnies 8000 --target-fps 60 --fps-mode capped --duration-seconds 10`.
  SpatialIndex must stay OFF in bunny runs (they measure the flat batch path).
  Details: `docs/en/perf/regression-check.md`.
- Docs referencing a `plyunit-bunny-benchmark` console script are stale — use
  `benchmarks/bunny_benchmark.py` directly.

## Engine conventions

- Canonical hook names (see `docs/en/naming-convention.md`): `update(dt)`,
  `fixed_update(dt, step)`, `render_submit(queue)`, `draw(canvas)`. The `on_`
  prefix is only for one-time/event callbacks (`on_load`, `on_enter_tree`, ...).
  Never add synonyms such as `on_update`.
- Hexagonal architecture: engine core must not import backends; backends sit
  behind interfaces (`docs/en/architecture-*.md`).
