from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest

from plyunit.tilemap.autotile import AutotileProcessor
from plyunit.tilemap.encoding import (
    decode_array,
    decode_base64_zlib,
    decode_csv,
    encode_array,
    encode_base64_zlib,
    encode_csv,
    get_decoder,
    get_encoder,
    register_decoder,
    register_encoder,
)
from plyunit.tilemap.physics_baker import bake_all_chunks, bake_chunk_physics, build_gid_physics_map


def test_encoding_round_trips_and_registry() -> None:
    data = [1, 2, 3, 4]
    packed = base64.b64encode(zlib.compress(struct.pack("<4I", *data))).decode("utf-8")

    assert decode_array(data) is data
    assert decode_array("1, 2, 3") == [1, 2, 3]
    assert decode_csv(data) is data
    assert decode_csv("1,2,3") == [1, 2, 3]
    assert decode_base64_zlib(data) is data
    assert decode_base64_zlib(packed) == data
    assert encode_array(data) is data
    assert encode_csv(data) == "1,2,3,4"
    assert decode_base64_zlib(encode_base64_zlib(data)) == data

    register_decoder("custom", lambda raw: [9])
    register_encoder("custom", lambda values: "custom")
    assert get_decoder("custom")("x") == [9]
    assert get_encoder("custom")([1]) == "custom"

    with pytest.raises(KeyError):
        get_decoder("missing")
    with pytest.raises(KeyError):
        get_encoder("missing")


def test_autotile_processor_modes_and_random_resolution(tmp_path) -> None:
    config = {
        "autotiles": {
            "grass": {
                "fallback_region": [0, 0, 8, 8],
                "bitmasks": {
                    "15": {"random": [{"id": "a", "weight": 1.0}, {"id": "b", "weight": 2.0}]},
                    "255": [8, 0, 8, 8],
                },
            }
        }
    }
    path = tmp_path / "auto.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    processor = AutotileProcessor(str(path))
    grid = [["g", "g", "g"], ["g", "g", "g"], ["g", "g", "g"]]

    assert processor.calculate_bitmask(grid, 1, 1, "g", "match_sides") == 15
    assert processor.calculate_bitmask(grid, 1, 1, "g", "match_corners") == 240
    assert processor.calculate_bitmask(grid, 1, 1, "g", "match_corners_and_sides") == 255
    assert processor.resolve_tile("missing", 15) == (None, 1.0)
    assert processor.resolve_tile("grass", 123) == ([0, 0, 8, 8], 1.0)
    assert processor.resolve_tile("grass", 255) == ([8, 0, 8, 8], 1.0)
    value, weight = processor.resolve_tile("grass", 15, seed=1)
    assert value in {"a", "b"}
    assert weight in {1.0, 2.0}


def test_physics_baker_builds_and_merges_chunks() -> None:
    physics = {
        "shape": {"kind": "box"},
        "layer": 2,
        "mask": 3,
        "is_one_way": False,
        "friction": 0.25,
        "restitution": 0.1,
    }
    tilesets = {"solid": {"gid": 1, "physics": physics}, "empty": {"gid": 2}}
    # pyrefly: ignore [bad-argument-type]
    gid_map = build_gid_physics_map(tilesets)

    assert gid_map == {1: physics}

    chunk = {
        "chunk_x": 2,
        "chunk_y": 3,
        "layers": {"1": [1, 1, 0, 0], "2": [0, 0, 0, 0]},
        "encoding": "array",
    }
    baked = bake_chunk_physics(
        # pyrefly: ignore [bad-argument-type]
        chunk,
        chunk_size=2,
        tile_size=16,
        gid_physics=gid_map,
        decode_fn={"array": lambda raw: raw},
    )

    assert list(baked) == ["1"]
    body = baked["1"]["bodies"][0]
    assert body["world_pos"] == (64.0, 96.0)
    # pyrefly: ignore [bad-typed-dict-key]
    assert body["shape"]["size"] == (32.0, 16.0)
    assert body["physics_layer"] == 2

    map_config = {
        "settings": {"tile_size": [16, 16], "chunk_size": 2, "encoding": "array"},
        "tilesets": tilesets,
        "chunks": {"2,3": chunk},
    }
    assert "2,3" in bake_all_chunks(map_config, {"array": lambda raw: raw})
    assert bake_all_chunks({"tilesets": {}, "chunks": {}}, {"array": lambda raw: raw}) == {}
