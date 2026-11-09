"""Regressions for tilemap asset-handle resolution and ownership boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from engine.tilemap._fakes import FakeCanvas, make_assets, make_texture

from plyunit.backends.ports.handler import RenderTextureHandle, Texture2DHandle
from plyunit.tilemap.map_data import ChunkRT, MapConfig, MapSettingsRT, TilesetRuntime
from plyunit.tilemap.tilemap import TileMapNode


def _make_node(textures) -> tuple[TileMapNode, MagicMock, FakeCanvas]:
    assets = make_assets(textures)
    canvas = FakeCanvas()
    node = TileMapNode()
    node.tile_size = 16
    node.chunk_size = 2
    node.config = MapConfig(
        settings=MapSettingsRT(tile_size=(16, 16), chunk_size=2),
        tilesets={1: TilesetRuntime(gid=1, asset_id="tile")},
        layers={"1": {"render_mode": "tiles"}},
        chunks={"0,0": ChunkRT(raw_layers={"1": [1, 0, 0, 0]})},
    )
    node.one = MagicMock(return_value=SimpleNamespace(canvas=canvas))
    node.one_or_none = MagicMock(
        side_effect=lambda query, **kwargs: assets if query == "@Assets" else None
    )
    return node, assets, canvas


def test_region_handle_and_logical_id_reach_sprite_submission_unchanged() -> None:
    texture = make_texture(
        "tile", 512, 256, parent_id="atlas", source_rect=(128.0, 64.0, 16.0, 8.0)
    )
    node, assets, canvas = _make_node({"tile": texture})
    node.on_ready()
    renderer = MagicMock()

    node.render_submit(renderer)

    assets.get_asset.assert_called_once_with("tile")
    entry = node._gid_map[1]
    assert entry.texture is texture
    assert entry.oversized is False
    assert node._max_overhang == (0.0, 0.0)
    kwargs = renderer.render_sprite.call_args.kwargs
    assert kwargs["texture"] is texture
    assert kwargs["texture"].texture_id == "tile"
    assert kwargs["texture"].parent_id == "atlas"
    assert kwargs["source"] == (128.0, 64.0, 16.0, 8.0)
    assert kwargs["dest"] == (0.0, 8.0, 16.0, 8.0)
    assert canvas.loads == []


def test_refresh_replaces_repacked_handle_and_resets_overhang() -> None:
    original = make_texture("tile", 100, 90)
    textures = {"tile": original}
    node, assets, _ = _make_node(textures)
    node.on_ready()
    assert node._max_overhang == (84.0, 74.0)
    replacement = make_texture(
        "tile", 512, 256, parent_id="new-atlas", source_rect=(64.0, 32.0, 16.0, 16.0)
    )
    textures["tile"] = replacement

    node._resolve_gid_map()
    renderer = MagicMock()
    node.render_submit(renderer)

    assert assets.get_asset.call_count == 2
    assert node._gid_map[1].texture is replacement
    assert node._max_overhang == (0.0, 0.0)
    kwargs = renderer.render_sprite.call_args.kwargs
    assert kwargs["texture"] is replacement
    assert kwargs["source"] == replacement.source_rect
    assert kwargs["dest"] == (0.0, 0.0, 16.0, 16.0)


def test_refresh_discards_missing_assets_without_dropping_valid_ones(caplog) -> None:
    textures = {"tile": make_texture("tile", 100, 90)}
    node, _, _ = _make_node(textures)
    node.on_ready()
    assert node.config is not None
    other = make_texture("other")
    textures["other"] = other
    node.config.tilesets[2] = TilesetRuntime(gid=2, asset_id="other")
    del textures["tile"]

    node._resolve_gid_map()

    assert set(node._gid_map) == {2}
    assert node._gid_map[2].texture is other
    assert node._max_overhang == (0.0, 0.0)
    assert "tile" in caplog.text


@pytest.mark.parametrize("missing", ["config", "assets", "tileset"])
def test_refresh_clears_stale_entries_when_source_disappears(missing: str) -> None:
    node, _, _ = _make_node({"tile": make_texture("tile", 100, 90)})
    node.on_ready()
    assert node._gid_map
    if missing == "config":
        node.config = None
    elif missing == "assets":
        node.one_or_none = MagicMock(return_value=None)
    else:
        assert node.config is not None
        node.config.tilesets.clear()

    node._resolve_gid_map()

    assert node._gid_map == {}
    assert node._max_overhang == (0.0, 0.0)


def test_asset_resolution_falls_back_to_mixed_scope() -> None:
    texture = make_texture("tile")
    node, assets, _ = _make_node({"tile": texture})
    node.one_or_none = MagicMock(side_effect=[None, assets])

    node._resolve_gid_map()

    assert node.one_or_none.call_args_list == [
        call("@Assets", scope="global"),
        call("@Assets"),
    ]
    assert node._gid_map[1].texture is texture


def test_failed_asset_service_does_not_leave_borrowed_handles_cached() -> None:
    node, assets, _ = _make_node({"tile": make_texture("tile")})
    node.on_ready()
    assets.get_asset.side_effect = RuntimeError("cache unavailable")

    with pytest.raises(RuntimeError, match="cache unavailable"):
        node._resolve_gid_map()

    assert node._gid_map == {}
    assert node._max_overhang == (0.0, 0.0)


def test_destroy_unloads_only_owned_render_targets() -> None:
    texture = make_texture("tile")
    node, assets, canvas = _make_node({"tile": texture})
    assert node.config is not None
    node.config.layers["1"]["render_mode"] = "baked"
    node.on_ready()
    target = node._baked_render[("0,0", "1")]
    assets.reset_mock()

    assert isinstance(texture, Texture2DHandle)
    assert isinstance(target, RenderTextureHandle)
    node.destroy()

    assert canvas.unloaded == [target]
    assert assets.mock_calls == []
