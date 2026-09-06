"""Example: Blend Modes

Demonstrasi berbagai blend modes yang tersedia di plyunit.
- ALPHA (default)
- ADDITIVE (cocok untuk cahaya, api, laser)
- MULTIPLIED (cocok untuk shadow overlay)

Setiap mode ditampilkan sebagai panel terpisah dengan objek bergerak.
"""

import math

import plyunit as pu


class GlowOrb(pu.NodeUnit):
    """Orb bercahaya — menggunakan additive blending untuk efek glow."""

    def __init__(self, color: tuple[int, int, int, int], radius: float = 30.0) -> None:
        super().__init__(name="GlowOrb")
        self.color = color
        self.radius = radius
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def render_submit(self, renderer: pu.Renderer) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Outer glow (lebih besar, lebih transparan)
        pulse = 0.8 + math.sin(self.time * 3.0) * 0.2
        glow_color = (
            self.color[0],
            self.color[1],
            self.color[2],
            int(80 * pulse),
        )

        renderer.render_circle(
            z=0,
            layer=pu.Layer.EFFECTS,
            center=(x, y),
            radius=self.radius * 2.0 * pulse,
            color=glow_color,
            blend_mode=pu.BlendMode.ADDITIVE,
            scissor=self._resolved_scissor,
        )

        # Inner core
        renderer.render_circle(
            z=1,
            layer=pu.Layer.EFFECTS,
            center=(x, y),
            radius=self.radius * pulse,
            color=self.color,
            blend_mode=pu.BlendMode.ADDITIVE,
            scissor=self._resolved_scissor,
        )

        # Center bright spot
        renderer.render_circle(
            z=2,
            layer=pu.Layer.EFFECTS,
            center=(x, y),
            radius=self.radius * 0.3,
            color=(255, 255, 255, 200),
            blend_mode=pu.BlendMode.ADDITIVE,
            scissor=self._resolved_scissor,
        )


class ShadowOverlay(pu.NodeUnit):
    """Overlay gelap — menggunakan multiply blending."""

    def __init__(self) -> None:
        super().__init__(name="ShadowOverlay")
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def render_submit(self, renderer: pu.Renderer) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Shadow bergerak
        ox = math.sin(self.time * 1.5) * 40.0
        oy = math.cos(self.time * 1.0) * 20.0

        renderer.render_circle(
            z=0,
            layer=pu.Layer.EFFECTS,
            center=(x + ox, y + oy),
            radius=50.0,
            color=(100, 100, 120, 180),
            blend_mode=pu.BlendMode.MULTIPLIED,
            scissor=self._resolved_scissor,
        )


class NormalRect(pu.NodeUnit):
    """Kotak biasa dengan alpha blending (default)."""

    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="NormalRect")
        self.color = color
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        ox = math.sin(self.time * 2.0) * 30.0

        # Kotak semi-transparan
        canvas.draw_rectangle(
            rect=(x + ox - 25, y - 25, 50, 50),
            color=self.color,
            roundness=0.2,
            segments=6,
        )


class BlendPanel(pu.NodeUnit):
    """Panel untuk menampilkan satu blend mode."""

    def __init__(
        self,
        title: str,
        width: float,
        height: float,
        bg_color: tuple[int, int, int, int],
    ) -> None:
        super().__init__(name=f"Panel_{title}")
        self.title = title
        self.width = width
        self.height = height
        self.bg_color = bg_color

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Background
        canvas.draw_rectangle(
            rect=(x, y, self.width, self.height),
            color=self.bg_color,
            roundness=0.05,
            segments=4,
        )

        # Border
        canvas.draw_rectangle(
            rect=(x, y, self.width, self.height),
            color=(100, 100, 120, 255),
            outline_only=True,
            thickness=1.5,
            roundness=0.05,
            segments=4,
        )

        # Title
        canvas.draw_text(
            text=self.title,
            pos=(x + 10, y + 8),
            font_size=16,
            color=(220, 220, 240, 255),
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        pw, ph = 190, 350

        # Panel 1: Alpha (default)
        p1 = BlendPanel("ALPHA (Default)", pw, ph, (30, 30, 45, 255))
        self.root.attach(p1)
        p1.transform.set_position(15, 70)

        for i, color in enumerate([
            (255, 80, 80, 150),
            (80, 255, 80, 150),
            (80, 80, 255, 150),
        ]):
            rect = NormalRect(color)
            p1.attach(rect)
            rect.transform.set_position(95, 100 + i * 80)

        # Panel 2: Additive
        p2 = BlendPanel("ADDITIVE (Glow)", pw, ph, (15, 15, 25, 255))
        self.root.attach(p2)
        p2.transform.set_position(220, 70)

        for i, color in enumerate([
            (255, 100, 50, 200),
            (50, 200, 255, 200),
            (200, 50, 255, 200),
        ]):
            orb = GlowOrb(color, radius=20.0)
            p2.attach(orb)
            orb.transform.set_position(95, 100 + i * 80)

        # Panel 3: Multiplied
        p3 = BlendPanel("MULTIPLIED (Shadow)", pw, ph, (50, 50, 60, 255))
        self.root.attach(p3)
        p3.transform.set_position(425, 70)

        # Beberapa kotak cerah sebagai "lantai"
        for i in range(4):
            for j in range(4):
                bright = NormalRect((180 + i * 15, 160 + j * 15, 140, 255))
                p3.attach(bright)
                bright.transform.set_position(30 + i * 45, 80 + j * 65)

        # Shadow overlays
        shadow1 = ShadowOverlay()
        p3.attach(shadow1)
        shadow1.transform.set_position(95, 150)

        shadow2 = ShadowOverlay()
        p3.attach(shadow2)
        shadow2.transform.set_position(95, 280)


class BlendModeApp(pu.App):
    def on_load(self) -> None:
        self.scene_manager.push(MainScene())
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((15, 15, 20, 255))
        self.scene_manager.render(self.renderer)

        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="Blend Modes Comparison",
            pos=(200, 15),
            font_size=24,
            color=(220, 220, 240, 255),
        )
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="Alpha | Additive (glow/fire) | Multiplied (shadows)",
            pos=(100, 45),
            font_size=13,
            color=(140, 140, 160, 255),
        )

        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        BlendModeApp(),
        pu.AppConfig(
            title="Blend Modes Example",
            window_width=640,
            window_height=480,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
