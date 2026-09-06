from plyunit.tilemap.tilemap import parse_map_config
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from plyunit.assets.assets import Assets
from plyunit.assets.types import TextureData
from plyunit.tilemap.tilemap import TileMapNode


@pytest.fixture
def mock_assets():
    assets = MagicMock(spec=Assets)

    # Mock regions
    # "grass", "water", "tree"
    t1 = TextureData(parent_id="terrain", texture=MagicMock(), source_rect=(0, 0, 16, 16))
    t2 = TextureData(parent_id="terrain", texture=MagicMock(), source_rect=(16, 0, 16, 16))
    t3 = TextureData(parent_id="terrain", texture=MagicMock(), source_rect=(32, 0, 16, 16))

    assets._regions = {
        "grass": t1,
        "water": t2,
        "tree": t3,
    }

    def fake_get_texture_data(alias):
        return assets._regions.get(alias)

    assets.get_texture_data.side_effect = fake_get_texture_data
    return assets


@pytest.fixture
def tilemap_service(mock_assets):
    # Inject fake canvas (via fake Renderer query one) so tests do not need
    # real pyray.
    class FakeCanvas:
        def __init__(self):
            self.loads = []
            self.draws = []

        def load_render_texture(self, w, h):
            t = MagicMock()
            self.loads.append((w, h))
            return t

        def unload_render_texture(self, target):
            pass

        def begin_texture_mode(self, target):
            pass

        def end_texture_mode(self):
            pass

        def clear_transparent(self):
            pass

        def draw_texture_region(self, texture, source, dest):
            self.draws.append((texture, source, dest))

        def set_texture_filter(self, target, filter_mode="trilinear"):
            pass

    canvas = FakeCanvas()
    service = TileMapNode()
    service._test_canvas = canvas

    def resolve_one(query, *args, **kwargs):
        # Canvas via Renderer; Assets for GID resolution; others absent.
        if query == "@Renderer":
            return SimpleNamespace(canvas=canvas)
        if query in (Assets, "@Assets") or (
            isinstance(query, str) and "Asset" in query
        ):
            return mock_assets
        return None

    service.one_or_none = MagicMock(side_effect=resolve_one)
    service.one = MagicMock(side_effect=resolve_one)
    return service


def test_tilemap_service_load_map(tilemap_service, tmp_path):
    map_config = {
        "settings": {"tile_size": [16, 16], "chunk_size": 8},
        "tilesets": {"1": {"gid": 1, "asset_id": "terrain"}},
        "chunks": {"0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [1, 2, 3]}, "baked_physics": {}}},
    }

    config_file = tmp_path / "map.json"
    with open(config_file, "w") as f:
        json.dump(map_config, f)

    tilemap_service.load_map(config_file)

    assert tilemap_service.tile_size == 16
    assert tilemap_service.chunk_size == 8
    assert tilemap_service.config is not None
    assert "0,0" in tilemap_service.config.chunks


def test_tilemap_service_on_ready_and_baking(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "tilesets": {
                "1": {"gid": 1, "asset_id": "grass"},
                "2": {"gid": 2, "asset_id": "water"},
                "3": {"gid": 3, "asset_id": "tree"},
            },
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {
                        "1": [1, 2, 0, 3],  # 4 tiles for 2x2 chunk
                        "2": [0, 0, 3, 0],  # Prop layer (should not be baked)
                    },
                }
            },
        }
    )

    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16
    tilemap_service.on_ready()

    # Verify GID mapping
    assert 1 in tilemap_service._gid_map
    assert 2 in tilemap_service._gid_map
    assert 3 in tilemap_service._gid_map

    # Verify Baking via canvas from Renderer (query one)
    canvas = tilemap_service._test_canvas
    assert canvas.loads == [(32, 32)]
    assert len(canvas.draws) == 3  # layer 1 tiles 1, 2, 3 (0 skipped)
    assert ("0,0", "1") in tilemap_service._baked_render


def test_tilemap_service_render_submit(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "layers": {
                "1": {"name": "Base", "y_sort_enabled": False},
                "2": {"name": "Props", "y_sort_enabled": False},
            },
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {"1": [1, 1, 1, 1], "2": [0, 0, 3, 0]},
                }
            },
        }
    )
    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16

    # Inject baked chunk layer 1
    mock_texture = SimpleNamespace(width=32, height=32)
    tilemap_service._baked_render[("0,0", "1")] = SimpleNamespace(
        texture=mock_texture
    )

    # Inject GID
    tilemap_service._gid_map[3] = SimpleNamespace(
        texture=MagicMock(),
        source_rect=(0, 0, 16, 16),
    )

    queue = MagicMock()

    # Mock camera resolution to None
    tilemap_service.one_or_none = MagicMock(return_value=None)

    # Submit without camera
    tilemap_service.render_submit(queue)

    # Expect 2 typed submissions: 1 baked chunk, 1 prop tile.
    assert queue.render_sprite.call_count == 2

    # Call 1 (Baked chunk)
    _, kwargs1 = queue.render_sprite.call_args_list[0]
    assert kwargs1["z"] == -1000
    assert kwargs1["source"] == (0, 0, 32, -32)
    assert kwargs1["dest"] == (0, 0, 32, 32)

    # Call 2 (Prop tile flat: y_sort_enabled default False)
    # index 2 -> row 1, col 0 -> y=16; z = layer*100 + z_offset only
    _, kwargs2 = queue.render_sprite.call_args_list[1]
    assert kwargs2["z"] == 200
    assert kwargs2["y_sort"] is False
    assert kwargs2["y_sort_origin"] == 0.0
    assert kwargs2["dest"] == (0, 16, 16, 16)


def test_tilemap_prop_layer_y_sort_enabled(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "layers": {
                "1": {"name": "Base"},
                "2": {"name": "Props", "y_sort_enabled": True},
            },
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {"1": [1, 1, 1, 1], "2": [0, 0, 3, 0]},
                }
            },
        }
    )
    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16
    mock_texture = SimpleNamespace(width=32, height=32)
    tilemap_service._baked_render[("0,0", "1")] = SimpleNamespace(
        texture=mock_texture
    )
    tilemap_service._gid_map[3] = SimpleNamespace(
        texture=MagicMock(),
        source_rect=(0, 0, 16, 16),
    )
    queue = MagicMock()
    tilemap_service.one_or_none = MagicMock(return_value=None)
    tilemap_service.render_submit(queue)

    assert queue.render_sprite.call_count == 2
    _, kwargs = queue.render_sprite.call_args_list[1]
    assert kwargs["y_sort"] is True
    assert kwargs["y_sort_origin"] == 16.0
    assert kwargs["z"] == 216  # layer*100 + ty


def test_tilemap_layer_render_mode_baked(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "tilesets": {
                "1": {"gid": 1, "asset_id": "grass"},
                "3": {"gid": 3, "asset_id": "tree"},
            },
            "layers": {
                "1": {"name": "Base", "render_mode": "auto"},
                "2": {
                    "name": "Roof",
                    "render_mode": "baked",
                    "y_sort_enabled": False,
                    "z_offset": 5,
                },
            },
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {
                        "1": [1, 1, 1, 1],
                        "2": [0, 0, 3, 0],
                    },
                }
            },
        }
    )
    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16
    tilemap_service.on_ready()

    assert ("0,0", "1") in tilemap_service._baked_render
    assert ("0,0", "2") in tilemap_service._baked_render

    queue = MagicMock()
    tilemap_service.one_or_none = MagicMock(return_value=None)
    tilemap_service.render_submit(queue)

    assert queue.render_sprite.call_count == 2
    zs = [c.kwargs["z"] for c in queue.render_sprite.call_args_list]
    assert -1000 in zs  # base
    assert 205 in zs  # layer 2 * 100 + z_offset 5


def test_tilemap_baked_clamped_by_y_sort(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "layers": {
                "1": {"name": "Base"},
                "2": {
                    "name": "Props",
                    "render_mode": "baked",
                    "y_sort_enabled": True,
                },
            },
            "chunks": {
                "0,0": {
                    "chunk_x": 0,
                    "chunk_y": 0,
                    "layers": {"1": [1, 1, 1, 1], "2": [0, 0, 3, 0]},
                }
            },
        }
    )
    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16
    tilemap_service._baked_render[("0,0", "1")] = SimpleNamespace(
        texture=SimpleNamespace(width=32, height=32)
    )
    tilemap_service._gid_map[3] = SimpleNamespace(
        texture=MagicMock(),
        source_rect=(0, 0, 16, 16),
    )
    assert tilemap_service._effective_render_mode("2") == "tiles"

    queue = MagicMock()
    tilemap_service.one_or_none = MagicMock(return_value=None)
    tilemap_service.render_submit(queue)
    assert queue.render_sprite.call_count == 2
    assert queue.render_sprite.call_args.kwargs["y_sort"] is True


def test_parse_map_type_isometric_normalized(tilemap_service):
    cfg = parse_map_config(
        {
            "map_type": "isometric",
            "settings": {"tile_size": [16, 16], "chunk_size": 2},
            "chunks": {},
        }
    )
    assert cfg.map_type == "orthogonal"


def test_tilemap_service_render_submit_culling(tilemap_service):
    tilemap_service.config = parse_map_config(
        {
            "settings": {"tile_size": [16, 16], "chunk_size": 2},  # 32x32 pixels per chunk
            "chunks": {
                "0,0": {"chunk_x": 0, "chunk_y": 0, "layers": {"1": [1]}},
                "10,10": {"chunk_x": 10, "chunk_y": 10, "layers": {"1": [1]}},
            },
        }
    )
    tilemap_service.chunk_size = 2
    tilemap_service.tile_size = 16

    # Full-bake path: RTs must exist before render_submit (O(1) get only).
    mock_texture = SimpleNamespace(width=32, height=32)
    tilemap_service._baked_render[("0,0", "1")] = SimpleNamespace(
        texture=mock_texture
    )
    tilemap_service._baked_render[("10,10", "1")] = SimpleNamespace(
        texture=mock_texture
    )
    for chunk in tilemap_service.config.chunks.values():
        chunk.gid_arrays["1"] = [1]
        chunk.decoded = True

    queue = MagicMock()
    camera = MagicMock()
    # Camera views world from 0,0 to 100,100. Chunk 10,10 is at 320,320,
    # so it's outside.
    camera.get_view_rect.return_value = (0, 0, 100, 100)
    tilemap_service.one_or_none = MagicMock(return_value=camera)

    tilemap_service.render_submit(queue)

    # Visible chunk 0,0 submitted; 10,10 culled (outside view + margin).
    assert queue.render_sprite.call_count == 1

    tilemap_service.render_submit(queue)

    # 10,10 is still culled; 0,0 submitted again → total 2 submissions.
    assert queue.render_sprite.call_count == 2
