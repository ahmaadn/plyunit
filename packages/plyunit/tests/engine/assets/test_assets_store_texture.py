"""Assets.store_texture / store_textures: simpan texture eksternal + atlas."""

from __future__ import annotations

import pytest

import plyunit.assets.assets as assets_module
from plyunit.assets.types import ConfigTexture


class FakeTexture:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.id = abs(hash(name)) % 100000


class StoreDummyLoader:
    def __init__(self) -> None:
        self.default = ConfigTexture(
            filter="nearest",
            wrap="clamp",
            mipmap=False,
            srgb=True,
            premultiply_alpha=False,
            color_key=(0, 0, 0, 255),
        )
        self.unloaded_textures: list[str] = []

    def unload_texture(self, texture):
        self.unloaded_textures.append(texture.name)


class AtlasComposeLoader(StoreDummyLoader):
    """Dummy loader that supports full atlas-page composition."""

    def __init__(self) -> None:
        super().__init__()
        self._page_counter = 0

    def gen_image_color(self, width, height, color=(0, 0, 0, 0)):
        return FakeTexture(f"page:{width}x{height}", width, height)

    def load_image_from_texture(self, texture):
        return FakeTexture(texture.name, texture.width, texture.height)

    def image_draw(self, dst, src, pos):
        pass

    def unload_image(self, image):
        pass

    def load_texture_from_image(self, image):
        self._page_counter += 1
        return FakeTexture(
            f"atlas_page_{self._page_counter}", image.width, image.height
        )

    def set_texture_filter(self, texture, filter_mode):
        pass

    def set_texture_wrap(self, texture, wrap_mode):
        pass


def make_assets() -> assets_module.Assets:
    # pyrefly: ignore [bad-argument-type]
    return assets_module.Assets(loader=StoreDummyLoader())


def test_store_texture_registers_root_asset() -> None:
    manager = make_assets()
    texture = FakeTexture("rect_a", 32, 16)

    manager.store_texture("rect_a", texture)

    data = manager.get_texture_data("rect_a")
    assert data.texture is texture
    assert data.parent_id == "rect_a"
    assert data.source_rect == (0.0, 0.0, 32.0, 16.0)
    assert manager.get_asset("rect_a") is texture


def test_store_texture_rejects_none() -> None:
    manager = make_assets()

    with pytest.raises(ValueError, match="tidak boleh None"):
        manager.store_texture("bad", None)


def test_store_texture_overwrites_existing_id() -> None:
    manager = make_assets()
    old = FakeTexture("old", 8, 8)
    new = FakeTexture("new", 16, 16)

    manager.store_texture("shared", old)
    manager.store_texture("shared", new)

    assert manager.get_asset("shared") is new
    # The old root is unloaded from the GPU when overwritten.
    assert manager._loader.unloaded_textures == ["old"]


def test_store_textures_bulk() -> None:
    manager = make_assets()
    textures = {
        "rect_1": FakeTexture("r1", 4, 4),
        "rect_2": FakeTexture("r2", 8, 2),
        "circle_1": FakeTexture("c1", 6, 6),
    }

    manager.store_textures(textures)

    for asset_id, texture in textures.items():
        assert manager.get_asset(asset_id) is texture


def test_store_textures_rejects_none_entry() -> None:
    manager = make_assets()

    with pytest.raises(ValueError, match="rect_1"):
        manager.store_textures({"rect_1": None})


def test_register_texture_is_deprecated_alias() -> None:
    manager = make_assets()
    texture = FakeTexture("legacy", 4, 4)

    with pytest.deprecated_call():
        manager.register_texture("legacy", texture)

    assert manager.get_asset("legacy") is texture


def test_stored_textures_are_atlas_packable() -> None:
    """Texture buatan canvas.create_* (root mandiri) layak di-pack atlas."""
    manager = make_assets()
    manager.store_texture("rect_a", FakeTexture("rect_a", 32, 16))
    manager.store_texture("rect_b", FakeTexture("rect_b", 16, 16))

    roots = manager._collect_atlas_roots(["rect_a", "rect_b"])

    assert roots == ["rect_a", "rect_b"]


def test_build_texture_atlas_packs_stored_textures() -> None:
    """Siklus penuh: store_texture -> build_texture_atlas -> get_asset."""
    loader = AtlasComposeLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(loader=loader)
    rect_a = FakeTexture("rect_a", 32, 16)
    rect_b = FakeTexture("rect_b", 16, 16)
    manager.store_texture("rect_a", rect_a)
    manager.store_texture("rect_b", rect_b)

    page_ids = manager.build_texture_atlas(["rect_a", "rect_b"])

    assert len(page_ids) == 1
    page = manager.get_asset(page_ids[0])
    # Both old IDs now point to the same atlas page.
    assert manager.get_asset("rect_a") is page
    assert manager.get_asset("rect_b") is page
    # The old textures are unloaded from the GPU after being moved into the atlas.
    assert loader.unloaded_textures == ["rect_a", "rect_b"]
    # Atlas source rects are valid (inside the page).
    rect = manager.get_source_rect("rect_a")
    assert rect is not None
    assert rect[0] >= 0.0 and rect[0] + rect[2] <= float(page.width)
    assert rect[1] >= 0.0 and rect[1] + rect[3] <= float(page.height)
