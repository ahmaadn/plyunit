"""ply-editor entrypoint.

Run from the monorepo root:

    uv run python projects/ply-editor/main.py
"""

from __future__ import annotations

from app import EditorApp
from imgui_bundle import hello_imgui, imgui

import plyunit
from scripts import constants as const
from scripts.assets import Assets


def load_font() -> imgui.ImFont:
    """Load Roboto as the main font, merging Font Awesome into it."""
    return hello_imgui.load_font_ttf_with_font_awesome_icons(
        str(const.FONT_PATH),
        const.FONT_SIZE,
    )


def main() -> None:
    """Bootstrap and run the editor."""
    app = plyunit.init(
        EditorApp(),
        plyunit.AppConfig(
            title=const.APP_NAME,
            window_width=const.WINDOW_WIDTH,
            window_height=const.WINDOW_HEIGHT,
            target_fps=const.FPS,
            fixed_update_hz=60,
            imgui=plyunit.ImGuiConfig(
                enabled=True,
                dark_style=True,
                no_ini=True,
            ),
        ),
        asset=Assets,
    )
    app.default_font = load_font()
    app.run()


if __name__ == "__main__":
    main()
