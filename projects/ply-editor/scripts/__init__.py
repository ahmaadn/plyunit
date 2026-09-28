"""ply_editor — the ply-editor application package.

The package is layered by responsibility; see README.md for the big
picture. Dependencies flow one way: UI -> context -> project model.

Root modules:
    constants.py      application-wide constants
    events.py         event-bus topic names
    context.py        AppContext — shared editor state hub
    dialogs.py        native file dialogs (headless-safe)
    exclude.py        folder-exclude patterns for project scanning
    global_config.py  GlobalConfig — cross-project settings
    json_io.py        safe/atomic JSON persistence helpers
    assets.py         Assets — asset index built from scan results
    project/          project state: configs, scanning, file tree
    ui/               ImGui layer, dock layout, panels
"""
