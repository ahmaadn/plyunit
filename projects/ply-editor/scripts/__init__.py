"""ply_editor — the ply-editor application package.

Layered by responsibility, dependencies flow one way:
UI -> app -> services -> state/core (see README.md):

    constants.py      application-wide constants
    core/             PURE domain: exclude rules, file kinds, tree
                      model, scan result (no ImGui, no I/O)
    state/            data-only dataclasses: workspace, ui, settings,
                      per-project configs
    services/         world access: dialogs, scanning, file tree,
                      assets
    app/              Context, event-bus intents, keymap
    ui/               ALL ImGui code: shell, layout, panels, screens
"""
