"""Example: stencil buffer masking (circle clip + inverse hole).

Controls:
- Space: toggle inverse mask
"""

from __future__ import annotations

import time

import pyray as pr

import plyunit as pu


class StencilApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.input.map("toggle_inverse", pr.KeyboardKey.KEY_SPACE)
        self._t0 = time.perf_counter()
        self._inverse = False
        self.draw = self.renderer.draw
        # Ensure GL stencil entry points are loaded after the window exists.
        self.canvas.init_stencil()

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        if self.input.is_pressed("toggle_inverse"):
            self._inverse = not self._inverse
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)

        # Immediate DrawScope drawing — valid inside the drawing block.
        self._draw_content()

        self.renderer.flush_all()
        self.window.end_drawing()

    def _draw_content(self) -> None:
        draw = self.draw
        t = time.perf_counter() - self._t0
        cx = 400.0 + 40.0 * (t % 4.0 - 2.0)
        cy = 240.0
        radius = 90.0

        # Background (unmasked)
        draw.rect((0, 0, 800, 480), (18, 20, 32, 255))

        with draw.stencil(inverse=self._inverse) as st:
            with st.mask():
                # Invisible mask geometry — only stamps the stencil buffer.
                draw.circle(cx, cy, radius, (255, 255, 255, 255))
            # Content is clipped to (or outside) the circle.
            draw.rect((40, 40, 720, 400), (70, 130, 220, 255))
            draw.rect((120, 100, 200, 140), (220, 90, 70, 255))
            draw.circle(500, 280, 60, (90, 200, 120, 255))

        mode = "INVERSE (outside)" if self._inverse else "NORMAL (inside)"
        draw.canvas.draw_text(
            text=f"Stencil demo [{mode}]  Space=toggle",
            pos=(12, 12),
            font_size=18,
            color=(230, 235, 255, 255),
        )


def main() -> None:
    app = pu.init(
        StencilApp(),
        pu.AppConfig(
            title="Stencil Mask Example",
            window_width=800,
            window_height=480,
            background_color=pr.Color(12, 14, 24, 255),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
