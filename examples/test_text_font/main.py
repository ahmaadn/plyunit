"""Configure fonts, select text templates, and reuse shaped text.

Demonstrates the unified ``Text`` service: load fonts, define styles, measure
text, draw immediately, and submit cached glyph quads to the renderer.
"""

import os

import plyunit as pu
from plyunit.backends.ports.renderer import ICanvas2D
from plyunit.backends.ports.text import IText, ShapedText


class TextShowcase(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="TextShowcase")

    def on_ready(self):
        self.text: IText = self.one("@Text")

        # Resolve font paths relative to this example, not the working directory.
        font_dir = os.path.join(os.path.dirname(__file__), "assets", "IBM_Plex_Mono")
        regular_font = os.path.join(font_dir, "IBMPlexMono-Regular.ttf")
        bold_font = os.path.join(font_dir, "IBMPlexMono-Bold.ttf")
        italic_font = os.path.join(font_dir, "IBMPlexMono-Italic.ttf")

        self.text.load_font("ibm_regular", regular_font)
        self.text.load_font("ibm_bold", bold_font)
        self.text.load_font("ibm_italic", italic_font)

        self.text.load_templates({
            "title": {"font": "ibm_bold", "spacing": 2, "size": 32},
            "body": {"font": "ibm_regular", "spacing": 1, "size": 20},
        })
        self.text.set_template("caption", "ibm_italic", spacing=0, size=14)
        # Keep the font loaded while its borrowed atlas is used by this shape.
        self._queued_text: ShapedText = self.text["title"].shape("Queued glyphs (Z=0)")
        self._font = self.text.get_font("ibm_bold")

    def draw(self, canvas: ICanvas2D) -> None:
        # Template selection is shared service state; select it for each call.
        self.text["title"].draw(
            "Plyunit Text & Font Showcase",
            pos=(20, 20),
            color=(255, 203, 0, 255),
        )

        self.text["body"].draw(
            "This example demonstrates how to configure and use custom fonts.",
            pos=(20, 80),
            color=(245, 245, 245, 255),
        )

        self.text["body"].draw(
            "IBM Plex Mono - Regular Font",
            pos=(20, 120),
            color=(200, 200, 200, 255),
        )

        self.text["caption"].draw(
            "The caption template uses the italic font.",
            pos=(20, 160),
            color=(130, 130, 130, 255),
        )

        # measure() returns layout width and height in pixels.
        test_str = "Measurement test string"
        width, height = self.text["body"].measure(test_str)
        self.text["body"].draw(
            f"{test_str} (Width: {width}px, Height: {height}px)",
            pos=(20, 220),
            color=(102, 191, 255, 255),
        )

        # Outline the measured text bounds.
        canvas.draw_rectangle(
            rect=(20, 220, width, height),
            color=(0, 0, 0, 0),
            border_color=(102, 191, 255, 255),
            thickness=1.0,
        )

        self.text["caption"].draw(
            f"Font: {self._font.base_size}px | Glyphs: {self._font.glyph_count}",
            pos=(20, 270),
            color=(200, 200, 200, 255),
        )

    def render_submit(self, renderer: pu.Renderer, context=None) -> None:
        super().render_submit(renderer, context)
        # Queue before flushing; never append glyphs from a draw callback.
        renderer.render_shaped_text(
            self._queued_text,
            pos=(20, 320),
            color=(255, 161, 0, 255),
            z=0,
            layer=pu.Layer.UI,
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main")

    def on_load(self) -> None:
        self.root.attach(TextShowcase())


class TextApp(pu.App):
    def on_load(self) -> None:
        self.text_service = pu.Text(renderer=self.renderer)
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((30, 30, 40, 255))
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        TextApp(),
        pu.AppConfig(
            title="Text Font Showcase",
            window_width=720,
            window_height=420,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
