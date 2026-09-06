"""Top-level map objects: JSON parse → ``MapConfig.objects`` + the ``on_objects`` hook."""

from __future__ import annotations

import json

from plyunit.tilemap.map_data import ChunkRT
from plyunit.tilemap.tilemap import TileMapNode

MAP_DICT = {
    "settings": {"tile_size": [16, 16], "chunk_size": 2},
    "objects": [
        {
            "type": "spawn_point",
            "world_x": 32.0,
            "world_y": 48.0,
            "properties": {"team": "blue"},
        },
        {"type": "chest", "world_x": 10.0, "world_y": 12.0},
    ],
    "chunks": {"0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [1, 0, 0, 0]}}},
}


def _write_map(tmp_path, payload=None):
    p = tmp_path / "map.json"
    p.write_text(
        json.dumps(payload if payload is not None else MAP_DICT), encoding="utf-8"
    )
    return p


class TestParseMapObjects:
    def test_objects_land_in_config(self, tmp_path):
        tm = TileMapNode()
        tm.load_map(_write_map(tmp_path))
        assert [o["type"] for o in tm.config.objects] == ["spawn_point", "chest"]
        assert tm.config.objects[0]["properties"] == {"team": "blue"}

    def test_chunk_no_longer_holds_objects(self, tmp_path):
        tm = TileMapNode()
        tm.load_map(_write_map(tmp_path))
        chunk = tm.config.chunks["0,0"]
        assert isinstance(chunk, ChunkRT)
        assert not hasattr(chunk, "objects")

    def test_missing_objects_defaults_empty(self, tmp_path):
        payload = {"settings": {"tile_size": [16, 16], "chunk_size": 2}, "chunks": {}}
        tm = TileMapNode()
        tm.load_map(_write_map(tmp_path, payload))
        assert tm.config.objects == []


class TestOnObjectsHook:
    def test_hook_called_once_after_load(self, tmp_path):
        tm = TileMapNode()
        calls: list[list] = []
        tm.load_map(_write_map(tmp_path), on_objects=calls.append)
        assert len(calls) == 1
        assert calls[0] is tm.config.objects
        assert [o["type"] for o in calls[0]] == ["spawn_point", "chest"]

    def test_hook_called_with_empty_list_when_no_objects(self, tmp_path):
        payload = {"settings": {"tile_size": [16, 16], "chunk_size": 2}, "chunks": {}}
        tm = TileMapNode()
        calls: list[list] = []
        tm.load_map(_write_map(tmp_path, payload), on_objects=calls.append)
        assert calls == [[]]

    def test_no_hook_no_error(self, tmp_path):
        tm = TileMapNode()
        tm.load_map(_write_map(tmp_path))

    def test_init_forwards_hook(self, tmp_path):
        calls: list[list] = []
        TileMapNode(
            name="tm", config_path=_write_map(tmp_path), on_objects=calls.append
        )
        assert len(calls) == 1
        assert calls[0][0]["type"] == "spawn_point"
