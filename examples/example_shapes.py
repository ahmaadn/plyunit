"""Example: Advanced Shapes Rendering

Demonstrasi penggunaan semua fitur render shape lanjutan pada Canvas di Plyunit:
- Rectangle (Rotasi, gradien, specific rounded corners, outline + fill)
- Circle (Sector angles, rotasi, outline + fill, gradient)
- Triangle (3-point gradient, outline, rotasi, pivot/origin)
- Line (Thick, bezier, rotasi)
- Polygon (Rotasi, thickness)
"""

import math

import pyray as pr

import plyunit as pu


class ShapeShowcase(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="ShapeShowcase")
        self.time = 0.0
        self._text: pu.Text | None = None
        self._sprites: dict[str, object] = {}

    def update(self, dt: float) -> None:
        self.time += dt

    def on_ready(self) -> None:
        """Bake the showcase shapes once; only sprite transforms animate.

        ``on_ready`` (bukan ``on_load``) adalah hook NodeUnit — dipanggil
        saat node ter-attach ke scene tree, saat GPU context sudah aktif.
        """
        canvas = self.one("@Renderer").canvas
        assets = self.one("@Assets")
        white = (255, 255, 255, 255)
        textures = {
            "rect": canvas.create_rect(
                rect=(0, 0, 120, 80),
                color=(50, 100, 200, 255),
                border_color=(255, 200, 50, 255),
                thickness=4.0,
                roundness=0.4,
                round_tl=True,
                round_br=True,
                round_tr=False,
                round_bl=False,
            ),
            "gradient_rect": canvas.create_rect(
                rect=(0, 0, 120, 80),
                gradient_v=((255, 0, 0, 255), (0, 0, 255, 255)),
                border_color=white,
                thickness=2.0,
            ),
            "pacman": canvas.create_circle(
                radius=50.0,
                color=(255, 255, 0, 255),
                border_color=(255, 100, 0, 255),
                sector_angles=(45.0, 315.0),
            ),
            "gradient_circle": canvas.create_circle(
                radius=50.0,
                color=(0, 255, 0, 255),
                gradient_outer=(0, 50, 0, 0),
            ),
            "triangle": canvas.create_triangle(
                v1=(50, 0),
                v2=(0, 80),
                v3=(100, 80),
                gradient=((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)),
                border_color=white,
                thickness=3.0,
            ),
            "polygon": canvas.create_poly(
                sides=6,
                radius=50.0,
                border_color=(255, 50, 200, 255),
                thickness=3.0,
                outline_only=True,
            ),
            "line": canvas.create_line(
                start=(0, 0),
                end=(150, 0),
                color=(0, 255, 255, 255),
                thickness=8.0,
            ),
            "bezier": canvas.create_line(
                start=(0, 0),
                end=(150, 40),
                color=(255, 100, 100, 255),
                thickness=4.0,
                bezier=True,
            ),
        }
        assets.store_textures({
            f"showcase_{key}": texture for key, texture in textures.items()
        })
        assets.build_texture_atlas([f"showcase_{key}" for key in textures])
        self._sprites = {
            key: assets.get_texture_data(f"showcase_{key}") for key in textures
        }
        self._text = pu.Text()

    def _render_sprite(
        self,
        renderer,
        key: str,
        pos: tuple[float, float],
        *,
        origin: tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
    ) -> None:
        data = self._sprites[key]
        renderer.render_sprite(
            texture=data.texture,
            source=data.source_rect,
            pos=pos,
            origin=origin,
            rotation=rotation,
            tint=(255, 255, 255, 255),
            layer=pu.Layer.ENTITIES,
        )

    def render_submit(self, renderer) -> None:
        if self._text is None:
            return

        white = (255, 255, 255, 255)
        rect_rot = math.degrees(self.time * 0.5)
        tri_rot = math.degrees(self.time * 1.5)
        line_rot = math.degrees(math.sin(self.time * 2.0)) * 45.0

        self._render_sprite(
            renderer, "rect", (100.0, 150.0), origin=(60.0, 40.0), rotation=rect_rot
        )
        self._render_sprite(renderer, "gradient_rect", (250.0, 110.0))
        self._render_sprite(
            renderer,
            "pacman",
            (120.0, 330.0),
            origin=(50.0, 50.0),
            rotation=-180.0 + math.degrees(math.sin(self.time) * 0.5),
        )
        self._render_sprite(
            renderer, "gradient_circle", (280.0, 330.0), origin=(50.0, 50.0)
        )
        self._render_sprite(
            renderer,
            "triangle",
            (500.0, 173.3333),
            origin=(51.5, 54.8333),
            rotation=tri_rot,
        )
        self._render_sprite(
            renderer, "polygon", (500.0, 330.0), origin=(51.5, 51.5), rotation=tri_rot
        )
        self._render_sprite(
            renderer, "line", (150.0, 480.0), origin=(4.0, 4.0), rotation=line_rot
        )
        self._render_sprite(renderer, "bezier", (398.0, 458.0))

        label_color = pr.LIGHTGRAY
        for text, pos in (
            ("Plyunit Baked Canvas Shapes", (20, 20)),
            ("1. Advanced Rectangle", (40, 70)),
            ("2. Advanced Circle", (40, 250)),
            ("3. Advanced Triangle", (400, 70)),
            ("4. Advanced Polygon", (400, 250)),
            ("5. Advanced Line", (40, 420)),
        ):
            self._text.push(
                text,
                pos=pos,
                font_size=20 if pos == (20, 20) else 16,
                color=white if pos == (20, 20) else label_color,
                spacing=1.0,
                z=0,
                layer=pu.Layer.UI,
            )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main")

    def on_load(self) -> None:
        self.root.attach(ShapeShowcase())


class ShapesApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        ShapesApp(),
        pu.AppConfig(
            title="Shapes Rendering Showcase",
            window_width=640,
            window_height=560,
            background_color=pr.Color(30, 30, 40, 255),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
