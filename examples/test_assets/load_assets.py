"""Load the asset showcase's valid regions without changing editor files."""

from __future__ import annotations

import json
import logging

from plyunit.backends.ports.assets import IAssets

logger = logging.getLogger(__name__)


def load_tiles(assets: IAssets) -> None:
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
