from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from plyunit.tilemap.map_data import ChunkRT
from plyunit.tilemap.tilemap import TileMapNode, parse_map_config


def _grid_map(n=3):
    chunks = {}
    for cx in range(n):
        for cy in range(n):
            chunks[f"{cx},{cy}"] = {
                "chunk_x": cx,
                "chunk_y": cy,
                "layers": {"1": [1]},
            }
    return {
        "settings": {"tile_size": [16, 16], "chunk_size": 2},
        "chunks": chunks,
    }


def _make_tilemap(config_dict):
    tm = TileMapNode()
    tm._background_bake_enabled = False
    tm.config = parse_map_config(config_dict)
    tm.tile_size = tm.config.settings.tile_size[0]
    tm.chunk_size = tm.config.settings.chunk_size
    return tm


def test_max_loaded_chunks_setter_applies_to_live_store():
    tm = _make_tilemap(_grid_map(n=3))
    store = tm._chunk_tile
    assert store._max_loaded == 64
    tm.max_loaded_chunks = 8
    assert store._max_loaded == 8
    assert tm.max_loaded_chunks == 8


def test_small_map_pins_all_chunks_no_unload_thrash():
    tm = _make_tilemap(_grid_map(n=3))
    tm.max_loaded_chunks = 16
    store = tm._chunk_tile
    # pyrefly: ignore [missing-attribute]
    store.update(set(tm.config.chunks.keys()))
    assert len(store) == 9
    store.update({"0,0"})
    assert len(store) == 9
    assert store.is_loaded("2,2")


def test_max_loads_per_update_spreads_only_when_not_pinned():
    # pin_all is off when max_loaded < total chunks.
    tm = _make_tilemap(_grid_map(n=3))
    tm.max_loaded_chunks = 16
    tm.max_loads_per_update = 2
    store = tm._chunk_tile
    assert store._max_loads_per_update == 2
    # visible=all still loads with cap; not pin_all because total(9) <= max(16)
    # would pin — force non-pin by lowering max below total after construct.
    store._max_loaded = 8
    # pyrefly: ignore [missing-attribute]
    store.update(set(tm.config.chunks.keys()))
    assert len(store) == 2
    # pyrefly: ignore [missing-attribute]
    store.update(set(tm.config.chunks.keys()))
    assert len(store) == 4
    for _ in range(10):
        # pyrefly: ignore [missing-attribute]
        store.update(set(tm.config.chunks.keys()))
    assert len(store) == 8  # capped by max_loaded


def test_small_map_pin_loads_all_immediately():
    tm = _make_tilemap(_grid_map(n=3))
    tm.max_loads_per_update = 2
    store = tm._chunk_tile
    store.update({"0,0"})
    assert len(store) == 9


def test_lru_cap_when_map_exceeds_max_loaded():
    tm = _make_tilemap(_grid_map(n=4))
    tm.max_loaded_chunks = 4
    store = tm._chunk_tile
    # pyrefly: ignore [missing-attribute]
    store.update(set(tm.config.chunks.keys()))
    assert len(store) <= 4


def test_get_render_bounds_covers_all_chunks():
    tm = _make_tilemap(_grid_map(n=3))
    bounds = tm.get_render_bounds()
    assert bounds is not None
    x, y, w, h = bounds
    assert (x, y, w, h) == (0.0, 0.0, 96.0, 96.0)

    tm2 = _make_tilemap({
        "settings": {"tile_size": [16, 16], "chunk_size": 16},
        "chunks": {
            "-1,-1": {"chunk_x": -1, "chunk_y": -1, "layers": {"1": [1]}},
            "1,1": {"chunk_x": 1, "chunk_y": 1, "layers": {"1": [1]}},
        },
    })
    # pyrefly: ignore [not-iterable]
    bx, by, bw, bh = tm2.get_render_bounds()
    assert (bx, by, bw, bh) == (-256.0, -256.0, 768.0, 768.0)


def test_visible_chunk_is_not_evicted_for_preload_margin() -> None:
    tm = _make_tilemap(_grid_map(n=4))
    tm.max_loaded_chunks = 1
    tm._load_chunk = MagicMock()
    tm._unload_chunk = MagicMock()
    store = tm._chunk_tile
    store.load_chunk("3,3")
    tm._load_chunk.reset_mock()

    for _ in range(3):
        store.update({"3,3"})

    assert store.loaded == {"3,3"}
    tm._load_chunk.assert_not_called()
    tm._unload_chunk.assert_not_called()


def test_load_budget_prioritizes_visible_chunks_over_margin() -> None:
    tm = _make_tilemap(_grid_map(n=4))
    tm.max_loaded_chunks = 2
    tm.max_loads_per_update = 1
    tm._load_chunk = MagicMock()
    store = tm._chunk_tile

    store.update({"3,3"})

    assert store.loaded == {"3,3"}
    assert tm._load_chunk.call_count == 1
    store.update({"3,3"})
    assert len(store) == 2
    assert store.is_loaded("3,3")
    assert tm._load_chunk.call_count == 2


def test_viewport_larger_than_capacity_does_not_thrash() -> None:
    tm = _make_tilemap(_grid_map(n=4))
    tm.max_loaded_chunks = 2
    tm._load_chunk = MagicMock()
    tm._unload_chunk = MagicMock()
    assert tm.config is not None
    visible = set(tm.config.chunks)
    store = tm._chunk_tile
    store.update(visible)
    resident = store.loaded
    tm._load_chunk.reset_mock()

    for _ in range(3):
        store.update(visible)

    assert store.loaded == resident
    assert len(store) == 2
    tm._load_chunk.assert_not_called()
    tm._unload_chunk.assert_not_called()


def test_camera_move_replaces_margin_before_visible_chunks() -> None:
    tm = _make_tilemap(_grid_map(n=4))
    tm.max_loaded_chunks = 2
    tm.max_loads_per_update = 1
    tm._load_chunk = MagicMock()
    tm._unload_chunk = MagicMock()
    store = tm._chunk_tile
    store.load_chunk("0,0")

    store.update({"1,1", "2,2"})
    assert store.is_loaded("1,1")
    store.update({"1,1", "2,2"})

    assert store.loaded == {"1,1", "2,2"}
    tm._unload_chunk.assert_called_once_with("0,0")


def test_removed_chunks_are_unloaded_even_when_map_is_pinned() -> None:
    tm = _make_tilemap(_grid_map(n=2))
    tm._load_chunk = MagicMock()
    tm._unload_chunk = MagicMock()
    assert tm.config is not None
    store = tm._chunk_tile
    store.update({"0,0"})
    del tm.config.chunks["0,0"]

    store.update(set())

    assert store.loaded == set(tm.config.chunks)
    tm._unload_chunk.assert_called_once_with("0,0")


@pytest.mark.parametrize("key", ["missing-comma", "x,0", "0,y", "0,1,2"])
def test_malformed_margin_keys_do_not_raise(key: str) -> None:
    tm = _make_tilemap(_grid_map())

    assert tm._chunk_tile._keys_around({key}, 1) == {key}


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        ((0.0, 0.0, 32.0, 32.0), {"0,0"}),
        ((32.0, 32.0, 64.0, 64.0), {"1,1"}),
        ((-32.0, -32.0, 0.0, 0.0), {"-1,-1"}),
        ((0.0, 0.0, 32.5, 32.5), {"0,0", "0,1", "1,0", "1,1"}),
        ((0.0, 0.0, 0.0, 32.0), set()),
        ((16.0, 16.0, 0.0, 0.0), set()),
    ],
)
def test_visible_keys_use_half_open_viewport_bounds(
    view: tuple[float, float, float, float], expected: set[str]
) -> None:
    tm = _make_tilemap(_grid_map(n=3))
    assert tm.config is not None
    tm.config.chunks["-1,-1"] = ChunkRT(chunk_x=-1, chunk_y=-1)
    tm.margin_chunks = 0
    camera = MagicMock()
    camera.get_view_rect.return_value = view
    tm.one_or_none = MagicMock(return_value=camera)

    assert tm._visible_chunk_keys() == expected


def test_visible_keys_never_include_nonexistent_chunks() -> None:
    tm = _make_tilemap(_grid_map(n=2))
    assert tm.config is not None
    camera = MagicMock()
    camera.get_view_rect.return_value = (-100.0, -100.0, 100.0, 100.0)
    tm.one_or_none = MagicMock(return_value=camera)

    assert tm._visible_chunk_keys() == set(tm.config.chunks)


def test_visible_keys_without_config_are_empty() -> None:
    assert TileMapNode()._visible_chunk_keys() == set()
