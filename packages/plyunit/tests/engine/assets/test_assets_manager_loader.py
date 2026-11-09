"""Loading, path containment, and configuration regression tests for Assets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asset_fakes import FakeGPU, FakeImages
from plyunit.backends.integrations.raylib.assets import Assets
from plyunit.backends.ports.assets import IAssets, IImageProcessor
from plyunit.backends.ports.handler import Texture2DHandle
from plyunit.utils.paths import resolve_config_resource, resolve_inside


def write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_asset_manager_conforms_to_ports(
    manager: Assets, images: FakeImages, gpu: FakeGPU
) -> None:
    assert isinstance(manager, IAssets)
    assert isinstance(images, IImageProcessor)
    manager.store_texture("asset", gpu.texture("asset", 8, 8))
    assert isinstance(manager["asset"], Texture2DHandle)
    view = manager.all_assets
    with pytest.raises(TypeError):
        view["other"] = manager["asset"]
    manager.unload_asset("asset")
    assert view == {}


def test_asset_manager_load_asset_from_json_and_image(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    image = tmp_path / "hero.png"
    image.touch()
    config = tmp_path / "hero.json"
    write_config(
        config, {"id": "hero", "image_path": "hero.png", "texture": {"wrap": "clamp"}}
    )
    manager.load_asset("hero.json")
    assert images.loaded == [image]
    assert manager["hero"].texture_id == "hero"
    assert manager.get_config_path_for("hero") == config
    standalone = tmp_path / "coin.png"
    standalone.touch()
    manager.load_asset("coin.png")
    assert images.loaded == [image, standalone]
    assert manager["coin"].source_rect == (0.0, 0.0, 100.0, 100.0)
    assert manager.get_config_path_for("coin") is None


def test_asset_manager_load_spritesheet(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    (tmp_path / "sheet.png").touch()
    config = tmp_path / "sheet.json"
    write_config(
        config,
        {
            "id": "sheet",
            "type": "spritesheet",
            "image_path": "sheet.png",
            "regions": {"tile": [0, 0, 16, 16]},
        },
    )
    manager.load_spritesheet("sheet.json")
    assert manager["tile"].raw_texture is manager["sheet"].raw_texture
    assert manager["tile"].parent_id == "sheet"
    assert manager.get_config_path_for("tile") == config


def test_nested_sidecar_preserves_relative_subdirectories(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    folder = tmp_path / "sprites"
    (folder / "frames").mkdir(parents=True)
    image = folder / "frames" / "sheet.png"
    image.touch()
    write_config(
        folder / "sheet.json", {"id": "sheet", "image_path": "frames/sheet.png"}
    )
    manager.load_asset("sprites/sheet.json")
    assert images.loaded == [image]


def test_asset_root_path_has_priority(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    (tmp_path / "sheet.png").touch()
    folder = tmp_path / "sprites"
    folder.mkdir()
    (folder / "sheet.png").touch()
    write_config(folder / "sheet.json", {"id": "sheet", "image_path": "sheet.png"})
    manager.load_asset("sprites/sheet.json")
    assert images.loaded == [tmp_path / "sheet.png"]


@pytest.mark.parametrize("method", ["load_asset", "load_spritesheet", "load_folder"])
def test_asset_manager_rejects_path_traversal(manager: Assets, method: str) -> None:
    with pytest.raises(ValueError, match="escapes base directory"):
        getattr(manager, method)("../outside")


def test_config_image_and_context_must_stay_inside_base(
    manager: Assets, tmp_path: Path
) -> None:
    (tmp_path / "hero.png").touch()
    with pytest.raises(ValueError, match="escapes base directory"):
        manager.load_from_dict({"id": "evil", "image_path": "../outside.png"})
    with pytest.raises(ValueError, match="escapes base directory"):
        manager.load_from_dict({
            "id": "evil",
            "image_path": "hero.png",
            "config_path": tmp_path.parent / "evil.json",
        })


def test_resolve_inside_normalizes_base(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    assert resolve_inside(folder / ".." / "data", "image.png") == folder / "image.png"
    with pytest.raises(ValueError, match="escapes"):
        resolve_inside(folder, tmp_path / "outside.png")


def test_sidecar_path_cannot_escape_or_discard_components(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "image.png").touch()
    context = folder / "sheet.json"
    missing = resolve_config_resource(tmp_path, "missing/image.png", context)
    assert missing == tmp_path / "missing" / "image.png"
    with pytest.raises(ValueError, match="escapes"):
        resolve_config_resource(tmp_path, "../image.png", context)


def test_symlink_escape_is_rejected(manager: Assets, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    outside.touch()
    link = tmp_path / "link.png"
    try:
        link.symlink_to(outside)
    except OSError:
        outside.unlink(missing_ok=True)
        pytest.skip("Windows symlink creation requires suitable privileges")
    try:
        with pytest.raises(ValueError, match="escapes"):
            manager.load_asset("link.png")
    finally:
        outside.unlink(missing_ok=True)


def test_load_from_dict_does_not_mutate_input(manager: Assets, tmp_path: Path) -> None:
    (tmp_path / "enemy.png").touch()
    data = {"id": "enemy", "image_path": "enemy.png", "texture": {}}
    manager.load_from_dict(data)
    assert data == {"id": "enemy", "image_path": "enemy.png", "texture": {}}
    assert manager["enemy"].texture_id == "enemy"
    with pytest.raises(FileNotFoundError):
        manager.load_from_dict({"id": "ghost", "image_path": "ghost.png"})


def test_load_folder_processes_configs_once(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    folder = tmp_path / "sprites"
    folder.mkdir()
    for name in ("hero.png", "coin.PNG"):
        (folder / name).touch()
    write_config(folder / "hero.json", {"id": "hero", "image_path": "hero.png"})
    write_config(folder / "animations.json", {"animations": {}})
    manager.load_folder("sprites")
    assert images.loaded == [folder / "hero.png", folder / "coin.PNG"]
    assert set(manager.all_assets) == {"hero", "coin"}
    with pytest.raises(FileNotFoundError):
        manager.load_folder("missing")


def test_load_folder_respects_extensions(manager: Assets, tmp_path: Path) -> None:
    (tmp_path / "hero.png").touch()
    (tmp_path / "icon.bmp").touch()
    manager.load_folder(".", allow_extensions=[".bmp"])
    assert set(manager.all_assets) == {"icon"}
    manager.clear_all()
    manager.load_folder(".", allow_extensions=[])
    assert manager.all_assets == {}


def test_missing_image_fails_before_decode(manager: Assets, images: FakeImages) -> None:
    with pytest.raises(FileNotFoundError):
        manager.load_asset("missing.png")
    assert images.loaded == []


def test_unload_region_does_not_free_parent(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 32, 32))
    manager._put(
        manager["sheet"].derive(
            texture_id="tile", parent_id="sheet", source_rect=(0.0, 0.0, 8.0, 8.0)
        )
    )
    manager.unload_asset("tile")
    manager.unload_asset("missing")
    assert manager.is_valid("sheet")
    assert gpu.unloaded == []


def test_destroy_unloads_each_owned_resource_once(
    manager: Assets, gpu: FakeGPU
) -> None:
    for name in ("hero", "coin"):
        manager.store_texture(name, gpu.texture(name, 8, 8))
    manager.destroy()
    manager.destroy()
    assert [raw.name for raw in gpu.unloaded] == ["hero", "coin"]
    assert manager.all_assets == {}
    assert manager._regions == {}
