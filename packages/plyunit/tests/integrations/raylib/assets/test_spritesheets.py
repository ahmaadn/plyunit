"""Spritesheet loading through raylib Assets and its dedicated Texture2D handles."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.backends.integrations.raylib.assets import Assets, ImageProcessor
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    monkeypatch.setattr(
        importlib.import_module("plyunit.core.units.unit"), "units", registry
    )
    return registry


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    module = importlib.import_module("plyunit.backends.integrations.raylib.assets")
    native = MagicMock()
    native.load_image.side_effect = lambda path: SimpleNamespace(
        width=64, height=32, format=7, data=b"pixels"
    )
    native.is_image_valid.return_value = True
    native.is_texture_valid.return_value = True
    native.load_texture_from_image.side_effect = lambda image: SimpleNamespace(
        id=native.load_texture_from_image.call_count,
        width=image.width,
        height=image.height,
        format=7,
    )
    monkeypatch.setattr(module, "pr", native)
    return native


@pytest.fixture
def manager(tmp_path: Path, native: MagicMock) -> Assets:
    return Assets(tmp_path, image_processor=ImageProcessor())


def write_config(tmp_path: Path, data: dict, name: str = "sheet.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_assets_load_spritesheet(
    manager: Assets, native: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "image.png").touch()
    config = write_config(
        tmp_path,
        {
            "id": "sheet",
            "image_path": "image.png",
            "texture": {"filter": "nearest"},
            "regions": {"left": [0, 0, 32, 32], "right": [32, 0, 32, 32]},
        },
    )
    manager.load_spritesheet(str(config))
    assert manager["left"].raw_texture is manager["sheet"].raw_texture
    assert manager["left"].parent_id == "sheet"
    assert manager["left"].source_rect == (0.0, 0.0, 32.0, 32.0)
    assert manager.get_config_path_for("left") == config
    native.load_texture_from_image.assert_called_once()
    native.unload_image.assert_called_once()


def test_spritesheet_does_not_load_embedded_animations(
    manager: Assets, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "image.png").touch()
    config = write_config(
        tmp_path,
        {
            "id": "sheet",
            "image_path": "image.png",
            "regions": {},
            "animations": {"run": {"frames": []}},
        },
    )
    lookup = MagicMock()
    monkeypatch.setattr(manager, "one_or_none", lookup)
    manager.load_spritesheet(str(config))
    lookup.assert_not_called()


def test_spritesheet_missing_image_path(manager: Assets, tmp_path: Path) -> None:
    config = write_config(tmp_path, {"id": "sheet"})
    with pytest.raises(ValueError, match="image_path is required"):
        manager.load_spritesheet(str(config))


def test_spritesheet_missing_image(manager: Assets, tmp_path: Path) -> None:
    config = write_config(tmp_path, {"id": "sheet", "image_path": "missing.png"})
    with pytest.raises(FileNotFoundError):
        manager.load_spritesheet(str(config))


@pytest.mark.parametrize(
    "config_id, override, expected",
    [
        (None, None, "sheet"),
        ("configured", None, "configured"),
        ("configured", "override", "override"),
    ],
)
def test_spritesheet_id_resolution(
    manager: Assets,
    tmp_path: Path,
    config_id: str | None,
    override: str | None,
    expected: str,
) -> None:
    (tmp_path / "image.png").touch()
    data = {"image_path": "image.png", "regions": {}}
    if config_id is not None:
        data["id"] = config_id
    config = write_config(tmp_path, data)
    manager.load_spritesheet(str(config), asset_id=override)
    assert set(manager.all_assets) == {expected}
    assert manager[expected].texture_id == manager[expected].parent_id == expected


@pytest.mark.parametrize(
    "regions",
    [
        {"bad": [0, 0, 32]},
        {"bad": [0, 0, float("nan"), 8]},
        {"bad": [0, 0, 65, 8]},
        {"bad": [-1, 0, 8, 8]},
        {"bad": [0, 0, 0, 8]},
        {"sheet": [0, 0, 8, 8]},
        [{"name": "dup", "rect": [0, 0, 8, 8]}, {"name": "dup", "rect": [8, 0, 8, 8]}],
        [{"name": "missing"}],
        "invalid-container",
    ],
)
def test_invalid_regions_do_not_replace_or_allocate(
    manager: Assets, native: MagicMock, tmp_path: Path, regions
) -> None:
    (tmp_path / "image.png").touch()
    config = write_config(
        tmp_path,
        {"id": "sheet", "image_path": "image.png", "regions": {"old": [0, 0, 8, 8]}},
    )
    manager.load_spritesheet(str(config))
    old = manager["sheet"]
    native.load_texture_from_image.reset_mock()
    native.unload_texture.reset_mock()
    write_config(
        tmp_path, {"id": "sheet", "image_path": "image.png", "regions": regions}
    )
    with pytest.raises(ValueError):
        manager.load_spritesheet(str(config))
    assert manager["sheet"] is old
    assert "old" in manager.all_assets
    native.load_texture_from_image.assert_not_called()
    native.unload_texture.assert_not_called()


def test_region_name_cannot_overwrite_an_unrelated_owner(
    manager: Assets, native: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "image.png").touch()
    manager.load_asset("image.png", asset_id="owned")
    owner = manager["owned"]
    config = write_config(
        tmp_path,
        {"id": "sheet", "image_path": "image.png", "regions": {"owned": [0, 0, 8, 8]}},
    )
    with pytest.raises(ValueError, match="already in use"):
        manager.load_spritesheet(str(config))
    assert manager["owned"] is owner
    assert "sheet" not in manager.all_assets


def test_reloading_sheet_removes_old_frames(
    manager: Assets, native: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "image.png").touch()
    config = write_config(
        tmp_path,
        {"id": "sheet", "image_path": "image.png", "regions": {"old": [0, 0, 8, 8]}},
    )
    manager.load_spritesheet(str(config))
    old_raw = manager["sheet"].raw_texture
    write_config(
        tmp_path,
        {
            "id": "sheet",
            "image_path": "image.png",
            "regions": [{"name": "new", "rect": [8, 0, 8, 8]}],
        },
    )
    manager.load_spritesheet(str(config))
    assert set(manager.all_assets) == {"sheet", "new"}
    assert manager["new"].raw_texture is manager["sheet"].raw_texture
    native.unload_texture.assert_called_once_with(old_raw)
