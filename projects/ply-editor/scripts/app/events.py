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

# Unlike the intents above, this topic expects the project path as a
# payload parameter (``path=<str>``).
APP_OPEN_PROJECT_BY_PATH: Final = "app.open_project_by_path"
