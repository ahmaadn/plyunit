"""State: data-only dataclasses, no heavy logic and no I/O.

State is split by lifetime and owner (see the architecture guide):

    workspace.py  WorkspaceState — session state (what is open)
    ui.py         UIState — ephemeral UI state (status message)
    settings.py   GlobalConfig — persisted cross-project settings
    project.py    per-project config dataclasses (project.json,
                  editor.json, map defaults)

Persistence is owned by ``scripts.app.context.Context``; these modules
only carry data and serialize via ``to_dict``/``from_dict``.
"""
