"""Example: Texture Atlas (opsional, in-memory)

Demonstrasi :meth:`Assets.build_texture_atlas` — menggabungkan semua aset
yang sudah dimuat menjadi satu texture atlas di memori, tanpa menulis apa
pun ke disk. Cukup satu baris di ``App.on_load``:

    self.one("@Assets").build_texture_atlas()

Fitur ini opsional: hapus baris tersebut dan game tetap berjalan persis
sama — ID aset tidak berubah, hanya tekstur di belakangnya yang
digabung. Manfaatnya terlihat pada statistik overlay: sprite yang berbagi
satu texture di-batch renderer menjadi satu draw call.

Aset tile (region spritesheet) dan player (frame animasi) ikut tergabung
ke atlas yang sama dengan aset standalone.
"""

import random
from pathlib import Path

import plyunit as pu

SPRITE_COUNT = 100
TILE_KEYS = [
    "well",
    "dirt_path_rect_1",
    "dirt_path_rect_3",
    "dirt_path_rect_5",
    "dirt_path_rect_7",
    "dirt_path_rect_9",
    "dirt_path_rect_11",
    "dirt_path_rect_13",
]
PLAYER_KEYS = [f"player:run_{i}" for i in range(4)]
ALL_KEYS = TILE_KEYS + PLAYER_KEYS


class Bouncer(pu.NodeUnit):
    """Satu sprite memantul; texture diselesaikan lazy lewat asset_key."""

    def __init__(self, asset_key: str) -> None:
        super().__init__(name=f"bouncer-{asset_key}")
        self.velocity = (
            random.uniform(-60.0, 60.0),
            random.uniform(-60.0, 60.0),
        )
        self.add_component(pu.builtin.SpriteRenderer(asset_key=asset_key))

    def update(self, dt: float) -> None:
        x, y = self.transform.local.position
        vx, vy = self.velocity
        x += vx * dt
        y += vy * dt
        if not 0.0 <= x <= 640.0 - 16.0:
            vx = -vx
            x += vx * dt
        if not 0.0 <= y <= 360.0 - 16.0:
            vy = -vy
            y += vy * dt
        self.velocity = (vx, vy)
        self.transform.set_position(x, y)


class MainScene(pu.SceneUnit):
    def on_load(self) -> None:
        for i in range(SPRITE_COUNT):
            bouncer = Bouncer(ALL_KEYS[i % len(ALL_KEYS)])
            bouncer.transform.set_position(
                random.uniform(0.0, 624.0),
                random.uniform(0.0, 344.0),
            )
            self.root.attach(bouncer)


class AtlasApp(pu.App):
    # Virtual view 640x360 dipusatkan di tengah field pantul (320, 180),
    # sehingga seluruh area permainan tepat mengisi layar.
    FIELD_SIZE = (640, 360)

    def on_load(self) -> None:
        self.camera: pu.Camera2D = pu.Camera2D(
            self.FIELD_SIZE,
            (self.FIELD_SIZE[0] / 2.0, self.FIELD_SIZE[1] / 2.0),
        )
        self.camera.setup(1280, 720)

        data_dir = Path(__file__).parent / "test_assets" / "data"
        assets = self.one("@Assets")
        assets.set_assets_path(data_dir)
        assets.load_spritesheet("tile/tiles.json")
        assets.load_folder("player/run")

        # --- Opsional: gabungkan semua aset di atas menjadi satu atlas ---
        # Hapus/komentari baris ini untuk membandingkan jumlah draw call;
        # game tetap berjalan identik tanpa atlas.
        page_ids = assets.build_texture_atlas()
        print(f"atlas pages: {page_ids}")

        self.animations.set_base_path(data_dir)
        self.animations.load("player/animations.json")

        self.one("@SceneManager").push(MainScene())
        self.text = pu.Text()
        self.renderer.profile_enabled = True
        self._hud_text = ""
        self._hud_frame = -1

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((245, 245, 245, 255))
        self.scene_manager.render(self.renderer)

        # HUD dibangun ulang tiap 15 frame (4x/detik) — angka FPS yang
        # berubah tiap frame akan memicu glyph shape cache-miss setiap
        # kali teksnya di-render ulang.
        stats = self.renderer.last_frame_profile
        if self._hud_frame != self.window.frame_count // 15:
            self._hud_frame = self.window.frame_count // 15
            self._hud_text = (
                f"FPS: {self.window.average_fps:.0f} | sprites: "
                f"{stats.get('sprite_count', 0):.0f} | texture runs: "
                f"{stats.get('texture_run_count', 0):.0f} | draw calls: "
                f"{stats.get('draw_call_count', 0):.0f} | atlas: aktif"
            )
        self.text.render(
            self._hud_text,
            pos=(8, 8),
            font_size=14,
            z=0,
            layer=pu.Layer.UI,
            color=(20, 20, 20, 255),
        )
        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()


def main():
    app = pu.init(
        AtlasApp(),
        pu.AppConfig(
            title="Texture Atlas Example",
            window_width=1280,
            window_height=720,
            target_fps=60,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
