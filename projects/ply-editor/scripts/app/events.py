"""Event-bus intent topic names for the editor.

The thin UI publishes these topics on the event bus; the application
layer (`EditorApp`) subscribes handlers that perform the action. Each
name is a plain string constant that doubles as the bus topic.
"""

from typing import Final

APP_NEW_MAP: Final = "app.new_map"
APP_OPEN_MAP: Final = "app.open_map"
APP_SAVE: Final = "app.save"
APP_SAVE_AS: Final = "app.save_as"
APP_OPEN_FOLDER_PROJECT: Final = "app.open_folder_project"
APP_REFRESH_ASSETS: Final = "app.refresh.assets"
APP_CLOSE_PROJECT: Final = "app.close_project"

# payload parameter (``path=<str>``).
APP_OPEN_PROJECT_BY_PATH: Final = "app.open_project_by_path"
"""Open a project by an absolute folder path."""

# payload parameter (``id=<int>``, ``rect=<tuple[int, int, int, int]>``).
REGION_PICKED = "image_canvas.region_picked"
"""A region was picked on the image canvas."""

# payload parameter (``path=<str | Path>``).
MAP_OPEN_REQUESTED = "map.open_requested"
"""Request to open a map document."""

# payload parameter (``asset_id=<str>``).
ASSET_OPEN_REQUESTED = "asset.open_requested"
"""Request to open an asset document."""

# payload parameter (``asset_id=<list[ActionTab]>``).
TAB_ACTION_REQUEST = "tab_bar.action_requested"
"""A tab-bar action was requested."""
