"""Tilemap baking and sprite submission use opaque backend handles."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from engine.tilemap._fakes import FakeCanvas, gid_entry, make_texture

from plyunit._enums import TextureFilter
from plyunit.backends.ports.renderer import ICanvas2D, IUnifiedBufferBatch
from plyunit.rendering.frame_buffer import FrameBuffer
from plyunit.rendering.renderer import Renderer
from plyunit.tilemap.map_data import ChunkRT, MapConfig
from plyunit.tilemap.tilemap import TileMapNode


def _make_node(canvas: FakeCanvas) -> tuple[TileMapNode, list[object]]:
    queries: list[object] = []

    def _one(ref, *args, **kwargs):
        queries.append(ref)
        return SimpleNamespace(canvas=canvas)

    node = TileMapNode(name="tm")
    node.one = MagicMock(side_effect=_one)
    node.one_or_none = MagicMock(return_value=None)
    node.tile_size = 16
    node.chunk_size = 2
    node._gid_map[1] = gid_entry(
        make_texture(
            "grass",
            256,
            128,
            parent_id="atlas",
            source_rect=(32.0, 16.0, 16.0, 16.0),
        )
    )
    return node, queries


def _chunk() -> ChunkRT:
    return ChunkRT(gid_arrays={"1": [1, 0, 0, 0]}, decoded=True)


def test_tilemap_uses_canvas_from_one_renderer_query() -> None:
    canvas = FakeCanvas()
    node, queries = _make_node(canvas)
    node._bake_chunk_layer("0,0", _chunk(), "1")
    target = node._baked_render[("0,0", "1")]
    texture = node._gid_map[1].texture

    assert queries == ["@Renderer"]
    assert canvas.calls == [
        ("load", 32, 32),
        ("begin", target),
        ("clear", (0, 0, 0, 0)),
        ("draw", texture, (32.0, 16.0, 16.0, 16.0), (0.0, 0.0, 16.0, 16.0)),
        ("end",),
        ("filter", target, TextureFilter.NEAREST),
    ]

    node._bake_chunk_layer("0,0", _chunk(), "1")
    assert queries == ["@Renderer"]
    assert len(canvas.loads) == 1
    node.destroy()
    assert canvas.unloaded == [target]


def test_baked_submission_passes_the_attachment_handle() -> None:
    canvas = FakeCanvas()
    node, _ = _make_node(canvas)
    node._bake_chunk_layer("0,0", _chunk(), "1")
    target = node._baked_render[("0,0", "1")]
    renderer = MagicMock()

    node._submit_baked_layer(renderer, "0,0", "1", -32, 64, 32)

    kwargs = renderer.render_sprite.call_args.kwargs
    assert kwargs["texture"] is target.texture
    assert kwargs["texture"].texture_id == "bake-1"
    assert kwargs["source"] == (0.0, 32.0, 32.0, -32.0)
    assert kwargs["dest"] == (-32.0, 64.0, 32.0, 32.0)


@pytest.mark.parametrize("failure", ["begin", "clear", "draw", "end", "filter"])
def test_failed_bake_releases_target_and_does_not_cache(failure: str) -> None:
    canvas = FakeCanvas()
    node, queries = _make_node(canvas)
    target = canvas.load_render_texture(32, 32)
    canvas.calls.clear()
    canvas.load_render_texture = MagicMock(return_value=target)
    method_name = {
        "begin": "begin_texture_mode",
        "clear": "clear_background",
        "draw": "draw_texture_region",
        "end": "end_texture_mode",
        "filter": "set_texture_filter",
    }[failure]
    original = getattr(canvas, method_name)

    def fail(*args, **kwargs):
        if failure == "end":
            original(*args, **kwargs)
        raise RuntimeError(f"{failure} failed")

    setattr(canvas, method_name, MagicMock(side_effect=fail))

    with pytest.raises(RuntimeError, match=f"{failure} failed"):
        node._bake_chunk_layer("0,0", _chunk(), "1")

    assert queries == ["@Renderer"]
    assert canvas.active_target is None
    assert canvas.unloaded == [target]
    assert node._baked_render == {}
    if failure in {"clear", "draw", "end", "filter"}:
        assert ("end",) in canvas.calls
    else:
        assert ("end",) not in canvas.calls


def test_destroy_releases_each_target_only_once() -> None:
    canvas = FakeCanvas()
    node, _ = _make_node(canvas)
    node._bake_chunk_layer("0,0", _chunk(), "1")
    target = node._baked_render[("0,0", "1")]

    node.destroy()
    node.destroy()

    assert canvas.unloaded == [target]
    assert node._baked_render == {}


def test_destroy_without_baked_render_skips_query() -> None:
    canvas = FakeCanvas()
    node, queries = _make_node(canvas)
    node.destroy()

    assert queries == []
    assert canvas.calls == []


def test_tilemap_leaves_native_id_conversion_to_renderer_adapter() -> None:
    canvas = FakeCanvas()
    node, _ = _make_node(canvas)
    chunk = ChunkRT(gid_arrays={"1": [1, 0, 0, 0], "2": [0, 1, 0, 0]}, decoded=True)
    node.config = MapConfig(chunks={"0,0": chunk})
    node._bake_chunk_layer("0,0", chunk, "1")
    attachment = node._baked_render[("0,0", "1")].texture
    region = node._gid_map[1].texture
    ubr = MagicMock(spec_set=IUnifiedBufferBatch)

    def texture_id(handle):
        if handle is attachment:
            return 61
        assert handle is region
        return 37

    ubr.texture_id.side_effect = texture_id
    frame = FrameBuffer(capacity=4)
    renderer = Renderer(
        canvas=MagicMock(spec_set=ICanvas2D, wraps=canvas),
        ubr=ubr,
        frame_buffer=frame,
    )

    node.render_submit(renderer)

    assert ubr.texture_id.call_args_list == [call(attachment), call(region)]
    assert frame.count == 2
    assert frame.tex_id[:2].tolist() == [61, 37]
    assert frame.uv_rect[0].tolist() == pytest.approx([0.0, 1.0, 1.0, 0.0])
    assert frame.uv_rect[1].tolist() == pytest.approx([0.125, 0.125, 0.1875, 0.25])
    assert frame.size_wh[:2].tolist() == [[32.0, 32.0], [16.0, 16.0]]
    ubr.init.assert_not_called()
    ubr.submit_frame.assert_not_called()
    node.destroy()
