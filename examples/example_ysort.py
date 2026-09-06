"""Example: Y-Sort Top-Down

Demonstrasi Y-sort untuk game top-down RPG.
Objek yang lebih dekat ke bawah layar digambar di atas objek yang lebih jauh.

- Pohon-pohon statis dengan Y-sort
- Karakter yang bisa bergerak, otomatis tersort berdasarkan posisi Y
- Layer ENTITIES ditandai sebagai Y-sort layer

Kontrol:
- WASD: gerakkan karakter
"""

import math

import pyray as pr

import plyunit as pu


class Tree(pu.NodeUnit):
    """Pohon statis — di-sort berdasarkan posisi Y (kaki pohon)."""

    def __init__(
        self, color: tuple[int, int, int, int], trunk_height: float = 60.0
    ) -> None:
        super().__init__(name="Tree")
        self.color = color
        self.trunk_height = trunk_height
        self.y_sort_enabled = True
        self.layer = pu.Layer.ENTITIES

    def draw(self, canvas: pu.Canvas) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Bayangan
        canvas.draw_ellipse(
            center=(x, y + 5),
            radius_h=20.0,
            radius_v=8.0,
            color=(0, 0, 0, 60),
        )

        # Batang
        trunk_color = (
            max(0, self.color[0] - 100),
            max(0, self.color[1] - 60),
            max(0, self.color[2] - 80),
            255,
        )
        canvas.draw_rectangle(
            rect=(x - 6, y - self.trunk_height, 12, self.trunk_height),
            color=trunk_color,
        )

        # Daun (lingkaran-lingkaran)
        leaf_y = y - self.trunk_height
        canvas.draw_circle(center=(x, leaf_y - 10), radius=22.0, color=self.color)
        canvas.draw_circle(
            center=(x - 12, leaf_y + 5),
            radius=16.0,
            color=(
                max(0, self.color[0] - 30),
                max(0, self.color[1] - 20),
                max(0, self.color[2] - 30),
                255,
            ),
        )
        canvas.draw_circle(
            center=(x + 14, leaf_y + 3),
            radius=18.0,
            color=(
                min(255, self.color[0] + 20),
                min(255, self.color[1] + 10),
                min(255, self.color[2] + 20),
                255,
            ),
        )


class Character(pu.NodeUnit):
    """Karakter yang bisa digerakkan — Y-sort berdasarkan posisi kaki."""

    def __init__(
        self,
        name: str,
        body_color: tuple[int, int, int, int],
        is_player: bool = False,
    ) -> None:
        super().__init__(name=name)
        self.body_color = body_color
        self.is_player = is_player
        self.y_sort_enabled = True
        self.layer = pu.Layer.ENTITIES
        self.time = 0.0
        self.speed = 150.0

    def update(self, dt: float) -> None:
        self.time += dt

        if self.is_player:
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
        else:
            # NPC: gerakan idle
            cx, cy = self.transform.local.position
            base_y = getattr(self, "_base_y", cy)
            if not hasattr(self, "_base_y"):
                self._base_y = cy
            # pyrefly: ignore [unsupported-operation]
            new_y = base_y + math.sin(self.time * 0.8) * 30.0
            self.transform.set_position(cx, new_y)

    def draw(self, canvas: pu.Canvas) -> None:
        wt = self.world_transform_lerp()
        x, y = wt.position

        # Bayangan
        canvas.draw_ellipse(
            center=(x, y + 2),
            radius_h=14.0,
            radius_v=5.0,
            color=(0, 0, 0, 60),
        )

        # Badan
        canvas.draw_rectangle(
            rect=(x - 10, y - 30, 20, 30),
            color=self.body_color,
            roundness=0.3,
            segments=6,
        )

        # Kepala
        head_color = (
            min(255, self.body_color[0] + 40),
            min(255, self.body_color[1] + 40),
            min(255, self.body_color[2] + 40),
            255,
        )
        canvas.draw_circle(center=(x, y - 38), radius=10.0, color=head_color)

        # Label
        if self.is_player:
            canvas.draw_text(
                text="YOU",
                pos=(x - 12, y - 55),
                font_size=12,
                color=(255, 255, 100, 255),
            )


class Ground(pu.NodeUnit):
    """Grid lantai untuk referensi visual."""

    def __init__(self) -> None:
        super().__init__(name="Ground")
        self.layer = pu.Layer.BACKGROUND

    def draw(self, canvas: pu.Canvas) -> None:
        # Grid
        for gx in range(0, 640, 40):
            canvas.draw_line(
                start=(gx, 0),
                end=(gx, 500),
                color=(40, 50, 40, 80),
                thickness=1.0,
            )
        for gy in range(0, 500, 40):
            canvas.draw_line(
                start=(0, gy),
                end=(640, gy),
                color=(40, 50, 40, 80),
                thickness=1.0,
            )


class YSortInfo(pu.NodeUnit):
    """UI overlay menampilkan info Y-sort."""

    def __init__(self, player: Character, entities: list[pu.NodeUnit]) -> None:
        super().__init__(name="YSortInfo")
        self.player_ref = player
        self.entity_refs = entities
        self.layer = pu.Layer.UI

    def draw(self, canvas: pu.Canvas) -> None:
        canvas.draw_text(
            text="WASD: move player | Entities Y-sorted automatically",
            pos=(10, 10),
            font_size=14,
            color=(180, 180, 180, 255),
        )

        # Tampilkan urutan Y-sort
        sorted_entities = sorted(
            self.entity_refs,
            key=lambda e: e.transform.world.position[1],
        )

        y_offset = 30
        canvas.draw_text(
            text="Y-Sort Order:",
            pos=(10, y_offset),
            font_size=13,
            color=(150, 150, 150, 255),
        )
        y_offset += 18
        for i, entity in enumerate(sorted_entities):
            ey = entity.transform.world.position[1]
            name = entity.name
            color = (
                (255, 255, 100, 255)
                if entity is self.player_ref
                else (150, 150, 150, 255)
            )
            canvas.draw_text(
                text=f"  {i + 1}. {name} (y={ey:.0f})",
                pos=(10, y_offset),
                font_size=12,
                color=color,
            )
            y_offset += 15


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # Tandai layer ENTITIES sebagai Y-sort layer
        pu.Renderer.enable_y_sort_layer(pu.Layer.ENTITIES)

        # Ground
        ground = Ground()
        self.root.attach(ground)

        entities: list[pu.NodeUnit] = []

        # Pohon-pohon
        tree_data = [
            ((60, 200, 60, 255), (150, 200)),
            ((40, 180, 40, 255), (350, 150)),
            ((80, 220, 80, 255), (500, 300)),
            ((50, 190, 50, 255), (250, 350)),
            ((70, 210, 70, 255), (450, 180)),
        ]
        for i, (color, pos) in enumerate(tree_data):
            tree = Tree(color, trunk_height=50.0 + i * 5)
            self.root.attach(tree)
            tree.transform.set_position(*pos)
            entities.append(tree)

        # Player
        player = Character("Player", (80, 120, 220, 255), is_player=True)
        self.root.attach(player)
        player.transform.set_position(300, 250)
        entities.append(player)

        # NPCs
        npc1 = Character("NPC_Red", (220, 80, 80, 255))
        self.root.attach(npc1)
        npc1.transform.set_position(200, 280)
        entities.append(npc1)

        npc2 = Character("NPC_Blue", (80, 80, 220, 255))
        self.root.attach(npc2)
        npc2.transform.set_position(400, 220)
        entities.append(npc2)

        # UI info
        info = YSortInfo(player, entities)
        self.root.attach(info)


class YSortApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.input.map("move_up", pr.KeyboardKey.KEY_W)
        self.input.map("move_down", pr.KeyboardKey.KEY_S)
        self.input.map("move_left", pr.KeyboardKey.KEY_A)
        self.input.map("move_right", pr.KeyboardKey.KEY_D)
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
        YSortApp(),
        pu.AppConfig(
            title="Y-Sort Top-Down Example",
            window_width=640,
            window_height=500,
            background_color=pr.Color(25, 30, 25, 255),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
