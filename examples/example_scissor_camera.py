"""Demonstrate scissor clipping with a 2D camera.

World-space clip rectangles are converted to screen coordinates and intersected
with parent clips, including while the camera pans or zooms.

Controls:
    Arrow keys: Move the camera.
    Mouse wheel: Zoom in or out.
    R: Reset the camera.
"""

import math

import pyray as pr

import plyunit as pu
from plyunit.backends.ports.camera2d import ICamera2D
from plyunit.backends.ports.renderer import ICanvas2D


class BouncingBall(pu.NodeUnit):
    """Move a ball in a circle, clipped by its parent's scissor rectangle."""

    def __init__(self, color: tuple[int, int, int, int], speed: float = 2.0) -> None:
        super().__init__(name="BouncingBall")
        self.color = color
        self.speed = speed
        self.time = 0.0
        self.y_sort_enabled = False

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Circular movement
        ox = math.cos(self.time * self.speed) * 80.0
        oy = math.sin(self.time * self.speed) * 80.0

        canvas.draw_circle(center=(x + ox, y + oy), radius=25.0, color=self.color)

    def get_render_bounds(self) -> tuple[float, float, float, float]:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Orbit radius 80 + circle radius 25
        return (x - 105.0, y - 105.0, 210.0, 210.0)


class ScissorPanel(pu.NodeUnit):
    """Clip child nodes to a panel's world-space rectangle."""

    def __init__(
        self,
        width: float,
        height: float,
        title: str,
        border_color: tuple[int, int, int, int],
    ) -> None:
        super().__init__(name=f"ScissorPanel_{title}")
        self.width = width
        self.height = height
        self.title = title
        self.border_color = border_color

    def update(self, dt: float) -> None:
        # Keep the clip rectangle aligned with the world transform.
        wt = self.transform.world
        x, y = wt.position
        self.set_scissor((x, y, self.width, self.height))

    def get_render_bounds(self) -> tuple[float, float, float, float]:
        wt = self.world_transform_lerp()
        x, y = wt.position
        return (x, y, self.width, self.height)

    def render_submit(
        self, renderer: pu.Renderer, context: pu.RenderContext | None = None
    ) -> None:
        super().render_submit(renderer, context)

        wt = self.world_transform_lerp()
        x, y = wt.position

        # Translucent background
        renderer.render_custom(
            z=-1,
            layer=pu.Layer.WORLD,
            draw_func=lambda canvas, rect=(x, y, self.width, self.height): (
                canvas.draw_rectangle(rect=rect, color=(30, 30, 50, 100))
            ),
            scissor=self._resolved_scissor,
        )

        # Border
        renderer.render_custom(
            z=10,
            layer=pu.Layer.WORLD,
            draw_func=lambda canvas, rect=(x, y, self.width, self.height), color=self.border_color: (
                canvas.draw_rectangle(
                    rect=rect,
                    color=color,
                    outline_only=True,
                    thickness=2.0,
                )
            ),
        )

        # Title
        self.one("@Text").render(
            z=10,
            layer=pu.Layer.WORLD,
            text=self.title,
            pos=(x + 5, y + 5),
            font_size=16,
            color=self.border_color,
        )


class ScrollingText(pu.NodeUnit):
    """Scroll text horizontally through its parent's scissor rectangle."""

    def __init__(self, text: str, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="ScrollingText")
        self.text = text
        self.color = color
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position
        ox = math.sin(self.time * 1.5) * 200.0
        canvas.draw_text(
            text=self.text, pos=(x + ox - 100, y), font_size=18, color=self.color
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # Main panel (red)
        main_panel = ScissorPanel(350, 300, "World Panel (Scissor)", (255, 80, 80, 255))
        self.root.attach(main_panel)
        main_panel.transform.set_position(50, 50)

        # Green ball inside the main panel
        ball1 = BouncingBall((100, 255, 100, 255), speed=2.0)
        main_panel.attach(ball1)
        ball1.transform.set_position(175, 150)

        # Scrolling text
        scroll = ScrollingText("LONG TEXT CLIPPED BY SCISSOR!", (200, 200, 200, 255))
        main_panel.attach(scroll)
        scroll.transform.set_position(175, 250)

        # The nested blue panel intersects its parent's clip rectangle.
        inner_panel = ScissorPanel(150, 150, "Nested", (80, 150, 255, 255))
        main_panel.attach(inner_panel)
        inner_panel.transform.set_position(100, 75)

        # Yellow ball inside the nested panel
        ball2 = BouncingBall((255, 255, 80, 255), speed=3.0)
        inner_panel.attach(ball2)
        ball2.transform.set_position(75, 75)

        # Independent panel (orange)
        side_panel = ScissorPanel(120, 200, "Side", (255, 165, 0, 255))
        self.root.attach(side_panel)
        side_panel.transform.set_position(440, 100)

        ball3 = BouncingBall((150, 200, 255, 255), speed=4.0)
        side_panel.attach(ball3)
        ball3.transform.set_position(60, 100)

        # This ball has no scissor rectangle and is not clipped.
        free_ball = BouncingBall((255, 100, 255, 255), speed=1.5)
        self.root.attach(free_ball)
        free_ball.transform.set_position(300, 420)


class ScissorCameraApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.mouse = pu.Mouse()
        self.input.map("cam_right", pr.KeyboardKey.KEY_RIGHT)
        self.input.map("cam_left", pr.KeyboardKey.KEY_LEFT)
        self.input.map("cam_down", pr.KeyboardKey.KEY_DOWN)
        self.input.map("cam_up", pr.KeyboardKey.KEY_UP)
        self.input.map("reset", pr.KeyboardKey.KEY_R)

        # Free-look: snap, no dead zone / slowness lag.
        self.camera: ICamera2D = pu.Camera2D(
            size=(640, 500),
            position=(320, 250),
            slowness=0.0,
        )
        self.camera.setup(640, 500)
        self.camera.teleport((320, 250))
        self._zoom = 1.0

        self.scene_manager.push(MainScene())
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step

        wheel = self.mouse.get_wheel_move()
        if wheel != 0:
            self._zoom = max(0.3, min(3.0, self._zoom + wheel * 0.1))
            self.camera.set_zoom(self._zoom)

        if self.input.is_pressed("reset"):
            self.camera.teleport((320, 250))
            self._zoom = 1.0
            self.camera.set_zoom(self._zoom)

        speed = 260.0 * dt
        dx = self.input.get_axis("cam_left", "cam_right")
        dy = self.input.get_axis("cam_up", "cam_down")
        if dx or dy:
            self.camera.move((dx * speed, dy * speed))
            self.camera.set_target(tuple(self.camera.pos))

        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((20, 20, 30, 255))
        self.scene_manager.render(self.renderer)

        # Screen-space UI is not affected by the camera.
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="Arrow keys: move | Scroll: zoom | R: reset",
            pos=(10, 10),
            font_size=16,
            color=(180, 180, 180, 255),
        )

        zoom_text = f"Zoom: {self._zoom:.1f}x"
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text=zoom_text,
            pos=(10, 30),
            font_size=16,
            color=(180, 180, 180, 255),
        )

        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()


def main():
    app = pu.init(
        ScissorCameraApp(),
        pu.AppConfig(
            title="Scissor + Camera Example",
            window_width=640,
            window_height=500,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
