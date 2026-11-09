"""Tests for oversized tile placement at runtime in :class:`TileMapNode`.

Invariants enforced:

1. A 100x90 image on a 16x16 grid is **not** forced to 16x16.
2. Its anchor is the **bottom-left** corner of the cell, not the center or
   top-left.
3. Oversized tiles are not baked into per-chunk ``RenderTexture``s, because
   an RT is exactly one chunk in size and would clip the overhanging part.

All GPU access is replaced with fakes, so the tests run without a
window/raylib.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from engine.tilemap._fakes import FakeCanvas, make_assets, make_texture

from plyunit.tilemap.tilemap import TileMapNode, parse_map_config

TILE = 16
CHUNK = 2
BIG_W, BIG_H = 100.0, 90.0


def make_node(sizes: dict[str, tuple[float, float]], layers: dict) -> TileMapNode:
    """Build a node with region handles and layer metadata.

    Args:
        sizes: Logical asset IDs mapped to each region's native size.
        layers: Metadata for the map's layers.

    Returns:
        An unready tilemap using a headless asset port and canvas.
    """
    regions = {
        alias: make_texture(
            alias,
            256,
            128,
            parent_id="sheet",
            source_rect=(32.0, 16.0, w, h),
        )
        for alias, (w, h) in sizes.items()
    }
    assets = make_assets(regions)
    canvas = FakeCanvas()

    def _resolve(query, *args, **kwargs):
        if query == "@Renderer":
            return SimpleNamespace(canvas=canvas)
        if query == "@Assets":
            return assets
        return None

    node = TileMapNode(name="tm")
    node.one_or_none = MagicMock(side_effect=_resolve)
    node.one = MagicMock(side_effect=_resolve)
    node._test_canvas = canvas

    tilesets = {
        str(i): {"gid": i, "asset_id": alias} for i, alias in enumerate(sizes, start=1)
    }
    node.config = parse_map_config({
        "settings": {"tile_size": [TILE, TILE], "chunk_size": CHUNK},
        "tilesets": tilesets,
        "layers": layers,
        # Cell (1,1) occupies x=16..32 and y=16..32.
        "chunks": {"0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [0, 0, 0, 1]}}},
    })
    node.tile_size = TILE
    node.chunk_size = CHUNK
    return node


def submitted_tiles(node: TileMapNode) -> list[dict]:
    """Collect world-space sprite submissions without a camera.

    Args:
        node: Ready tilemap to render.

    Returns:
        Keyword arguments for each sprite submission.
    """
    queue = MagicMock()
    node.one_or_none = MagicMock(return_value=None)
    node.render_submit(queue)
    return [kw for _, kw in queue.render_sprite.call_args_list]


@pytest.fixture
def tiles_layer() -> dict:
    return {"1": {"name": "Props", "render_mode": "tiles"}}


@pytest.fixture
def baked_layer() -> dict:
    return {"1": {"name": "Base", "render_mode": "baked"}}


class TestTilesModeNativeSize:
    """``tiles`` mode: native size is preserved."""

    def test_keeps_native_size(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        dest = submitted_tiles(node)[0]["dest"]
        assert dest[2:] == (BIG_W, BIG_H)

    def test_not_squashed_to_tile_size(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        dest = submitted_tiles(node)[0]["dest"]
        assert dest[2] != float(TILE)
        assert dest[3] != float(TILE)


class TestTilesModeBottomLeftAnchor:
    """``tiles`` mode: anchored at the cell's bottom-left corner."""

    def test_exact_rect(self, tiles_layer) -> None:
        # Cell (1,1): x 16..32, y 16..32. The 100x90 image stands on the
        # cell floor, so y = 32 - 90 = -58.
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        assert submitted_tiles(node)[0]["dest"] == (16.0, -58.0, BIG_W, BIG_H)

    def test_bottom_edge_on_cell_bottom(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        _, y, _, h = submitted_tiles(node)[0]["dest"]
        assert y + h == float((1 + 1) * TILE)

    def test_left_edge_on_cell_left(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        x = submitted_tiles(node)[0]["dest"][0]
        assert x == float(1 * TILE)

    def test_grows_upward_not_downward(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        y = submitted_tiles(node)[0]["dest"][1]
        assert y < float(1 * TILE)

    def test_not_top_left(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        y = submitted_tiles(node)[0]["dest"][1]
        assert y != float(1 * TILE)

    def test_not_centered(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        x, y, w, h = submitted_tiles(node)[0]["dest"]
        cell_center = (1 * TILE + TILE / 2.0, 1 * TILE + TILE / 2.0)
        assert (x + w / 2.0, y + h / 2.0) != cell_center

    def test_cell_sized_tile_unchanged(self, tiles_layer) -> None:
        """A cell-sized region aligns with its grid cell."""
        node = make_node({"grass": (16.0, 16.0)}, tiles_layer)
        node.on_ready()
        assert submitted_tiles(node)[0]["dest"] == (16.0, 16.0, 16.0, 16.0)


class TestBakedModeRoutesOversizedOut:
    """``baked`` mode: oversized tiles must not enter the chunk RT."""

    def test_not_drawn_into_render_texture(self, baked_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, baked_layer)
        node.on_ready()
        assert node._test_canvas.draws == []

    def test_no_render_texture_allocated(self, baked_layer) -> None:
        """A layer containing only oversized tiles needs no RT."""
        node = make_node({"tree": (BIG_W, BIG_H)}, baked_layer)
        node.on_ready()
        assert node._test_canvas.loads == []

    def test_submitted_as_world_space_tile(self, baked_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, baked_layer)
        node.on_ready()
        tiles = submitted_tiles(node)
        assert len(tiles) == 1
        assert tiles[0]["dest"] == (16.0, -58.0, BIG_W, BIG_H)

    def test_cell_sized_tile_still_baked(self, baked_layer) -> None:
        node = make_node({"grass": (16.0, 16.0)}, baked_layer)
        node.on_ready()
        assert node._test_canvas.loads == [(CHUNK * TILE, CHUNK * TILE)]
        assert len(node._test_canvas.draws) == 1

    def test_baked_dest_rect_unchanged(self, baked_layer) -> None:
        node = make_node({"grass": (16.0, 16.0)}, baked_layer)
        node.on_ready()
        _, _, dest = node._test_canvas.draws[0]
        assert tuple(float(v) for v in dest) == (16.0, 16.0, 16.0, 16.0)


class TestAutoModeBaseLayer:
    """A base layer without an explicit ``render_mode`` still complies."""

    def test_auto_base_layer_oversized_not_squashed(self) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, {"1": {"name": "Base"}})
        node.on_ready()
        assert node._test_canvas.draws == []
        assert submitted_tiles(node)[0]["dest"] == (16.0, -58.0, BIG_W, BIG_H)


class TestOverhangBookkeeping:
    def test_overhang_tracked(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        assert node._max_overhang == (BIG_W - TILE, BIG_H - TILE)

    def test_no_overhang_for_cell_sized(self, tiles_layer) -> None:
        node = make_node({"grass": (16.0, 16.0)}, tiles_layer)
        node.on_ready()
        assert node._max_overhang == (0.0, 0.0)

    def test_render_bounds_cover_overhang(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        x, y, w, h = node.get_render_bounds()
        span = float(CHUNK * TILE)
        # Overhang upward raises the top edge; rightward overhang adds width.
        assert y == -(BIG_H - TILE)
        assert x == 0.0
        assert w == span + (BIG_W - TILE)
        assert h == span + (BIG_H - TILE)

    def test_render_bounds_unchanged_without_oversized(self, tiles_layer) -> None:
        node = make_node({"grass": (16.0, 16.0)}, tiles_layer)
        node.on_ready()
        span = float(CHUNK * TILE)
        assert node.get_render_bounds() == (0.0, 0.0, span, span)


class TestGidEntryFlag:
    def test_oversized_flag_set(self, tiles_layer) -> None:
        node = make_node({"tree": (BIG_W, BIG_H)}, tiles_layer)
        node.on_ready()
        assert node._gid_map[1].oversized is True

    def test_flag_clear_for_cell_sized(self, tiles_layer) -> None:
        node = make_node({"grass": (16.0, 16.0)}, tiles_layer)
        node.on_ready()
        assert node._gid_map[1].oversized is False


def test_mixed_baked_layer_submits_opaque_oversized_handle(baked_layer) -> None:
    node = make_node({"grass": (16.0, 16.0), "tree": (BIG_W, BIG_H)}, baked_layer)
    assert node.config is not None
    node.config.chunks["0,0"].raw_layers["1"] = [1, 0, 0, 2]
    node.on_ready()
    grass = node._gid_map[1].texture
    tree = node._gid_map[2].texture
    target = node._baked_render[("0,0", "1")]

    tiles = submitted_tiles(node)

    assert len(node._test_canvas.draws) == 1
    assert node._test_canvas.draws[0][0] is grass
    assert len(tiles) == 2
    assert tiles[0]["texture"] is target.texture
    assert tiles[1]["texture"] is tree
    assert tiles[1]["source"] == tree.source_rect
    assert tiles[1]["dest"] == (16.0, -58.0, BIG_W, BIG_H)
    assert tiles[1]["z"] == tiles[0]["z"] + 1


@pytest.mark.parametrize("render_mode", ["tiles", "baked"])
@pytest.mark.parametrize("view", [(96.0, 0.0, 112.0, 16.0), (16.0, -64.0, 32.0, -48.0)])
def test_overhang_keeps_offscreen_owning_chunk_visible(
    render_mode: str, view: tuple[float, float, float, float]
) -> None:
    node = make_node({"tree": (BIG_W, BIG_H)}, {"1": {"render_mode": render_mode}})
    node.margin_chunks = 0
    node.on_ready()
    camera = MagicMock()
    camera.get_view_rect.return_value = view
    node.one_or_none = MagicMock(
        side_effect=lambda query, **kwargs: camera if query == "@Camera2D" else None
    )
    renderer = MagicMock()

    assert node._visible_chunk_keys() == {"0,0"}
    node.render_submit(renderer)

    renderer.render_sprite.assert_called_once()
    assert (
        renderer.render_sprite.call_args.kwargs["texture"] is node._gid_map[1].texture
    )
    assert node._test_canvas.loads == []
