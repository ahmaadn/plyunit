"""Full-bake on_ready + O(1) render_submit + mutation API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from engine.tilemap._fakes import (
    FakeCanvas,
    make_assets,
    make_texture,
)

from plyunit._enums import TextureFilter
from plyunit.tilemap.map_data import ChunkRT, MapConfig, MapSettingsRT, TilesetRuntime
from plyunit.tilemap.tilemap import TileMapNode


@pytest.fixture(autouse=True)
def _canvas():
    canvas = FakeCanvas()
    yield canvas


def _make_node(canvas: FakeCanvas) -> TileMapNode:
    node = TileMapNode(name="tm")
    node.one = MagicMock(return_value=SimpleNamespace(canvas=canvas))
    node.tile_size = 16
    node.chunk_size = 2
    texture = make_texture("grass")
    assets = make_assets({"grass": texture})
    node.config = MapConfig(
        settings=MapSettingsRT(tile_size=(16, 16), chunk_size=2, encoding="array"),
        tilesets={1: TilesetRuntime(gid=1, asset_id="grass")},
        layers={
            "1": {"name": "Base", "render_mode": "auto", "y_sort_enabled": False},
            "2": {
                "name": "Props",
                "render_mode": "tiles",
                "y_sort_enabled": True,
            },
        },
        chunks={
            "0,0": ChunkRT(
                chunk_x=0,
                chunk_y=0,
                raw_layers={"1": [1, 0, 0, 0], "2": [0, 1, 0, 0]},
                gid_arrays={},
                decoded=False,
            ),
            "1,0": ChunkRT(
                chunk_x=1,
                chunk_y=0,
                raw_layers={"1": [1, 1, 0, 0]},
                gid_arrays={},
                decoded=False,
            ),
        },
    )
    node.one_or_none = MagicMock(
        side_effect=lambda query, **kwargs: assets if query == "@Assets" else None
    )
    return node


def test_on_ready_full_bakes_baked_layers_nearest_filter(
    _canvas: FakeCanvas,
) -> None:
    node = _make_node(_canvas)
    node.on_ready()

    # Layer "1" auto → baked for both chunks; layer "2" tiles → no bake.
    assert ("0,0", "1") in node._baked_render
    assert ("1,0", "1") in node._baked_render
    assert ("0,0", "2") not in node._baked_render

    mipmaps = [c for c in _canvas.calls if c[0] == "mipmap"]
    filters = [c for c in _canvas.calls if c[0] == "filter"]
    assert len(mipmaps) == 0
    assert len(filters) == 2
    assert all(c[2] is TextureFilter.NEAREST for c in filters)

    # gid_arrays decoded
    # pyrefly: ignore [missing-attribute]
    assert node.config.chunks["0,0"].decoded is True
    # pyrefly: ignore [missing-attribute]
    assert node.config.chunks["0,0"].gid_arrays["1"] == [1, 0, 0, 0]


def test_render_submit_does_not_bake(_canvas: FakeCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    loads_after_ready = sum(1 for c in _canvas.calls if c[0] == "load")
    mip_after_ready = sum(1 for c in _canvas.calls if c[0] == "mipmap")

    renderer = MagicMock()
    node.render_submit(renderer)

    loads_after_submit = sum(1 for c in _canvas.calls if c[0] == "load")
    mip_after_submit = sum(1 for c in _canvas.calls if c[0] == "mipmap")
    assert loads_after_submit == loads_after_ready
    assert mip_after_submit == mip_after_ready
    assert renderer.render_sprite.called


def test_set_tile_updates_without_rebake(_canvas: FakeCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    assert node.set_tile(16, 0, 5) is True
    assert node.get_gid_at(16, 0) == 5
    # No re-bake: still only the original baked entries
    assert len(node._baked_render) == 2


def test_fill_and_remove(_canvas: FakeCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    n = node.fill((0, 0, 16, 16), 7)
    assert n >= 1
    assert node.remove_tile(0, 0) is True


@pytest.mark.parametrize("layer_id", ["1", "3"])
def test_mutation_before_ready_does_not_skip_other_layers(
    _canvas: FakeCanvas, layer_id: str
) -> None:
    node = _make_node(_canvas)
    assert node.config is not None
    chunk = node.config.chunks["0,0"]
    node.config.settings.encoding = "csv"
    node.config.layers["2"].update(render_mode="baked", y_sort_enabled=False)
    chunk.raw_layers = {"1": "1,0,0,0", "2": "0,1,0,0"}

    assert node.set_tile(16, 0, 1, layer_id) is True
    assert chunk.decoded is False
    node.on_ready()

    assert chunk.decoded is True
    assert chunk.gid_arrays["2"] == [0, 1, 0, 0]
    assert chunk.gid_arrays[layer_id][1] == 1
    assert ("0,0", "1") in node._baked_render
    assert ("0,0", "2") in node._baked_render


@pytest.mark.parametrize(
    ("rect", "expected"),
    [
        ((0.0, 0.0, 0.25, 0.25), 1),
        ((15.75, 15.75, 0.5, 0.5), 4),
        ((15.5, 0.0, 0.5, 16.0), 1),
        ((16.0, 0.0, 16.0, 16.0), 1),
        ((0.0, 0.0, 0.0, 16.0), 0),
        ((0.0, 0.0, 16.0, -1.0), 0),
    ],
)
def test_fill_uses_half_open_fractional_bounds(
    _canvas: FakeCanvas, rect: tuple[float, float, float, float], expected: int
) -> None:
    node = _make_node(_canvas)

    assert node.fill(rect, 7) == expected
    assert node.fill(rect, 7) == 0
    assert _canvas.loads == []


def test_streaming_unload_retains_bakes_until_destroy(_canvas: FakeCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    targets = dict(node._baked_render)

    node._chunk_tile.unload_all()

    assert len(node._chunk_tile) == 0
    assert node._baked_render == targets
    assert _canvas.unloaded == []

    node.destroy()

    assert node._baked_render == {}
    assert len(_canvas.unloaded) == len(targets)
    assert all(
        any(target is unloaded for unloaded in _canvas.unloaded)
        for target in targets.values()
    )
