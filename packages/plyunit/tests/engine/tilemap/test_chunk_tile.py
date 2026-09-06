from __future__ import annotations

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

    tm2 = _make_tilemap(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 16},
            "chunks": {
                "-1,-1": {"chunk_x": -1, "chunk_y": -1, "layers": {"1": [1]}},
                "1,1": {"chunk_x": 1, "chunk_y": 1, "layers": {"1": [1]}},
            },
        }
    )
    # pyrefly: ignore [not-iterable]
    bx, by, bw, bh = tm2.get_render_bounds()
    assert (bx, by, bw, bh) == (-256.0, -256.0, 768.0, 768.0)
