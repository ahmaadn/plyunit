"""Demonstrate basic and nested scissor clipping.

Clip rectangles use world coordinates. The renderer converts them to screen
coordinates and intersects each nested rectangle with its parent's clip.
"""

import math

import pyray as pr

import plyunit as pu
from plyunit.backends.ports.renderer import ICanvas2D


class AnimatedChild(pu.NodeUnit):
    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="AnimatedChild")
        self.color = color
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        world_transform = self.world_transform_lerp()
        x, y = world_transform.position

        # Move in a circle across the clip boundary.
        offset_x = math.cos(self.time * 3.0) * 80.0
        offset_y = math.sin(self.time * 3.0) * 80.0

        canvas.draw_rectangle(
            rect=(x + offset_x - 30, y + offset_y - 30, 60.0, 60.0),
            color=self.color,
        )


class ScrollingTextChild(pu.NodeUnit):
    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="ScrollingText")
        self.color = color
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        world_transform = self.world_transform_lerp()
        x, y = world_transform.position

        offset_x = math.sin(self.time * 2.0) * 200.0

        canvas.draw_text(
            text="LONG TEXT CLIPPED BY SCISSOR",
            pos=(x + offset_x - 150, y),
            font_size=20,
            color=self.color,
        )


class MovingCircleChild(pu.NodeUnit):
    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="MovingCircle")
        self.color = color
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        world_transform = self.world_transform_lerp()
        x, y = world_transform.position

        offset_y = math.sin(self.time * 4.0) * 80.0

        canvas.draw_circle(
            center=(x, y + offset_y),
            radius=50.0,
            color=self.color,
        )


class CustomDrawChild(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="CustomDraw")
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, canvas: ICanvas2D) -> None:
        world_transform = self.world_transform_lerp()
        x, y = world_transform.position

        offset_x = math.cos(self.time * 2.0) * 80.0

        base_x = int(x + offset_x)
        base_y = int(y)
        size = 30
        angle = self.time * 100.0

        # Draw a rotating X.
        p1_x = int(base_x + math.cos(math.radians(angle)) * size)
        p1_y = int(base_y + math.sin(math.radians(angle)) * size)
        p2_x = int(base_x - math.cos(math.radians(angle)) * size)
        p2_y = int(base_y - math.sin(math.radians(angle)) * size)
        pr.draw_line(p1_x, p1_y, p2_x, p2_y, (0, 0, 0, 255))

        p3_x = int(base_x + math.cos(math.radians(angle + 90)) * size)
        p3_y = int(base_y + math.sin(math.radians(angle + 90)) * size)
        p4_x = int(base_x - math.cos(math.radians(angle + 90)) * size)
        p4_y = int(base_y - math.sin(math.radians(angle + 90)) * size)
        pr.draw_line(p3_x, p3_y, p4_x, p4_y, (0, 0, 0, 255))

        pr.draw_line(base_x, int(y - 150), base_x, int(y + 150), (100, 100, 100, 150))


class ScissorContainer(pu.NodeUnit):
    def __init__(
        self, width: float, height: float, title: str, color: tuple[int, int, int, int]
    ) -> None:
        super().__init__(name="ScissorContainer")
        self.width = width
        self.height = height
        self.title = title
        self.color = color

    def update(self, dt: float) -> None:
        # Animate the outer container.
        if self.title == "Outer Scissor":
            self.time = getattr(self, "time", 0.0) + dt
            self.transform.set_position(
                120.0 + math.sin(self.time) * 40.0,
                100.0 + math.cos(self.time * 1.5) * 20.0,
            )

        # Update the clip rectangle in world coordinates.
        world_transform = self.transform.world
        x, y = world_transform.position
        self.set_scissor((x, y, self.width, self.height))

    def draw(self, canvas: ICanvas2D) -> None:
        world_transform = self.world_transform_lerp()
        x, y = world_transform.position

        # Outline the clipping area.
        canvas.draw_rectangle(
            rect=(x, y, self.width, self.height),
            color=self.color,
            outline_only=True,
            thickness=2.0,
        )

        canvas.draw_text(
            text=self.title,
            pos=(x + 5, y + 5),
            font_size=20,
            color=self.color,
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # Outer container (red clip)
        outer = ScissorContainer(300, 300, "Outer Scissor", (255, 0, 0, 255))
        self.root.attach(outer)
        outer.transform.set_position(120, 100)

        # Child clipped by the red container
        child1 = AnimatedChild((0, 255, 0, 255))
        outer.attach(child1)
        child1.transform.set_position(150, 150)

        # Scrolling text tests text clipping.
        text_child = ScrollingTextChild((50, 50, 50, 255))
        outer.attach(text_child)
        text_child.transform.set_position(150, 250)

        # Inner container (nested blue clip)
        inner = ScissorContainer(150, 150, "Inner", (0, 100, 255, 255))
        outer.attach(inner)
        inner.transform.set_position(75, 75)

        # Child inside the blue container
        child2 = AnimatedChild((255, 255, 0, 255))
        inner.attach(child2)
        child2.transform.set_position(75, 75)

        # A sibling container tests independent clipping bounds.
        side_container = ScissorContainer(100, 250, "Side", (255, 120, 0, 255))
        self.root.attach(side_container)
        side_container.transform.set_position(470, 125)

        circle_child = MovingCircleChild((100, 200, 255, 255))
        side_container.attach(circle_child)
        circle_child.transform.set_position(50, 125)

        # Custom draw
        custom_child = CustomDrawChild()
        side_container.attach(custom_child)
        custom_child.transform.set_position(50, 200)


class MyApp(pu.App):
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
        self.window.clear_background((245, 245, 245, 255))
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        MyApp(),
        pu.AppConfig(
            title="Nested Scissor Example",
            window_width=600,
            window_height=500,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
