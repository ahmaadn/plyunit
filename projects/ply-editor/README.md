# ply-editor

A **map-editor application** built on plyunit + Dear ImGui: project
scanning, an asset index, a VS Code-style file explorer, and an IDE
dock layout. Run it from the monorepo root:

    uv run python projects/ply-editor/main.py

## Architecture

Responsibilities are split one way: **UI -> context -> project model**.

```
main.py                          entrypoint: bootstrap + font loading
app.py                           EditorApp — engine lifecycle, input, actions
ply_editor/
├── context.py                   AppContext — shared state hub + intents
├── constants.py / events.py     constants and event-bus topic names
├── global_config.py             GlobalConfig — cross-project settings
│                                (data/settings.json)
├── dialogs.py                   native open/save dialogs (headless-safe)
├── exclude.py                   scan-exclude glob parsing and merging
├── json_io.py                   safe/atomic JSON persistence helpers
├── assets.py                    Assets — asset index built from scans
├── project/
│   ├── project.py               Project — open/save a folder as a project
│   ├── configs.py               project.json / editor.json dataclasses
│   ├── scan.py                  one-pass folder scan with pruning
│   ├── scan_worker.py           background ScanJob + main-thread worker
│   └── file_tree.py             full project file tree for the explorer
└── ui/
    ├── layer.py                 ImGuiLayer — menu, toolbar, sidebars, status
    ├── layout.py                DockLayout — fixed IDE layout + splitters
    ├── panel.py                 Panel — abstract base for editor panels
    └── panels/explorer.py       ExplorerPanel — VS Code-style file tree
```

- **`EditorApp`** owns the frame pipeline, services, event wiring, and
  hotkeys (Ctrl+S saves).
- **`AppContext`** is the single state hub. Panels read state from the
  context and trigger *intents*; they never talk to each other.
- **`ImGuiLayer`** is the bridge to the engine `@ImGui` service and
  draws the whole editor chrome in one registered draw callback.

## Opening a project

`File -> Project Baru / Buka Folder...` opens any folder as a project:

1. A `.ply-editor/` scaffold is created when missing, holding
   `project.json` (project settings) and `editor.json` (UI state).
2. Exclude rules merge the global defaults with per-project overrides;
   `ALWAYS_EXCLUDED` (`.ply-editor/`, `.git`) can never be disabled.
3. A background thread scans the folder once, pruning excluded
   folders, classifying images/maps/animation configs/sidecars/fonts/
   audio.
4. The main thread picks the result up each frame: assets load into
   the index, the file tree builds from the same scan (no second disk
   traversal), and the explorer panel refreshes.

## Frame flow

```
renderer.reset_frame()
window.begin_drawing() / clear
scene_manager.render(renderer)      # game preview behind the UI
renderer.flush_all()
layer draw callback                 # menu → toolbar → sidebars →
                                    #   splitters → status bar
window.end_drawing()
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
