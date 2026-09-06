"""Example: optional ImGui UI (immediate-mode only).

Requires the **imgui** extra: ``uv sync --package plyunit --extra raylib
--extra imgui`` in the monorepo workspace.

Controls:
- ImGui demo window (built-in)
- Custom panel with FPS + counter
"""

from __future__ import annotations

from imgui_bundle import imgui

import plyunit as pu


class ImGuiApp(pu.App):
    def on_load(self) -> None:
        self._counter = 0
        imgui_service = self.one("@ImGui", scope="global")
        imgui_service.add_draw(self._draw_ui)

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)

        # Queued world content (ImGui is separate, immediate, post-pass).
        self.renderer.render_rect(
            z=0,
            layer=pu.Layer.WORLD,
            rect=(80, 80, 160, 100),
            color=(70, 110, 180, 255),
        )

        self.renderer.flush_all()

        # ImGui draws on top of the game, still inside the drawing block.
        imgui_service = self.one_or_none("@ImGui", scope="global")
        if imgui_service is not None:
            imgui_service.frame(dt)

        self.window.end_drawing()

    def _draw_ui(self) -> None:
        imgui.begin("Plyunit ImGui")
        imgui.text("Immediate-mode UI (no scene traversal)")
        imgui.text(f"FPS: {imgui.get_io().framerate:.1f}")
        if imgui.button("Increment"):
            self._counter += 1
        imgui.same_line()
        imgui.text(f"count = {self._counter}")
        imgui.end()
        imgui.show_demo_window()


def main() -> None:
    app = pu.init(
        ImGuiApp(),
        pu.AppConfig(
            title="ImGui Example",
            window_width=960,
            window_height=600,
            background_color=(20, 22, 30, 255),
            imgui=pu.ImGuiConfig(enabled=True),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
