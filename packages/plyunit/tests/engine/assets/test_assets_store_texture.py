"""Texture ownership, replacement, and bulk storage through dedicated handles."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from asset_fakes import FakeGPU
from plyunit.backends.integrations.raylib.assets import Assets
from plyunit.backends.integrations.raylib.handler import RenderTexture


def test_store_texture_registers_root_asset(manager: Assets, gpu: FakeGPU) -> None:
    texture = gpu.texture("rect_a", 32, 16)
    manager.store_texture("rect_a", texture)
    handle = manager.get_asset("rect_a")
    assert handle is not texture
    assert handle.raw_texture is texture.raw_texture
    assert handle.texture_id == handle.parent_id == "rect_a"
    assert handle.source_rect == (0.0, 0.0, 32.0, 16.0)
    assert manager["rect_a"] is handle
    assert texture.texture_id == ""


def test_store_texture_rejects_none(manager: Assets) -> None:
    with pytest.raises(ValueError, match="must not be None"):
        manager.store_texture("bad", None)


def test_store_texture_rejects_raw_struct(manager: Assets, gpu: FakeGPU) -> None:
    raw = gpu.texture("raw", 8, 8).raw_texture
    with pytest.raises(TypeError, match="Texture2D handle"):
        manager.store_texture("raw", raw)


def test_store_texture_overwrites_existing_id(manager: Assets, gpu: FakeGPU) -> None:
    old = gpu.texture("old", 8, 8)
    new = gpu.texture("new", 16, 16)
    manager.store_texture("shared", old)
    manager.store_texture("shared", new)
    assert manager.get_asset("shared").raw_texture is new.raw_texture
    assert gpu.unloaded == [old.raw_texture]


def test_store_same_texture_is_idempotent(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("shared", gpu.texture("shared", 8, 8))
    first = manager["shared"]
    wrapped_again = replace(first, raw_texture=replace(first.raw_texture))
    manager.store_texture("shared", wrapped_again)
    assert manager.is_valid("shared")
    assert gpu.unloaded == []
    manager.clear_all()
    assert len(gpu.unloaded) == 1


def test_same_gpu_resource_cannot_have_two_owners(
    manager: Assets, gpu: FakeGPU
) -> None:
    texture = gpu.texture("shared", 8, 8)
    manager.store_texture("first", texture)
    with pytest.raises(ValueError, match="already owned"):
        manager.store_texture(
            "second", replace(texture, raw_texture=replace(texture.raw_texture))
        )
    assert set(manager.all_assets) == {"first"}
    assert gpu.unloaded == []


def test_regions_cannot_transfer_parent_ownership(
    manager: Assets, gpu: FakeGPU
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 16, 16))
    region = manager["sheet"].derive(
        texture_id="tile", parent_id="sheet", source_rect=(0.0, 0.0, 8.0, 8.0)
    )
    with pytest.raises(ValueError, match="borrowed"):
        manager.store_texture("tile", region)
    assert manager.is_valid("sheet")
    assert gpu.unloaded == []
    promoted = region.derive(
        texture_id="promoted", parent_id="promoted", source_rect=region.source_rect
    )
    with pytest.raises(ValueError, match="borrowed"):
        manager.store_texture("promoted", promoted)


def test_render_target_attachment_is_borrowed(manager: Assets, gpu: FakeGPU) -> None:
    raw = gpu.texture("attachment", 8, 8).raw_texture
    target = RenderTexture(SimpleNamespace(texture=raw))
    with pytest.raises(ValueError, match="borrowed"):
        manager.store_texture("attachment", target.texture)
    assert not raw.unloaded


def test_store_textures_bulk(manager: Assets, gpu: FakeGPU) -> None:
    textures = {name: gpu.texture(name, 4, 4) for name in ("r1", "r2", "c1")}
    manager.store_textures(textures)
    for asset_id, texture in textures.items():
        assert manager[asset_id].raw_texture is texture.raw_texture


def test_store_textures_rejects_none_before_mutation(
    manager: Assets, gpu: FakeGPU
) -> None:
    with pytest.raises(ValueError, match="bad"):
        manager.store_textures({"good": gpu.texture("good", 4, 4), "bad": None})
    assert manager.all_assets == {}


def test_store_invalid_texture_preserves_old(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("asset", gpu.texture("old", 8, 8))
    old = manager["asset"]
    invalid = gpu.texture("invalid", 0, 0)
    invalid.raw_texture.valid = False
    with pytest.raises(ValueError, match="invalid"):
        manager.store_texture("asset", invalid)
    assert manager["asset"] is old
    assert gpu.unloaded == []


def test_stored_textures_are_atlas_packable(manager: Assets, gpu: FakeGPU) -> None:
    manager.store_texture("rect_a", gpu.texture("rect_a", 32, 16))
    manager.store_texture("rect_b", gpu.texture("rect_b", 16, 16))
    assert manager._collect_atlas_roots(["rect_a", "rect_b"]) == ["rect_a", "rect_b"]
    pages = manager.build_texture_atlas()
    assert pages == ["atlas"]
    page = manager["atlas"]
    assert manager["rect_a"].raw_texture is page.raw_texture
    assert manager["rect_b"].raw_texture is page.raw_texture
    assert [raw.name for raw in gpu.unloaded] == ["rect_a", "rect_b"]


def test_gpu_owner_checks_remain_linear_for_bulk_storage(
    manager: Assets, gpu: FakeGPU, monkeypatch: pytest.MonkeyPatch
) -> None:
    count = 200
    textures = {str(index): gpu.texture(str(index), 8, 8) for index in range(count)}
    texture_key = Mock(wraps=manager._texture_key)
    monkeypatch.setattr(manager, "_texture_key", texture_key)

    manager.store_textures(textures)

    assert len(manager.all_assets) == count
    assert texture_key.call_count <= count * 3
    assert manager._texture_owners == {
        texture.raw_texture.id: asset_id for asset_id, texture in textures.items()
    }


def test_owner_index_tracks_replacement_and_reused_native_ids(
    manager: Assets, gpu: FakeGPU
) -> None:
    old = gpu.texture("old", 8, 8)
    new = gpu.texture("new", 16, 16)
    old_id, new_id = old.raw_texture.id, new.raw_texture.id
    manager.store_texture("shared", old)
    manager.store_texture("shared", new)

    assert manager._texture_owners == {new_id: "shared"}
    reused = gpu.texture("reused", 8, 8)
    reused.raw_texture.id = old_id
    manager.store_texture("reused", reused)
    assert manager._texture_owners == {new_id: "shared", old_id: "reused"}

    manager.unload_asset("shared")
    assert manager._texture_owners == {old_id: "reused"}
    manager.clear_all()
    assert manager._texture_owners == {}


def test_owner_index_rejects_duplicate_without_replacing_an_existing_asset(
    manager: Assets, gpu: FakeGPU
) -> None:
    first = gpu.texture("first", 8, 8)
    second = gpu.texture("second", 8, 8)
    manager.store_texture("first", first)
    manager.store_texture("second", second)

    with pytest.raises(ValueError, match="already owned"):
        manager.store_texture("first", second)

    assert manager["first"].raw_texture is first.raw_texture
    assert manager["second"].raw_texture is second.raw_texture
    assert manager._texture_owners == {
        first.raw_texture.id: "first",
        second.raw_texture.id: "second",
    }
    assert gpu.unloaded == []


def test_owner_index_is_updated_after_atlas_repacking(
    manager: Assets, gpu: FakeGPU
) -> None:
    textures = {name: gpu.texture(name, 8, 8) for name in ("a", "b")}
    manager.store_textures(textures)
    manager.build_texture_atlas()
    page_id = manager["atlas"].raw_texture.id

    assert manager._texture_owners == {page_id: "atlas"}
    replacement = gpu.texture("reused", 8, 8)
    replacement.raw_texture.id = textures["a"].raw_texture.id
    manager.store_texture("a", replacement)
    assert manager._texture_owners == {
        page_id: "atlas",
        replacement.raw_texture.id: "a",
    }
    assert manager.is_valid("b")

    manager.unload_asset("atlas")
    assert manager._texture_owners == {replacement.raw_texture.id: "a"}
    assert set(manager.all_assets) == {"a"}
    manager.clear_all()
    assert manager._texture_owners == {}
