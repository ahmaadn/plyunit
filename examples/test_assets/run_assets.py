import json
import logging
from pathlib import Path

import plyunit as pu

logger = logging.Logger(__name__)


def load_tiles(assets: pu.Assets) -> None:
    """Register the tile texture and regions that fit its actual image bounds.

    Args:
        assets: Configured service whose base contains the ``tile`` directory.
    """
    config_path = assets.asset_base_path / "tile" / "tiles.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assets.load_asset("tile/tileset.png", asset_id="showcase_tiles")
    root = assets.get_asset("showcase_tiles")

    regions = {}
    for name, rect in config["regions"].items():
        x, y, width, height = rect
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > root.width
            or y + height > root.height
        ):
            logger.warning("Skipping tile region outside the source image: %s", name)
            continue
        regions[name] = tuple(float(value) for value in rect)
    assets.load_from_dict({
        "id": "showcase_tiles",
        "type": "spritesheet",
        "image_path": "tile/tileset.png",
        "texture": config.get("texture", {}),
        "regions": regions,
        "config_path": config_path,
    })


class PlayerNode(pu.NodeUnit):
    def __init__(self) -> None:
        super().__init__("Player", tags={"player"})

        self.add_component(pu.builtin.SpriteRenderer(asset_key="player:run_0"))
        animation = self.add_component(
            pu.builtin.AnimationController(
                clip_name="player.run", group="player_animations"
            )
        )

        animation.play("player.run")


class AssetStatus(pu.NodeUnit):
    """Submit the asset example's status message in screen space."""

    def __init__(self) -> None:
        super().__init__(name="AssetStatus")
        self.layer = pu.Layer.UI

    def render_submit(self, renderer: pu.Renderer, context=None) -> None:
        self.one("@Text").render(
            "This is a test for assets. It doesn't do anything yet.",
            z=0,
            layer=pu.Layer.UI,
            pos=(0, 0),
            font_size=20,
            color=(0, 0, 0, 255),
        )


class TestScreen(pu.SceneUnit):
    def on_load(self) -> None:
        self.root.attach(AssetStatus())
        player = PlayerNode()
        self.root.attach(player)
        player.transform.set_position(200, 200)

        well_node = pu.NodeUnit("WellNode")
        well_node.add_component(pu.builtin.SpriteRenderer(asset_key="well"))
        self.root.attach(well_node)
        well_node.transform.set_position(100, 100)

        self.one("@Camera2D").teleport(player)
        self.one("@Camera2D").set_pivot(0.5, 0.5)


class TestAssetsApp(pu.App):
    def on_load(self) -> None:
        self.camera: pu.Camera2D = pu.Camera2D((320, 180), (0.0, 0.0))
        self.camera.setup(1280, 720)

        self.setup_logging("DEBUG", "./logs/test_assets.log")

        self.one("@Assets").load_folder("player/run")
        self.one("@Assets").load_asset("images/test.png", asset_id="test_texture")
        self.one("@Assets").load_asset("background/config.json")
        self.one("@Assets").load_asset(
            "images_with_json/config.json", asset_id="test_texture_with_json"
        )
        load_tiles(self.one("@Assets"))

        self.animations.load("player/animations.json")
        self.one("@SceneManager").push(TestScreen())
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        self.camera.update(self.window.unscaled_dt)
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((245, 245, 245, 255))
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all(camera=self.camera)
        self.window.end_drawing()


def main():
    script_dir = Path(__file__).parent
    app = pu.init(
        TestAssetsApp(),
        pu.AppConfig(
            "Test Assets App",
            assets_path=script_dir / "data",
            animation_path=script_dir / "data",
            window_height=720,
            window_width=1280,
            target_fps=60,
        ),
    )
    app.run()
