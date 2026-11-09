"""Render a world-space scene with an offscreen minimap overlay.

The minimap pass draws into a render-target handle before the screen-space
UI pass samples its color-attachment texture. Use WASD to move the player.
"""

import math

import pyray as pr

import plyunit as pu
from plyunit.backends.ports.camera2d import ICamera2D
from plyunit.backends.ports.handler import RenderTextureHandle
from plyunit.backends.ports.renderer import ICanvas2D


class Player(pu.NodeUnit):
    """Move the player using the mapped directional actions."""

    def __init__(self) -> None:
        super().__init__(name="Player")
        self.layer = pu.Layer.ENTITIES
        self.speed = 180.0

    def update(self, dt: float) -> None:
        kb = self.one("@Input", scope="global")
        dx = kb.get_axis("move_left", "move_right")
        dy = kb.get_axis("move_up", "move_down")
        if dx != 0 or dy != 0:
            length = math.sqrt(dx * dx + dy * dy)
            dx /= length
            dy /= length
            cx, cy = self.transform.local.position
            self.transform.set_position(
                cx + dx * self.speed * dt,
                cy + dy * self.speed * dt,
            )

    def draw(self, canvas: ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Shadow
        canvas.draw_ellipse(
            center=(x, y + 3),
            radius_h=12.0,
            radius_v=5.0,
            color=(0, 0, 0, 60),
        )

        # Body
        canvas.draw_rectangle(
            rect=(x - 8, y - 24, 16, 24),
            color=(80, 150, 255, 255),
            roundness=0.3,
            segments=6,
        )

        # Head
        canvas.draw_circle(
            center=(x, y - 30),
            radius=8.0,
            color=(120, 190, 255, 255),
        )


class House(pu.NodeUnit):
    """Draw a simple house."""

    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="House")
        self.color = color
        self.layer = pu.Layer.WORLD

    def draw(self, canvas: ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # House walls
        canvas.draw_rectangle(
            rect=(x - 30, y - 25, 60, 50),
            color=self.color,
        )

        # Roof
        canvas.draw_triangle(
            v1=(x, y - 55),
            v2=(x - 38, y - 25),
            v3=(x + 38, y - 25),
            color=(
                max(0, self.color[0] - 50),
                max(0, self.color[1] - 30),
                max(0, self.color[2] - 30),
                255,
            ),
        )

        # Door
        canvas.draw_rectangle(
            rect=(x - 8, y + 5, 16, 20),
            color=(60, 40, 20, 255),
        )


class WorldBorder(pu.NodeUnit):
    """Draw the world boundary and reference grid."""

    WORLD_W = 800
    WORLD_H = 600

    def __init__(self) -> None:
        super().__init__(name="WorldBorder")
        self.layer = pu.Layer.BACKGROUND

    def get_render_bounds(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, float(self.WORLD_W), float(self.WORLD_H))

    def draw(self, canvas: ICanvas2D) -> None:
        # Grid
        for gx in range(0, self.WORLD_W + 1, 50):
            canvas.draw_line(
                start=(gx, 0),
                end=(gx, self.WORLD_H),
                color=(35, 40, 35, 100),
            )
        for gy in range(0, self.WORLD_H + 1, 50):
            canvas.draw_line(
                start=(0, gy),
                end=(self.WORLD_W, gy),
                color=(35, 40, 35, 100),
            )

        # Border
        canvas.draw_rectangle(
            rect=(0, 0, self.WORLD_W, self.WORLD_H),
            color=(100, 120, 100, 200),
            outline_only=True,
            thickness=2.0,
        )


class MinimapRenderer(pu.NodeUnit):
    """Render map markers offscreen and display the target as a UI overlay."""

    def __init__(self, player: Player, houses: list[House]) -> None:
        super().__init__(name="MinimapRenderer")
        self.layer = pu.Layer.OVERLAY
        self.player_ref = player
        self.house_refs = houses
        self.map_w = 160
        self.map_h = 120
        self.map_x = 640 - self.map_w - 10
        self.map_y = 10
        self.scale_x = self.map_w / WorldBorder.WORLD_W
        self.scale_y = self.map_h / WorldBorder.WORLD_H
        self._target: RenderTextureHandle | None = None
        self._renderer: pu.Renderer | None = None

    def on_ready(self) -> None:
        renderer = self.one("@Renderer")
        self._renderer = renderer
        self._target = renderer.canvas.load_render_texture(self.map_w, self.map_h)
        renderer.create_pass(
            "minimap",
            target=self._target,
            clear_color=(20, 25, 20, 255),
            order=-10,
            screen_space=True,
        )

    def render_submit(self, renderer: pu.Renderer, context=None) -> None:
        if self._target is None:
            return
        renderer.render_custom(draw_func=self._draw_map, pass_name="minimap")
        super().render_submit(renderer, context)

    def _draw_map(self, canvas: ICanvas2D) -> None:
        """Draw map-local markers while the minimap target is active."""
        for house in self.house_refs:
            hx, hy = house.world_transform_lerp().position
            canvas.draw_rectangle(
                rect=(hx * self.scale_x - 4, hy * self.scale_y - 4, 8, 8),
                color=(180, 120, 80, 255),
            )
        px, py = self.player_ref.world_transform_lerp().position
        canvas.draw_circle(
            center=(px * self.scale_x, py * self.scale_y),
            radius=4.0,
            color=(80, 200, 255, 255),
        )

    def draw(self, canvas: ICanvas2D) -> None:
        if self._target is None:
            return
        mx, my = self.map_x, self.map_y
        canvas.draw_rectangle(
            rect=(mx - 2, my - 2, self.map_w + 4, self.map_h + 4),
            color=(40, 40, 50, 200),
            roundness=0.05,
            segments=4,
        )
        # Raylib render targets are vertically inverted. Sample the borrowed
        # color attachment directly; do not wrap it or unload it separately.
        canvas.draw_texture(
            texture=self._target.texture,
            source=(0, 0, self.map_w, -self.map_h),
            dest=(mx, my, self.map_w, self.map_h),
        )
        canvas.draw_rectangle(
            rect=(mx, my, self.map_w, self.map_h),
            color=(100, 120, 100, 200),
            outline_only=True,
            thickness=1.0,
        )
        canvas.draw_text(
            text="MINIMAP",
            pos=(mx + 5, my + self.map_h + 5),
            font_size=11,
            color=(120, 120, 140, 200),
        )

    def on_exit_tree(self) -> None:
        """Release the render target while its graphics context is still alive."""
        if self._renderer is not None and self._target is not None:
            self._renderer.remove_pass("minimap")
            self._renderer.canvas.unload_render_texture(self._target)
            self._target = None
        super().on_exit_tree()


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # World border
        border = WorldBorder()
        self.root.attach(border)

        # Player
        player = Player()
        self.root.attach(player)
        player.transform.set_position(400, 300)

        # Houses
        houses = []
        house_data = [
            ((180, 100, 80, 255), (150, 150)),
            ((100, 160, 80, 255), (600, 200)),
            ((80, 100, 180, 255), (350, 450)),
            ((180, 180, 80, 255), (100, 400)),
            ((180, 80, 130, 255), (550, 480)),
        ]
        for color, pos in house_data:
            house = House(color)
            self.root.attach(house)
            house.transform.set_position(*pos)
            houses.append(house)

        # Screen-space minimap overlay
        minimap = MinimapRenderer(player, houses)
        self.root.attach(minimap)

        self.one("@Camera2D").set_target(player)


class RenderTargetApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.input.map("move_up", pr.KeyboardKey.KEY_W)
        self.input.map("move_down", pr.KeyboardKey.KEY_S)
        self.input.map("move_left", pr.KeyboardKey.KEY_A)
        self.input.map("move_right", pr.KeyboardKey.KEY_D)

        # Follow the player with a short smoothing interval.
        self.camera: ICamera2D = pu.Camera2D(
            size=(640, 500), position=(400, 300), slowness=0.1
        )
        self.camera.setup(640, 500)
        self.camera.teleport((400, 300))
        self.scene_manager.push(MainScene())
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((20, 25, 20, 255))
        self.scene_manager.render(self.renderer)

        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="WASD: move | Camera follows player | Minimap in corner",
            pos=(10, 10),
            font_size=14,
            color=(160, 160, 180, 255),
        )

        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()


def main():
    app = pu.init(
        RenderTargetApp(),
        pu.AppConfig(
            title="Render Target (Minimap) Example",
            window_width=640,
            window_height=500,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
