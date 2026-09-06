"""Tests for the tilemap → Physics bridge, baker shape preservation,
one-way platforms, streaming, and the typed MapConfig."""

from __future__ import annotations
from plyunit.tilemap.tilemap import parse_map_config

from unittest.mock import MagicMock

import pytest

# pymunk is a real (non-mocked) dependency in the venv.
from plyunit.backends.physics.pymunk.service import Physics
from plyunit.core.components.physics import (
    BodyType,
    BoxShape,
    CollisionFilter,
)
from plyunit.tilemap.map_data import ChunkRT, MapConfig, MapSettingsRT
from plyunit.tilemap.mesher import (
    generate_merged_rectangles,
    generate_merged_rectangles_grouped,
)
from plyunit.tilemap.physics_baker import (
    bake_all_chunks_runtime,
    bake_chunk_from_arrays,
    build_gid_physics_map_runtime,
)
from plyunit.tilemap.physics_bridge import TileMapPhysicsBridge
from plyunit.tilemap.tilemap import TileMapNode

# ---------------------------------------------------------------------------
# Mesher
# ---------------------------------------------------------------------------


class TestMesher:
    def test_generate_merged_rectangles_basic(self):
        grid = [[1, 1], [1, 1]]
        rects = generate_merged_rectangles(grid, tile_size=16)
        assert rects == [(0.0, 0.0, 32.0, 32.0)]

    def test_grouped_merges_same_key_skips_none(self):
        grid = [["a", "a", None], ["a", "b", "b"]]
        # pyrefly: ignore [bad-argument-type]
        rects = generate_merged_rectangles_grouped(grid, tile_size=10)
        # "a" merges into 2x2? No: (0,0)a,(1,0)a,(0,1)a are 'a' but (1,1)=b.
        # So 'a' at (0,0) expands right to (1,0) [w=2], down check (0,1)=a,(1,1)=b
        # -> can't extend down. So 'a' rect = (0,0,20,10).
        # 'a' at (0,1) separate -> (0,10,10,10). 'b' at (1,1),(2,1) -> (10,10,20,10).
        keys = {r[4] for r in rects}
        assert "a" in keys and "b" in keys
        a_rects = sorted(r for r in rects if r[4] == "a")
        assert a_rects[0][:4] == (0.0, 0.0, 20.0, 10.0)


# ---------------------------------------------------------------------------
# Baker
# ---------------------------------------------------------------------------


def _chunk(gid_arrays, chunk_x=0, chunk_y=0):
    return ChunkRT(
        chunk_x=chunk_x,
        chunk_y=chunk_y,
        gid_arrays=dict(gid_arrays),
        decoded=True,
    )


class TestBaker:
    def test_full_tile_boxes_merge(self):
        physics = {"shape": {"kind": "box"}, "layer": 1, "mask": 0xFFFF}
        tilesets = {1: _tset(1, physics)}
        gid_physics = build_gid_physics_map_runtime(tilesets)
        # 2x2 solid block
        chunk = _chunk({"1": [1, 1, 1, 1]})
        MapConfig(
            settings=MapSettingsRT(tile_size=(16, 16), chunk_size=2),
            tilesets=tilesets,
            chunks={"0,0": chunk},
        )
        baked = bake_chunk_from_arrays(chunk, 2, 16, gid_physics)
        assert list(baked) == ["1"]
        bodies = baked["1"]["bodies"]
        assert len(bodies) == 1
        body = bodies[0]
        # pyrefly: ignore [bad-typed-dict-key]
        assert body["shape"]["size"] == (32.0, 32.0)
        assert body["world_pos"] == (0.0, 0.0)
        assert body["physics_layer"] == 1

    def test_polygon_emitted_per_tile_preserved(self):
        verts = [(0.0, 0.0), (16.0, 0.0), (8.0, 16.0)]
        physics = {
            "shape": {"kind": "polygon", "vertices": verts},
            "layer": 2,
            "friction": 0.3,
            "restitution": 0.7,
            "is_one_way": True,
        }
        tilesets = {1: _tset(1, physics)}
        gid_physics = build_gid_physics_map_runtime(tilesets)
        chunk = _chunk({"1": [1, 0, 1, 0]})  # two polygon tiles
        baked = bake_chunk_from_arrays(chunk, 2, 16, gid_physics)
        bodies = baked["1"]["bodies"]
        assert len(bodies) == 2
        for b in bodies:
            assert b["shape"]["kind"] == "polygon"
            assert b["shape"]["vertices"] == verts
            assert b["is_one_way"] is True
            assert b["friction"] == 0.3
            assert b["restitution"] == 0.7
            assert b["physics_layer"] == 2

    def test_circle_emitted_per_tile(self):
        physics = {"shape": {"kind": "circle", "offset": (8.0, 8.0), "radius": 6.0}}
        tilesets = {1: _tset(1, physics)}
        gid_physics = build_gid_physics_map_runtime(tilesets)
        chunk = _chunk({"1": [1, 1, 0, 0]})
        baked = bake_chunk_from_arrays(chunk, 2, 16, gid_physics)
        bodies = baked["1"]["bodies"]
        assert len(bodies) == 2
        for b in bodies:
            assert b["shape"]["kind"] == "circle"
            assert b["shape"]["radius"] == 6.0

    def test_non_full_box_not_merged(self):
        physics = {"shape": {"kind": "box", "offset": (0.0, 0.0), "size": (8.0, 8.0)}}
        tilesets = {1: _tset(1, physics)}
        gid_physics = build_gid_physics_map_runtime(tilesets)
        chunk = _chunk({"1": [1, 1, 1, 1]})
        baked = bake_chunk_from_arrays(chunk, 2, 16, gid_physics)
        bodies = baked["1"]["bodies"]
        # Each non-full box stays per-tile (no merge).
        assert len(bodies) == 4

    def test_bake_all_chunks_runtime(self):
        physics = {"shape": {"kind": "box"}, "layer": 1}
        tilesets = {1: _tset(1, physics)}
        cfg = MapConfig(
            settings=MapSettingsRT(tile_size=(16, 16), chunk_size=2),
            tilesets=tilesets,
            chunks={"0,0": _chunk({"1": [1, 1, 1, 1]})},
        )
        result = bake_all_chunks_runtime(cfg)
        assert "0,0" in result
        assert len(result["0,0"]["1"]["bodies"]) == 1


def _tset(gid, physics):
    from plyunit.tilemap.map_data import TilesetRuntime

    return TilesetRuntime(gid=gid, physics=physics)


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


def _box_body(world_pos, size=(32.0, 16.0), layer=1, mask=0xFFFFFFFF, one_way=False):
    return {
        "shape": {"kind": "box", "offset": (0.0, 0.0), "size": size},
        "world_pos": world_pos,
        "physics_layer": layer,
        "physics_mask": mask,
        "is_one_way": one_way,
        "friction": 0.5,
        "restitution": 0.0,
    }


class TestBridge:
    def test_spawn_and_despawn_statics(self):
        physics = Physics(gravity=(0, 0))
        bridge = TileMapPhysicsBridge(physics, tile_size=16, chunk_size=16)
        # pyrefly: ignore [bad-argument-type]
        ids = bridge.spawn_bodies([_box_body((0.0, 0.0))])
        assert len(ids) == 1
        # pyrefly: ignore [missing-attribute]
        assert physics.static_count == 1
        bridge.despawn_bodies(ids)
        assert physics.static_count == 0

    def test_box_offset_centered(self):
        physics = Physics(gravity=(0, 0))
        bridge = TileMapPhysicsBridge(physics, tile_size=16, chunk_size=16)
        # pyrefly: ignore [bad-argument-type]
        ids = bridge.spawn_bodies([_box_body((0.0, 0.0), size=(32.0, 16.0))])
        static = physics._statics[ids[0]]
        # Box centered at world_pos + size/2 → AABB covers [0,0,32,16].
        # pyrefly: ignore [missing-attribute]
        aabb = physics._compute_static_aabb(static)
        assert aabb.min_x == pytest.approx(0.0)
        assert aabb.min_y == pytest.approx(0.0)
        assert aabb.max_x == pytest.approx(32.0)
        assert aabb.max_y == pytest.approx(16.0)

    def test_install_one_way_handler_idempotent(self):
        physics = Physics(gravity=(0, 0))
        bridge = TileMapPhysicsBridge(physics, tile_size=16, chunk_size=16)
        bridge.install_one_way_handler()
        n1 = len(physics._pre_solve_handlers)
        bridge.install_one_way_handler()
        assert len(physics._pre_solve_handlers) == n1

    def test_one_way_passes_from_below_blocks_from_above(self):
        physics = Physics(gravity=(0, 900))
        bridge = TileMapPhysicsBridge(physics, tile_size=16, chunk_size=16)
        bridge.install_one_way_handler()

        # One-way platform spanning x=[0,200], y=[100,116].
        # pyrefly: ignore [bad-argument-type]
        bridge.spawn_bodies([_box_body((0.0, 100.0), size=(200.0, 16.0), one_way=True)])

        actor_filter = CollisionFilter.dynamic_actor()
        # Actor above, falling.
        above = physics.create_body(
            position=(100.0, 50.0),
            body_type=BodyType.DYNAMIC,
            shapes=[BoxShape(width=12, height=12)],
            mass=1.0,
            filter=actor_filter,
        )
        # Actor below, moving up.
        below = physics.create_body(
            position=(100.0, 180.0),
            body_type=BodyType.DYNAMIC,
            shapes=[BoxShape(width=12, height=12)],
            mass=1.0,
            filter=actor_filter,
        )
        physics.set_body_state(below, velocity=(0.0, -800.0))

        for _ in range(60):
            # pyrefly: ignore [missing-attribute]
            physics.step(1 / 60)

        # pyrefly: ignore [unsupported-operation]
        above_y = physics.get_position(above)[1]
        # pyrefly: ignore [unsupported-operation]
        below_y = physics.get_position(below)[1]

        # Above actor must NOT fall through the platform (stays at/above y≈100).
        assert above_y < 100.0
        # Below actor penetrates upward past the platform top (y < 100).
        assert below_y < 100.0

    def test_solid_platform_blocks_from_below(self):
        physics = Physics(gravity=(0, 900))
        bridge = TileMapPhysicsBridge(physics, tile_size=16, chunk_size=16)
        bridge.install_one_way_handler()

        # Solid (non-one-way) platform.
        bridge.spawn_bodies(
            # pyrefly: ignore [bad-argument-type]
            [_box_body((0.0, 100.0), size=(200.0, 16.0), one_way=False)]
        )

        actor_filter = CollisionFilter.dynamic_actor()
        below = physics.create_body(
            position=(100.0, 180.0),
            body_type=BodyType.DYNAMIC,
            shapes=[BoxShape(width=12, height=12)],
            mass=1.0,
            filter=actor_filter,
        )
        physics.set_body_state(below, velocity=(0.0, -800.0))

        for _ in range(60):
            # pyrefly: ignore [missing-attribute]
            physics.step(1 / 60)

        # pyrefly: ignore [unsupported-operation]
        below_y = physics.get_position(below)[1]
        # Solid platform stops the upward-moving actor → stays below platform.
        assert below_y > 110.0


# ---------------------------------------------------------------------------
# TileMapNode: MapConfig, get_gid_at O(1), mutation, streaming
# ---------------------------------------------------------------------------


def _make_tilemap(config_dict, mock_assets=None):
    tm = TileMapNode()
    tm._background_bake_enabled = False
    tm.config = parse_map_config(config_dict)
    tm.tile_size = tm.config.settings.tile_size[0]
    tm.chunk_size = tm.config.settings.chunk_size
    if mock_assets is not None:
        tm.one = MagicMock(return_value=mock_assets)
    return tm


class TestTileMapNode:
    def test_get_gid_at_is_o1(self):
        cfg = {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {"1": [1, 2, 3, 4]},
                }
            },
        }
        tm = _make_tilemap(cfg)
        # grid (0,0)->gid1, (1,0)->gid2, (0,1)->gid3, (1,1)->gid4
        assert tm.get_gid_at(0, 0) == 1
        assert tm.get_gid_at(16, 0) == 2
        assert tm.get_gid_at(0, 16) == 3
        assert tm.get_gid_at(16, 16) == 4
        assert tm.get_gid_at(48, 48) is None  # outside chunk

    def test_set_tile_emits_signal_and_updates(self):
        cfg = {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "chunks": {
                "0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [1, 0, 0, 0]}}
            },
        }
        tm = _make_tilemap(cfg)
        events = []
        tm.tile_changed.connect(
            lambda key, layer, x, y, old, new: events.append(
                (key, layer, x, y, old, new)
            )
        )
        changed = tm.set_tile(16, 0, 5)
        assert changed is True
        assert events == [("0,0", "1", 1, 0, 0, 5)]
        assert tm.get_gid_at(16, 0) == 5
        # No-op returns False, no signal.
        assert tm.set_tile(16, 0, 5) is False
        assert len(events) == 1

    def test_fill_changes_count(self):
        cfg = {
            "settings": {"tile_size": [16, 16], "chunk_size": 4},
            "chunks": {"0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [0] * 16}}},
        }
        tm = _make_tilemap(cfg)
        n = tm.fill((0, 0, 32, 32), 7)
        assert n == 4  # 2x2 tiles
        assert tm.get_gid_at(0, 0) == 7
        assert tm.get_gid_at(16, 16) == 7
        assert tm.get_gid_at(48, 0) is None

    def test_remove_tile(self):
        cfg = {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "chunks": {
                "0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [1, 0, 0, 0]}}
            },
        }
        tm = _make_tilemap(cfg)
        assert tm.remove_tile(0, 0) is True
        assert tm.get_gid_at(0, 0) is None


class TestChunkTileStreaming:
    def _grid_map(self, n=3):
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

    def test_load_unload_by_visibility(self):
        tm = _make_tilemap(self._grid_map(n=4))
        tm.max_loaded_chunks = 8
        store = tm._chunk_tile

        # pyrefly: ignore [missing-attribute]
        all_keys = set(tm.config.chunks.keys())
        store.update(all_keys)
        assert len(store) <= 8

        store.load_chunk("3,3")
        assert store.is_loaded("3,3")
        store.update({"0,0"})
        assert store.is_loaded("0,0")
        assert not store.is_loaded("3,3")

    def test_lru_eviction(self):
        tm = _make_tilemap(self._grid_map(n=4))
        tm.max_loaded_chunks = 4
        store = tm._chunk_tile
        store.update(tm._visible_chunk_keys())
        assert len(store) <= 4

    def test_destroy_no_leak(self):
        tm = _make_tilemap(self._grid_map(n=2))
        physics = Physics(gravity=(0, 0))

        def _one(ref):
            return physics if ref == "@Physics" else None

        tm.one_or_none = MagicMock(side_effect=_one)
        tm._bridge = None
        # pyrefly: ignore [missing-attribute]
        for _key, chunk in tm.config.chunks.items():
            chunk.baked_physics = {"1": {"bodies": [_box_body((0.0, 0.0))]}}

        # pyrefly: ignore [missing-attribute]
        tm._chunk_tile.update(set(tm.config.chunks.keys()))
        # pyrefly: ignore [missing-attribute]
        for key in list(tm._chunk_tile.loaded):
            # pyrefly: ignore [missing-attribute]
            tm._spawn_chunk_physics(key, tm.config.chunks[key])
        # pyrefly: ignore [missing-attribute]
        assert physics.static_count == 4

        tm.destroy()
        assert physics.static_count == 0
        assert tm._baked_render == {}
