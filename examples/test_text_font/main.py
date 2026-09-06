"""Example: Text & Font Configuration

Demonstrasi penggunaan modul Text dan Font pada Plyunit:
- Load font dari path
- Konfigurasi template (font, size, spacing)
- Menggambar menggunakan dictionary-like template selection
- Mengukur ukuran text
- Submit text ke Renderer
"""

import os

import pyray as pr

import plyunit as pu
from plyunit.assets.text import Text


class TextShowcase(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="TextShowcase")

    def on_ready(self):
        # Mengambil instance dari Text Service yang telah ditambahkan ke scene
        self.text: Text = self.one("@Text")

        # Path absolut agar script bisa dieksekusi dari direktori mana saja
        font_dir = os.path.join(os.path.dirname(__file__), "assets", "IBM_Plex_Mono")
        regular_font = os.path.join(font_dir, "IBMPlexMono-Regular.ttf")
        bold_font = os.path.join(font_dir, "IBMPlexMono-Bold.ttf")
        italic_font = os.path.join(font_dir, "IBMPlexMono-Italic.ttf")

        # 1. Load Fonts
        # Memberikan penamaan pada setiap font yang dimuat
        self.text.font.load_font("ibm_regular", regular_font)
        self.text.font.load_font("ibm_bold", bold_font)
        self.text.font.load_font("ibm_italic", italic_font)

        # 2. Setup Templates
        # Template menyimpan kombinasi dari font, spacing, dan font_size
        self.text.font.set_template("title", "ibm_bold", spacing=2, size=32)
        self.text.font.set_template("body", "ibm_regular", spacing=1, size=20)
        self.text.font.set_template("caption", "ibm_italic", spacing=0, size=14)

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:

        # 3. Menggambar teks menggunakan draw()
        # Menggunakan syntax array/dict-like untuk memilih template
        self.text["title"].draw(
            "Plyunit Text & Font Showcase",
            pos=(20, 20),
            # pyrefly: ignore [bad-argument-type]
            color=pr.GOLD,
        )

        self.text["body"].draw(
            "This example demonstrates how to configure and use custom fonts.",
            pos=(20, 80),
            # pyrefly: ignore [bad-argument-type]
            color=pr.RAYWHITE,
        )

        self.text["body"].draw(
            "IBM Plex Mono - Regular Font",
            pos=(20, 120),
            # pyrefly: ignore [bad-argument-type]
            color=pr.LIGHTGRAY,
        )

        self.text["caption"].draw(
            "Ini adalah contoh penggunaan template 'caption' dengan font Italic.",
            pos=(20, 160),
            # pyrefly: ignore [bad-argument-type]
            color=pr.GRAY,
        )

        # 4. Mengukur teks
        # method measure() mengembalikan (width, height)
        test_str = "Measurement test string"
        width, height = self.text["body"].measure(test_str)
        self.text["body"].draw(
            f"{test_str} (Lebar: {width}px, Tinggi: {height}px)",
            pos=(20, 220),
            # pyrefly: ignore [bad-argument-type]
            color=pr.SKYBLUE,
        )

        # Kotak pembatas untuk memvisualisasikan hasil measure
        canvas.draw_rectangle(
            rect=(20, 220, width, height),
            color=(0, 0, 0, 0),
            border_color=pr.SKYBLUE,
            thickness=1.0,
        )

        # 5. Submit ke Renderer
        # push() berguna jika kita ingin mengatur Z-index atau Layer rendering
        self.text["title"].draw(
            "Pushed to Render Queue (Z=0)",
            pos=(20, 320),
            # pyrefly: ignore [bad-argument-type]
            color=pr.ORANGE,
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main")

    def on_load(self) -> None:
        # Menambahkan showcase
        self.root.attach(TextShowcase())


class TextApp(pu.App):
    def on_load(self) -> None:
        self.text_service = Text()
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
