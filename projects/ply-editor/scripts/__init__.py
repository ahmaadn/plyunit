"""simple-editor — editor application base on plyunit + Dear ImGui.

The package is layered; see README.md for the full picture.

State (no ImGui):
    commands.py     CommandStack — undo/redo infrastructure
    settings.py     EditorSettings — .ryeditor/editor.json
    viewport.py     Viewport — pan/zoom camera math
    dialogs.py      native file dialogs (headless-safe)

UI:
    context.py      AppContext — shared state hub + intents
    shell.py        EditorShell — dock layout, elements, hotkeys
    layer.py        ImGuiLayer — bridge to the engine @ImGui service
    panel.py        Element — base class for UI elements
    layout.py       DockLayout — fixed IDE-style layout + splitters
    panels/         menu bar, toolbar, status bar, placeholders, viewport,
                    floating debug panels (stats, ImGui demo)

Preview scene (behind the UI):
    main_scene.py   scene pushed by the app
    player.py       example unit
"""
