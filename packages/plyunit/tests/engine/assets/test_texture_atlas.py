"""Atlas packing, handle remapping, ownership, and failure regression tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from asset_fakes import FakeGPU, FakeImages
from plyunit.backends.integrations.raylib.assets import Assets
from plyunit.services.animations import AnimationClip, AnimationFrame, Animations
from plyunit.services.assets.atlas import pack_shelf


def inject_region(manager: Assets, parent: str, name: str, rect) -> None:
    manager._put(
        manager[parent].derive(
            texture_id=name, parent_id=parent, source_rect=tuple(float(v) for v in rect)
        )
    )
    manager._sheet_regions.setdefault(parent, set()).add(name)
    manager._region_sheets[name] = parent


def rects_are_disjoint(a, b, padding: float) -> bool:
    return (
        a[0] + a[2] + padding <= b[0]
        or b[0] + b[2] + padding <= a[0]
        or a[1] + a[3] + padding <= b[1]
        or b[1] + b[3] + padding <= a[1]
    )


def test_atlas_packs_roots_into_single_page(
    manager: Assets, gpu: FakeGPU, images: FakeImages
) -> None:
    manager.store_texture("hero", gpu.texture("hero", 64, 64))
    manager.store_texture("coin", gpu.texture("coin", 32, 32))
    pages = manager.build_texture_atlas()
    assert pages == ["atlas"]
    page = manager["atlas"]
    assert manager["hero"] is not page
    assert manager["coin"] is not page
    assert (
        manager["hero"].raw_texture is manager["coin"].raw_texture is page.raw_texture
    )
    assert manager["hero"].texture_id == "hero"
    assert manager["coin"].texture_id == "coin"
    assert (
        manager.get_region_parent("hero")
        == manager.get_region_parent("coin")
        == "atlas"
    )
    assert manager["hero"].source_rect[2:] == (64.0, 64.0)
    assert manager["coin"].source_rect[2:] == (32.0, 32.0)
    assert rects_are_disjoint(
        manager["hero"].source_rect, manager["coin"].source_rect, 2.0
    )
    assert page.source_rect == (0.0, 0.0, 98.0, 64.0)
    assert (images.created[0].width, images.created[0].height) == (98, 64)
    assert all(raw.unloaded for raw in images.created)
    assert [raw.name for raw in gpu.unloaded] == ["hero", "coin"]


def test_atlas_remaps_spritesheet_regions(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 64, 64))
    inject_region(manager, "sheet", "tile", (16, 16, 16, 16))
    manager.build_texture_atlas()
    assert manager["tile"].raw_texture is manager["atlas"].raw_texture
    assert manager["sheet"].source_rect == (0.0, 0.0, 64.0, 64.0)
    assert manager["tile"].source_rect == (16.0, 16.0, 16.0, 16.0)
    assert manager["tile"].parent_id == "atlas"
    assert manager._regions["atlas"] == {"sheet", "tile"}
    assert "sheet" not in manager._regions
    assert manager._sheet_regions["sheet"] == {"tile"}


def test_atlas_skips_oversized_assets(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("big", gpu.texture("big", 4096, 4096))
    manager.store_texture("coin", gpu.texture("coin", 32, 32))
    big = manager["big"]
    assert manager.build_texture_atlas(max_size=2048) == ["atlas"]
    assert manager["big"] is big
    assert not big.raw_texture.unloaded
    assert [raw.name for raw in gpu.unloaded] == ["coin"]


def test_atlas_creates_multiple_pages(manager: Assets, gpu: FakeGPU) -> None:
    for name in ("a", "b", "c"):
        manager.store_texture(name, gpu.texture(name, 100, 50))
    assert manager.build_texture_atlas(max_size=128) == ["atlas", "atlas_2"]
    assert (
        manager["a"].raw_texture
        is manager["b"].raw_texture
        is manager["atlas"].raw_texture
    )
    assert manager["c"].raw_texture is manager["atlas_2"].raw_texture
    assert [raw.name for raw in gpu.unloaded] == ["a", "b", "c"]


def test_atlas_explicit_ids_pack_subset(manager: Assets, gpu: FakeGPU) -> None:
    for name in ("hero", "coin"):
        manager.store_texture(name, gpu.texture(name, 32, 32))
    coin = manager["coin"]
    manager.build_texture_atlas(["hero"])
    assert manager["hero"].parent_id == "atlas"
    assert manager["coin"] is coin
    assert not coin.raw_texture.unloaded


def test_atlas_region_id_packs_parent_only_once(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 32, 32))
    inject_region(manager, "sheet", "tile", (0, 0, 16, 16))
    assert manager.build_texture_atlas(["tile", "sheet", "tile"]) == ["atlas"]
    assert [raw.name for raw in gpu.unloaded] == ["sheet"]


def test_atlas_unknown_id_raises(manager: Assets) -> None:
    with pytest.raises(KeyError, match="ghost"):
        manager.build_texture_atlas(["ghost"])


def test_empty_atlas_and_second_call(manager: Assets, gpu: FakeGPU) -> None:
    assert manager.build_texture_atlas() == []
    manager.store_texture("hero", gpu.texture("hero", 32, 32))
    assert manager.build_texture_atlas() == ["atlas"]
    assert manager.build_texture_atlas() == []
    assert manager.build_texture_atlas(["hero"]) == []
    assert len(gpu.unloaded) == 1


def test_atlas_page_ids_avoid_existing_and_reserved_collisions(
    manager: Assets, gpu: FakeGPU
) -> None:
    for name in ("atlas", "a", "b", "c"):
        manager.store_texture(name, gpu.texture(name, 100, 100))
    pages = manager.build_texture_atlas(["a", "b", "c"], max_size=128)
    assert len(set(pages)) == 3
    assert "atlas" not in pages
    assert manager["atlas"].parent_id == "atlas"


def test_atlas_remaps_animation_ids_and_concrete_handles(
    manager: Assets, gpu: FakeGPU
) -> None:
    manager.store_texture("tall", gpu.texture("tall", 64, 100))
    manager.store_texture("sheet", gpu.texture("sheet", 64, 64))
    inject_region(manager, "sheet", "tile", (16, 16, 16, 16))
    sheet = manager["sheet"]
    another_wrapper = replace(sheet, raw_texture=replace(sheet.raw_texture))
    animations = Animations()
    clip = AnimationClip(
        name="run",
        frames=[
            AnimationFrame(asset_id="tile", source_rect=(0, 0, 8, 8)),
            AnimationFrame(asset_id="tile"),
            AnimationFrame(asset_id="tall"),
            AnimationFrame(texture=another_wrapper, source_rect=(16, 16, 16, 16)),
            AnimationFrame(asset_id="sheet", texture=sheet, source_rect=(0, 0, 8, 8)),
        ],
    )
    animations.add_clip(clip)
    manager.build_texture_atlas(max_size=256)
    assert manager["sheet"].source_rect == (66.0, 0.0, 64.0, 64.0)
    assert clip.frames[0].source_rect == (66.0, 0.0, 8.0, 8.0)
    assert clip.frames[1].source_rect is None and clip.frames[2].source_rect is None
    assert clip.frames[3].texture.raw_texture is manager["atlas"].raw_texture
    assert clip.frames[3].texture.texture_id == "sheet"
    assert clip.frames[3].source_rect == (82.0, 16.0, 16.0, 16.0)
    assert clip.frames[4].texture.raw_texture is manager["atlas"].raw_texture
    assert clip.frames[4].source_rect == (66.0, 0.0, 8.0, 8.0)


def test_unload_packed_sheet_removes_its_regions_only(
    manager: Assets, gpu: FakeGPU
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 64, 64))
    manager.store_texture("coin", gpu.texture("coin", 32, 32))
    inject_region(manager, "sheet", "tile", (0, 0, 16, 16))
    manager.build_texture_atlas()
    gpu.unloaded.clear()
    manager.unload_asset("sheet")
    assert set(manager.all_assets) == {"atlas", "coin"}
    assert manager.is_valid("coin")
    assert gpu.unloaded == []
    assert manager._regions["atlas"] == {"coin"}
    assert manager._sheet_regions == {} and manager._region_sheets == {}


def test_replace_packed_sheet_does_not_leave_stale_frames(
    manager: Assets, gpu: FakeGPU
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 64, 64))
    manager.store_texture("coin", gpu.texture("coin", 32, 32))
    inject_region(manager, "sheet", "tile", (0, 0, 16, 16))
    manager.build_texture_atlas()
    gpu.unloaded.clear()
    replacement = gpu.texture("new-sheet", 32, 32)
    manager.store_texture("sheet", replacement)
    assert "tile" not in manager.all_assets
    assert manager["sheet"].raw_texture is replacement.raw_texture
    assert manager.is_valid("coin")
    assert gpu.unloaded == []


def test_atlas_destroy_unloads_each_page_once(manager: Assets, gpu: FakeGPU) -> None:
    for name in ("hero", "coin"):
        manager.store_texture(name, gpu.texture(name, 32, 32))
    manager.build_texture_atlas()
    gpu.unloaded.clear()
    page = manager["atlas"].raw_texture
    manager.destroy()
    assert gpu.unloaded == [page]
    assert manager.all_assets == {}
    assert manager._atlases == set()


def test_unloading_page_removes_every_region_and_config(
    manager: Assets, gpu: FakeGPU
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 32, 32))
    inject_region(manager, "sheet", "tile", (0, 0, 16, 16))
    manager._config_paths["tile"] = Path("sheet.json")
    manager.build_texture_atlas()
    manager.unload_asset("atlas")
    assert manager.all_assets == {}
    assert manager._config_paths == {}
    assert manager._sheet_regions == {} and manager._region_sheets == {}


def test_atlas_composition_failure_is_transactional(
    manager: Assets, gpu: FakeGPU, images: FakeImages
) -> None:
    for name in ("a", "b"):
        manager.store_texture(name, gpu.texture(name, 100, 100))
    original = dict(manager.all_assets)
    gpu.fail_upload_at = 2
    with pytest.raises(RuntimeError, match="upload failed"):
        manager.build_texture_atlas(max_size=128)
    assert dict(manager.all_assets) == original
    assert manager._atlases == set()
    assert all(not handle.raw_texture.unloaded for handle in original.values())
    assert len(gpu.unloaded) == 1
    assert all(image.unloaded for image in images.created)


def test_atlas_blit_failure_releases_temporary_images(
    manager: Assets, gpu: FakeGPU, images: FakeImages
) -> None:
    manager.store_texture("hero", gpu.texture("hero", 32, 32))
    original = manager["hero"]
    images.blit_error = True
    with pytest.raises(RuntimeError, match="blit failed"):
        manager.build_texture_atlas()
    assert manager["hero"] is original
    assert gpu.unloaded == []
    assert all(image.unloaded for image in images.created)


def test_render_passes_handle_and_region_rect(
    manager: Assets, gpu: FakeGPU, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager.store_texture("hero", gpu.texture("hero", 64, 64))
    inject_region(manager, "hero", "tile", (16, 16, 16, 16))
    renderer = SimpleNamespace(render_sprite=MagicMock())
    monkeypatch.setattr(manager, "one", lambda _: renderer)
    manager.render("tile")
    assert renderer.render_sprite.call_args.kwargs["texture"] is manager["tile"]
    assert renderer.render_sprite.call_args.kwargs["source"] == (16.0, 16.0, 16.0, 16.0)
    manager.build_texture_atlas()
    manager.render("tile", source=(0, 0, 8, 8))
    assert renderer.render_sprite.call_args.kwargs["texture"] is manager["tile"]
    assert renderer.render_sprite.call_args.kwargs["source"] == (0, 0, 8, 8)


@pytest.mark.parametrize("kwargs", [{"max_size": 0}, {"padding": -1}])
def test_packer_validation(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        pack_shelf([], **kwargs)


def test_shelf_packer_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        pack_shelf([("same", 8, 8), ("same", 8, 8)])


def test_shelf_packer_rectangles_stay_inside_pages() -> None:
    pages, placements = pack_shelf(
        [("a", 32, 16), ("b", 16, 16), ("c", 32, 32)], max_size=48, padding=2
    )
    assert set(placements) == {"a", "b", "c"}
    for placement in placements.values():
        page = pages[placement.page]
        assert placement.x + placement.width <= page.width <= 48
        assert placement.y + placement.height <= page.height <= 48
