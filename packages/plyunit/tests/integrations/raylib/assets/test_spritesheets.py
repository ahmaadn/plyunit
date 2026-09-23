import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plyunit.assets.animations import Animations
from plyunit.assets.assets import Assets


@pytest.fixture
def mock_assets(tmp_path):
    assets = MagicMock(spec=Assets)
    assets._loader = MagicMock()
    assets._asset_base_path = tmp_path
    assets._resolve_under_base.side_effect = (
        lambda x: Path(x) if Path(x).is_absolute() else tmp_path / x
    )
    assets.unit = MagicMock()
    assets._register_region = MagicMock()
    assets._regions = {}
    assets._configs = {}

    # Bind the real methods to the mock object
    assets.load_spritesheet = Assets.load_spritesheet.__get__(assets)
    assets.load_from_dict = Assets.load_from_dict.__get__(assets)
    assets._resolve_config_image_path = Assets._resolve_config_image_path.__get__(assets)
    return assets


@pytest.fixture
def mock_animations():
    return MagicMock(spec=Animations)


def test_assets_load_spritesheet(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    mock_texture = MagicMock(width=64, height=32)

    config = {
        "id": "test_sheet",
        "image_path": "test_image.png",
        "texture": {"filter": "nearest"},
        "regions": {
            "region_1": [0, 0, 32, 32],
            "region_2": [32, 0, 32, 32]
        }
    }

    # Create fake image file
    image_file = tmp_path / "test_image.png"
    image_file.touch()

    config_file = tmp_path / "test_sheet.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    # Mock methods
    mock_assets._loader.load_texture_from_dict.return_value = mock_texture

    # Need to simulate what get_source_rect returns after _register_region is called
    regions_store = {}
    def fake_register_region(alias, t_data):
        regions_store[alias] = t_data
    mock_assets._register_region.side_effect = fake_register_region

    # Call loader
    mock_assets.load_spritesheet(str(config_file), asset_id="test_sheet")

    # Verify texture loaded
    mock_assets._loader.load_texture_from_dict.assert_called_once()
    mock_assets._cache_texture.assert_called_once_with("test_sheet", mock_texture)

    # Verify regions registered
    assert "region_1" in regions_store
    assert regions_store["region_1"].parent_id == "test_sheet"
    assert regions_store["region_1"].source_rect == (0.0, 0.0, 32.0, 32.0)

    # Animations are no longer part of the spritesheet config.
    mock_animations.load_animation.assert_not_called()


def test_assets_load_spritesheet_missing_image_path(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {"id": "test"}
    config_file = tmp_path / "test.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    with pytest.raises(ValueError, match="image_path is required"):
        mock_assets.load_spritesheet(str(config_file), asset_id="test")


def test_assets_load_spritesheet_image_not_found(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {
        "id": "test",
        "image_path": "missing.png"
    }
    config_file = tmp_path / "test.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    with pytest.raises(FileNotFoundError):
        mock_assets.load_spritesheet(str(config_file), asset_id="test")


def test_assets_load_spritesheet_invalid_region(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {
        "id": "test",
        "image_path": "test.png",
        "regions": {
            "reg1": [0, 0, 32] # Invalid
        }
    }
    image_file = tmp_path / "test.png"
    image_file.touch()

    config_file = tmp_path / "test.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    with pytest.raises(ValueError, match="must have 4 values for rect"):
        mock_assets.load_spritesheet(str(config_file), asset_id="test")


def test_assets_load_spritesheet_fallback_sheet_id(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {
        "image_path": "test.png"
    }
    image_file = tmp_path / "test.png"
    image_file.touch()

    config_file = tmp_path / "my_sheet.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    mock_assets.load_spritesheet(str(config_file), asset_id=None)

    mock_assets._cache_texture.assert_called_once_with("my_sheet", mock_assets._loader.load_texture_from_dict.return_value)


def test_assets_load_spritesheet_only_one_argument(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {
        "id": "config_sheet_id",
        "image_path": "test.png"
    }
    image_file = tmp_path / "test.png"
    image_file.touch()

    config_file = tmp_path / "my_sheet.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    # Call with only one argument (config_path)
    mock_assets.load_spritesheet(str(config_file))

    mock_assets._cache_texture.assert_called_once_with("config_sheet_id", mock_assets._loader.load_texture_from_dict.return_value)





def test_assets_load_spritesheet_override_id(mock_assets, mock_animations, tmp_path):
    mock_assets.one.return_value = mock_animations
    config = {
        "id": "config_sheet_id",
        "image_path": "test.png"
    }
    image_file = tmp_path / "test.png"
    image_file.touch()

    config_file = tmp_path / "my_sheet.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    # Call with override parameter asset_id
    mock_assets.load_spritesheet(str(config_file), asset_id="override_sheet_id")

    mock_assets._cache_texture.assert_called_once_with("override_sheet_id", mock_assets._loader.load_texture_from_dict.return_value)
