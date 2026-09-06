"""TileMapNode bake uses the canvas from the Renderer (one query)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from plyunit.tilemap.tilemap import TileMapNode


class FakeCanvas:
    """Fake canvas that records render-texture calls, without a GPU."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def load_render_texture(self, width, height):
        self.calls.append(("load", width, height))
        return SimpleNamespace(id=1, w=width, h=height)

    def unload_render_texture(self, target):
        self.calls.append(("unload", target.id))

    def begin_texture_mode(self, target):
        self.calls.append(("begin", target.id))

    def end_texture_mode(self):
        self.calls.append(("end",))

    def clear_transparent(self):
        self.calls.append(("clear",))

    def draw_texture_region(self, texture, source, dest):
        self.calls.append(("draw", source, dest))

    def gen_mipmaps(self, target):
        self.calls.append(("mipmap", target.id))

    def set_texture_filter(self, target, filter_mode="trilinear"):
        self.calls.append(("filter", target.id, filter_mode))


def _make_node(canvas: FakeCanvas) -> tuple[TileMapNode, list[object]]:
    queries: list[object] = []

    def _one(ref, *args, **kwargs):
        queries.append(ref)
        return SimpleNamespace(canvas=canvas)

    node = TileMapNode(name="tm")
    node.one = MagicMock(side_effect=_one)
    node.tile_size = 16
    node.chunk_size = 2
    # pyrefly: ignore [unsupported-operation]
    node._gid_map[1] = SimpleNamespace(
        texture="tex",
        source_rect=(0.0, 0.0, 16.0, 16.0),
        asset_id="a",
        is_oversized=lambda tile_size: False
    )
    return node, queries


def test_tilemap_uses_canvas_from_renderer_query_one() -> None:
    canvas = FakeCanvas()
    node, queries = _make_node(canvas)
    # 2x2 chunk: one tile
    gid_array = [1, 0, 0, 0]
    node._bake_chunk_layer(
        # pyrefly: ignore [bad-argument-type]
        "0,0", SimpleNamespace(gid_arrays={"1": gid_array}), "1"
    )

    assert "@Renderer" in queries
    assert ("load", 32, 32) in canvas.calls
    assert ("begin", 1) in canvas.calls
    assert ("clear",) in canvas.calls
    assert ("draw", (0.0, 0.0, 16.0, 16.0), (0, 0, 16, 16)) in canvas.calls
    assert ("end",) in canvas.calls
    # Point filter keeps pixel tiles sharp (mipmaps no longer applied on bake).
    assert ("filter", 1, "point") in canvas.calls
    assert ("0,0", "1") in node._baked_render

    node.destroy()
    assert ("unload", 1) in canvas.calls


def test_destroy_without_baked_render_skips_query() -> None:
    canvas = FakeCanvas()
    node, queries = _make_node(canvas)
    node.destroy()
    assert "@Renderer" not in queries
    assert canvas.calls == []
