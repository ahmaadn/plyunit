import raylib as ry

import plyunit as pu


class VelocityComponent(pu.Component):
    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        super().__init__()
        self.x = x
        self.y = y


class PlayerControllerComponent(pu.Component):
    def update(self, dt: float) -> None:
        dir_x = self.unit.one("@Input").get_axis("move_left", "move_right")
        dir_y = self.unit.one("@Input").get_axis("move_up", "move_down")

        velocity = self.unit[VelocityComponent]
        velocity.x = dir_x * self.unit.speed
        velocity.y = dir_y * self.unit.speed


class PlayerUnit(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__(name="Player", tags={"player"})

        self.speed = 200.0
        self.add_component(VelocityComponent())
        self.add_component(PlayerControllerComponent())

    def update(self, dt: float) -> None:
        vx, vy = (
            self[VelocityComponent].x,
            self[VelocityComponent].y,
        )
        cur_x, cur_y = self.transform.local.position

        new_x = cur_x + vx * dt
        new_y = cur_y + vy * dt

        self.transform.set_position(new_x, new_y)

    def render_submit(self, renderer: pu.Renderer) -> None:

        # gunakan world_transform_lerp untuk mendapatkan posisi yang
        # lebih halus saat rendering
        world_transform = self.world_transform_lerp()

        x, y = world_transform.position
        renderer.render_rect(
            z=0,
            layer=pu.Layer.WORLD,
            rect=(x, y, 30.0, 30.0),
            color=(0, 255, 0, 255),
        )


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        player = PlayerUnit()
        self.root.attach(player)
        player.transform.set_position(200, 200)


class MyApp(pu.App):
    def on_load(self) -> None:
        if not hasattr(self, "input"):
            self.input = pu.Input()

        self.input.map("move_up", ry.KEY_W, ry.KEY_UP)
        self.input.map("move_down", ry.KEY_S, ry.KEY_DOWN)
        self.input.map("move_left", ry.KEY_A, ry.KEY_LEFT)
        self.input.map("move_right", ry.KEY_D, ry.KEY_RIGHT)

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
        MyApp(),
        pu.AppConfig(
            title="Input Service Example",
            window_height=400,
            window_width=300,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
