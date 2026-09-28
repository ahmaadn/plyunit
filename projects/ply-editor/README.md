# simple-editor

An **editor application base** on plyunit + Dear ImGui: dock layout,
element system, state hub, undo/redo, settings persistence and hotkeys —
without any domain features. Build your editor on top by filling in the
marked seams.

    uv run python projects/simple-editor/main.py

## Architecture

Three objects split responsibilities. Dependencies flow one way:
**UI → Context → your model**.

```
EditorApp (main.py)          engine lifecycle: window, scenes, render pipeline
├── AppContext (context.py)  STATE   — settings, history, viewport, layout,
│                                       status + your intents
├── ImGuiLayer (layer.py)    BRIDGE  — engine @ImGui service: frame(dt),
│                                       draw callbacks, input-capture gates
└── EditorShell (shell.py)   UI      — dock layout, elements, hotkeys
```

- **`AppContext`** is the single state hub. Elements never talk to each
  other; they read state from the context and trigger *intents*
  (`undo`, `set_status`, plus whatever you add) so the menu bar,
  toolbar, hotkeys and tools share one code path.
- **`ImGuiLayer`** is deliberately thin — it resolves the `@ImGui`
  service, forwards draw callbacks, and exposes `frame(dt)` plus
  `want_capture_mouse()/want_capture_keyboard()`. It knows nothing about
  panels.
- **`EditorShell`** owns the dock layout, the element tree and global
  hotkeys, and registers exactly one draw callback with the layer.

## File map

```
scripts/
├── context.py     AppContext — shared state + intents        [extend me]
├── shell.py       EditorShell — layout, elements, hotkeys    [extend me]
├── layer.py       ImGuiLayer — engine ImGui service bridge
├── panel.py       Element — base class (docked / floating)
├── layout.py      DockLayout — IDE layout, splitters, viewport rect
├── viewport.py    Viewport — pan/zoom camera math
├── commands.py    CommandStack + CallableCommand — undo/redo
├── settings.py    EditorSettings — .ryeditor/editor.json
├── dialogs.py     native open/save dialogs (headless-safe)
├── panels/
│   ├── main_menu_bar.py     File / Edit / View / Help        [extend me]
│   ├── toolbar.py           example action row               [extend me]
│   ├── status_bar.py        status message + FPS
│   ├── placeholder_panel.py copy this to write a docked panel
│   ├── viewport_panel.py    transparent center + camera demo
│   ├── stats_panel.py       floating: engine metrics + pause
│   └── demo_panel.py        floating: Dear ImGui demo window
├── main_scene.py  preview scene rendered behind the UI
└── player.py      example unit
```

## Frame flow

```
renderer.reset_frame()
window.begin_drawing() / clear
scene_manager.render(renderer)      # game preview behind the UI
renderer.flush_all()
layer.frame(dt)                     # shell draws:
                                    #   menu → toolbar → status → sidebars
                                    #   → splitter → viewport → debug windows
window.end_drawing()
```

The viewport window is **fully transparent**, so the raylib render behind
it stays visible; grid, gizmos and world content you draw with the ImGui
draw list appear in the same frame as the input that changed them.

## Extending

**Add a panel** — copy `panels/placeholder_panel.py`, implement `draw()`
with content only (the shell wraps it in `begin`/`end` at its dock rect),
then instantiate it in `EditorShell.__init__` and call
`draw_window(rect)` in `draw()`. Floating panels manage their own window
(`floating=True`) and are drawn while `visible` — wire toggles into the
View → Debug menu automatically.

**Add state and intents** — put fields on `AppContext` (document,
selection, active tool, …) and methods for every mutation; route menu,
toolbar and hotkey handlers through those methods.

**Add hotkeys** — extend `EditorShell._handle_hotkeys()` (skips while a
text field has focus).

**Add undoable actions** — implement the `Command` protocol (`apply` /
`revert` / `label`) and `context.history.push(cmd)`. The Edit menu and
Ctrl+Z / Ctrl+Y pick it up automatically.

**Add file IO** — `dialogs.open_file()/save_file()` return a path or
`None` (no tkinter / cancelled), safe to call from menus.

## Controls

| Input | Action |
| --- | --- |
| Middle drag | Pan the viewport camera |
| Wheel | Zoom around the cursor |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo (Edit menu) |

## Files on disk

- `.ryeditor/editor.json` — sidebar widths, right-sidebar split,
  visibility toggles. Written on exit, loaded on start; unknown keys are
  ignored so adding settings fields is safe.

Docs: `docs/en/imgui.md`; tutorial: `TUTORIAL_IMGUI.md` (§21 covers this
architecture).
