"""Example: Render Target (Minimap)

Demonstrasi penggunaan Render Target untuk membuat minimap.
- World utama di-render ke screen via default pass
- Minimap di-render ke RenderTexture2D via pass terpisah
- Minimap ditampilkan sebagai overlay di sudut layar

Kontrol:
- WASD: gerakkan player
"""

import math

import pyray as pr

import plyunit as pu


class Player(pu.NodeUnit):
    """Player yang bisa digerakkan."""

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

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Bayangan
        canvas.draw_ellipse(
            center=(x, y + 3),
            radius_h=12.0,
            radius_v=5.0,
            color=(0, 0, 0, 60),
        )

        # Badan
        canvas.draw_rectangle(
            rect=(x - 8, y - 24, 16, 24),
            color=(80, 150, 255, 255),
            roundness=0.3,
            segments=6,
        )

        # Kepala
        canvas.draw_circle(
            center=(x, y - 30),
            radius=8.0,
            color=(120, 190, 255, 255),
        )


class House(pu.NodeUnit):
    """Rumah sederhana."""

    def __init__(self, color: tuple[int, int, int, int]) -> None:
        super().__init__(name="House")
        self.color = color
        self.layer = pu.Layer.WORLD

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Badan rumah
        canvas.draw_rectangle(
            rect=(x - 30, y - 25, 60, 50),
            color=self.color,
        )

        # Atap (triangle)
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

        # Pintu
        canvas.draw_rectangle(
            rect=(x - 8, y + 5, 16, 20),
            color=(60, 40, 20, 255),
        )


class WorldBorder(pu.NodeUnit):
    """Batas dunia — garis border."""

    WORLD_W = 800
    WORLD_H = 600

    def __init__(self) -> None:
        super().__init__(name="WorldBorder")
        self.layer = pu.Layer.BACKGROUND

    def get_render_bounds(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, float(self.WORLD_W), float(self.WORLD_H))

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
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
    """Renders the minimap overlay ke screen.

    Ini menggambar dunia dalam skala kecil langsung menggunakan custom draw,
    menunjukkan posisi player dan objek-objek penting.
    """

    def __init__(self, player: Player, houses: list[House]) -> None:
        super().__init__(name="MinimapRenderer")
        self.layer = pu.Layer.OVERLAY
        self.player_ref = player
        self.house_refs = houses

        # Ukuran dan posisi minimap di screen
        self.map_w = 160
        self.map_h = 120
        self.map_x = 640 - self.map_w - 10  # Kanan atas
        self.map_y = 10

        # Skala world -> minimap
        self.scale_x = self.map_w / WorldBorder.WORLD_W
        self.scale_y = self.map_h / WorldBorder.WORLD_H

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        mx, my = self.map_x, self.map_y

        # Background minimap
        canvas.draw_rectangle(
            rect=(mx - 2, my - 2, self.map_w + 4, self.map_h + 4),
            color=(40, 40, 50, 200),
            roundness=0.05,
            segments=4,
        )
        canvas.draw_rectangle(
            rect=(mx, my, self.map_w, self.map_h),
            color=(20, 25, 20, 220),
        )

        # Border
        canvas.draw_rectangle(
            rect=(mx, my, self.map_w, self.map_h),
            color=(100, 120, 100, 200),
            outline_only=True,
            thickness=1.0,
        )

        # Gambar rumah-rumah di minimap
        for house in self.house_refs:
            hx, hy = house.transform.world.position
            hmx = mx + hx * self.scale_x
            hmy = my + hy * self.scale_y
            canvas.draw_rectangle(
                rect=(hmx - 4, hmy - 4, 8, 8),
                color=(180, 120, 80, 200),
            )

        # Gambar player di minimap
        px, py = self.player_ref.transform.world.position
        pmx = mx + px * self.scale_x
        pmy = my + py * self.scale_y
        canvas.draw_circle(
            center=(pmx, pmy),
            radius=4.0,
            color=(80, 200, 255, 255),
        )

        # Label
        canvas.draw_text(
            text="MINIMAP",
            pos=(mx + 5, my + self.map_h + 5),
            font_size=11,
            color=(120, 120, 140, 200),
        )


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

        # Rumah-rumah
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

        # Minimap (UI overlay — tidak terpengaruh kamera)
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

        # Setup camera mengikuti player
        self.camera: pu.Camera2D = pu.Camera2D(size=(640, 500), position=(400, 300))
        self.camera.setup(640, 500)
        self.camera.teleport((400, 300))
        self.camera.lerp_speed = 0.1
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
