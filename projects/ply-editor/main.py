"""ply-editor entrypoint.

Run from the monorepo root:

    uv run python projects/ply-editor/main.py
"""

from __future__ import annotations

from app import EditorApp
from imgui_bundle import hello_imgui, imgui

import plyunit
from scripts import constants as const
from scripts.services.assets import Assets


def load_font() -> imgui.ImFont:
    """Load Roboto as the main font, then merge Font Awesome with fixed-width glyphs."""
    # 1) Font utama, tanpa merge
    main_font = hello_imgui.load_font(
        str(const.FONT_PATH), const.FONT_SIZE, hello_imgui.FontLoadingParams()
    )

    # 2) Icon, digabung ke font terakhir dengan config sendiri
    icon_cfg = imgui.ImFontConfig()
    icon_cfg.glyph_min_advance_x = const.FONT_SIZE * 1.25

    icon_params = hello_imgui.FontLoadingParams(
        merge_to_last_font=True,
        inside_assets=True,
        font_config=icon_cfg,
    )

    hello_imgui.load_font(str(const.FONT_ICON_PATH), const.FONT_SIZE, icon_params)

    return main_font


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
