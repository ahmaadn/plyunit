# ply-editor

A **map-editor application** built on plyunit + Dear ImGui: project
scanning, an asset index, a VS Code-style file explorer, and an IDE
dock layout. Run it from the monorepo root:

    uv run python projects/ply-editor/main.py

## Architecture

Dependencies flow one way: **UI → app → services → state/core**. The
event bus is the dispatcher: the thin UI publishes *intent* topics, and
the application layer (`EditorApp`, not a separate `Handlers` class)
subscribes handlers that are the single place state and services are
mutated. `core/` is pure — no ImGui, no I/O.

```
main.py                          entrypoint: bootstrap + font loading
app.py                           EditorApp — composition root, frame
                                 pipeline, intent handlers
scripts/
├── constants.py                 application-wide constants
├── core/                        PURE domain (no ImGui, no I/O):
│   ├── exclude.py               folder-exclude glob rules + merging
│   ├── file_kind.py             file role classification
│   ├── file_tree.py             explorer tree model (dataclasses)
│   └── scan.py                  scan result model (dataclasses)
├── state/                       data-only dataclasses:
│   ├── workspace.py             WorkspaceState — session state
│   ├── ui.py                    UIState — ephemeral state
│   ├── settings.py              GlobalConfig — cross-project settings
│   └── project.py               project.json / editor.json dataclasses
├── services/                    world access (dialogs, scan, assets, tree):
│   ├── json_io.py               safe/atomic JSON persistence helpers
│   ├── dialogs.py               native Tk file/folder dialogs
│   ├── scan.py                  one-pass folder scan with pruning
│   ├── scan_worker.py           background ScanJob + main-thread coordinator
│   ├── file_tree.py             FileTree service for the explorer
│   └── assets.py                Assets — asset index built from scans
├── app/                         application layer:
│   ├── context.py               Context — shared state hub (state only)
│   ├── events.py                event-bus intent topic names
│   └── keymap.py                shortcut → bus intent
└── ui/                          ALL ImGui code:
    ├── shell.py                 EditorShell — facade over the ImGui service
    ├── layout.py                DockLayout — fixed IDE layout + splitters
    ├── panel.py                 Panel — base class, auto-attached (ctx, bus)
    ├── menus.py                 MainMenuBar
    ├── panels/                  ExplorerPanel, StatusBar, Toolbar
    └── screens/                 StartScreen, EditorScreen
```

- **`EditorApp`** is the composition root: `on_load` builds state →
  engine pieces → services → UI layer, in that order, and each object
  is fully usable the moment it is constructed (no `setup()` phases, no
  first-frame flags). It subscribes the event-bus intents itself — the
  handlers live on the app, so there is no separate `Handlers` class —
  and is the only place state and services are mutated.
- **`Context`** is state only — no services, no service locator. It
  owns the config dataclasses (`global_`, `project`, `editor`), the
  session state (`workspace` session state, `ui` ephemeral state), and
  the project flags (`project_root`, `project_active`), and is handed
  explicitly to panels. Each mutable flag has exactly one owner:
  `workspace.scanning` is raised and lowered by `ScanWorker` alone (on
  every terminal path — done, failed, cancelled).
- **Panels** are thin views. `Panel.__new__` auto-attaches the shared
  `@EventBus` and `@Context` units from the engine registry; panels read
  shared state and publish intents, and never reach into other panels.
  User actions are published as intents on the event bus, and the
  subscribed app handlers respond.
- **`EditorShell`** is the bridge to the engine `@ImGui` service and
  draws the whole editor chrome in one registered draw callback; it
  builds the start screen and the editor screen in its attach hook.
- The explorer holds **no tree copy**: it reads the `FileTree` service
  (the single source of truth, rebuilt by the background scan) every
  frame, the immediate-mode way.

## Opening a project

`File -> Project Baru / Buka Folder...` opens any folder as a project:

1. The folder is validated (it must exist, be a folder, and be
   readable), then a `.ply-editor/` scaffold is created when missing,
   holding `project.json` (project settings) and `editor.json` (UI
   state).
2. Exclude rules merge the global defaults with per-project overrides;
   `ALWAYS_EXCLUDED` (`.ply-editor/`, `.git`) can never be disabled.
3. A background thread scans the folder once, pruning excluded
   folders, classifying images/maps/animation configs/sidecars/fonts/
   audio.
4. The main thread picks the result up each frame: assets load into
   the index, the file tree is rebuilt from the same scan (no second
   disk traversal), and the explorer panel reads the tree straight
   from the service — no UI object is touched by the worker.
5. The project is recorded as the most recently used entry, so the
   next launch reopens it (`open_last_project`). On shutdown
   (`on_unload`) the background scan is cancelled, the global config
   is saved, and the open project's configs are persisted.

## Frame flow

```
renderer.reset_frame()
window.begin_drawing() / clear
scan_worker.poll()                  # apply finished background scans
poll_shortcuts()                    # Ctrl+S -> bus intent
shell.update(dt)                    # editor chrome logic
scene_manager.render(renderer)      # game preview behind the UI
renderer.flush_all()
ui.frame(dt)                        # runs the shell's draw callback:
                                    #   menu → toolbar → sidebars →
                                    #   splitters → status bar
window.end_drawing()
mouse.update(dt) / input.update(dt)
```

## Files on disk

- `data/settings.json` — global editor settings: recent projects,
  window geometry, global scan excludes. Written atomically; a corrupt
  file falls back to defaults (the old file is kept as `.bak`).
- `<project>/.ply-editor/project.json` — per-project settings,
  including map defaults and per-project exclude patterns.
- `<project>/.ply-editor/editor.json` — per-project editor UI state
  (camera, grid toggles, panels, sidebar widths). Unknown keys are
  preserved across rewrites.

Docs: `docs/en/imgui.md`; tutorial: `TUTORIAL_IMGUI.md`.
