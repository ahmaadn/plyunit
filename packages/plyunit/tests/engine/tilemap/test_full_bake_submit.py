"""Full-bake on_ready + O(1) render_submit + mutation API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plyunit.tilemap.map_data import ChunkRT, MapConfig, MapSettingsRT
from plyunit.tilemap.tilemap import TileMapNode


class RecordingCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._n = 0

    def load_render_texture(self, w, h):
        self._n += 1
        self.calls.append(("load", w, h))
        return SimpleNamespace(
            id=self._n,
            texture=SimpleNamespace(width=w, height=h),
        )

    def unload_render_texture(self, target):
        self.calls.append(("unload", getattr(target, "id", target)))

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


@pytest.fixture(autouse=True)
def _canvas():
    canvas = RecordingCanvas()
    yield canvas


def _make_node(canvas: RecordingCanvas) -> TileMapNode:
    node = TileMapNode(name="tm")
    node.one = MagicMock(return_value=SimpleNamespace(canvas=canvas))
    node.tile_size = 16
    node.chunk_size = 2
    # pyrefly: ignore [unsupported-operation]
    node._gid_map[1] = SimpleNamespace(
        texture="tex",
        source_rect=(0.0, 0.0, 16.0, 16.0),
        asset_id="a",
        is_oversized=lambda tile_size: False
    )
    node.config = MapConfig(
        settings=MapSettingsRT(tile_size=(16, 16), chunk_size=2, encoding="array"),
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
    node.one_or_none = MagicMock(return_value=None)
    return node


def test_on_ready_full_bakes_baked_layers_point_filter(
    _canvas: RecordingCanvas,
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
    assert all(c[2] == "point" for c in filters)

    # gid_arrays decoded
    # pyrefly: ignore [missing-attribute]
    assert node.config.chunks["0,0"].decoded is True
    # pyrefly: ignore [missing-attribute]
    assert node.config.chunks["0,0"].gid_arrays["1"] == [1, 0, 0, 0]


def test_render_submit_does_not_bake(_canvas: RecordingCanvas) -> None:
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


def test_set_tile_updates_without_rebake(_canvas: RecordingCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    assert node.set_tile(16, 0, 5) is True
    assert node.get_gid_at(16, 0) == 5
    # No re-bake: still only the original baked entries
    assert len(node._baked_render) == 2


def test_fill_and_remove(_canvas: RecordingCanvas) -> None:
    node = _make_node(_canvas)
    node.on_ready()
    n = node.fill((0, 0, 16, 16), 7)
    assert n >= 1
    assert node.remove_tile(0, 0) is True
