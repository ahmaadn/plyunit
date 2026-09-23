"""Test texture atlas in-memory: packing, remap region/animasi, unload GPU."""

from __future__ import annotations

import importlib

import pytest

import plyunit as pu
import plyunit.assets.assets as assets_module
from plyunit.assets.animations import AnimationClip, AnimationFrame, Animations
from plyunit.assets.types import TextureData, TextureProperty

unit_module = importlib.import_module("plyunit.core.units.unit")


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


class FakeImage:
    def __init__(self, width: int, height: int, name: str = "image") -> None:
        self.width = width
        self.height = height
        self.name = name


class FakeTexture:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.id = abs(hash(name)) % 100000


class AtlasDummyLoader:
    """Dummy loader that records all atlas composition operations."""

    def __init__(self) -> None:
        self.default = TextureProperty(
            filter="nearest",
            wrap="clamp",
            mipmap=False,
            srgb=True,
            premultiply_alpha=False,
            color_key=(0, 0, 0, 255),
        )
        self.created_images: list[tuple[int, int]] = []
        self.drawn: list[tuple[str, int, int]] = []
        self.textures_from_images: list[FakeTexture] = []
        self.unloaded_images: list[str] = []
        self.unloaded_textures: list[str] = []
        self.filters: list[tuple[str, str]] = []
        self.wraps: list[tuple[str, str]] = []

    def gen_image_color(self, width: int, height: int, color=(0, 0, 0, 0)):
        _ = color
        self.created_images.append((width, height))
        return FakeImage(width, height, name=f"canvas:{width}x{height}")

    def load_image_from_texture(self, texture):
        return FakeImage(texture.width, texture.height, name=texture.name)

    def image_draw(self, dst, src, pos):
        self.drawn.append((src.name, pos[0], pos[1]))

    def unload_image(self, image):
        self.unloaded_images.append(image.name)

    def load_texture_from_image(self, image):
        texture = FakeTexture(
            f"page:{image.width}x{image.height}", image.width, image.height
        )
        self.textures_from_images.append(texture)
        return texture

    def set_texture_filter(self, texture, filter_mode):
        self.filters.append((texture.name, filter_mode))

    def set_texture_wrap(self, texture, wrap_mode):
        self.wraps.append((texture.name, wrap_mode))

    def unload_texture(self, texture):
        self.unloaded_textures.append(texture.name)


def make_manager(loader: AtlasDummyLoader) -> assets_module.Assets:
    # pyrefly: ignore [bad-argument-type]
    return assets_module.Assets(loader=loader)


def inject_asset(manager: assets_module.Assets, texture: FakeTexture) -> None:
    manager._textures[texture.name] = TextureData(
        texture=texture,  # type: ignore[arg-type]
        parent_id=texture.name,
        source_rect=(0.0, 0.0, float(texture.width), float(texture.height)),
    )
    manager._regions[texture.name] = set()


def inject_region(
    manager: assets_module.Assets, parent_id: str, region_id: str, rect: tuple[int, ...]
) -> None:
    manager._textures[region_id] = TextureData(
        texture=manager._textures[parent_id].texture,  # type: ignore[arg-type]
        parent_id=parent_id,
        source_rect=(
            float(rect[0]),
            float(rect[1]),
            float(rect[2]),
            float(rect[3]),
        ),
    )
    manager._regions[parent_id].add(region_id)


def rects_are_disjoint(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    padding: float,
) -> bool:
    return not (
        a[0] < b[0] + b[2] + padding
        and b[0] < a[0] + a[2] + padding
        and a[1] < b[1] + b[3] + padding
        and b[1] < a[1] + a[3] + padding
    )


def test_atlas_packs_roots_into_single_page(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("hero", 64, 64))
    inject_asset(manager, FakeTexture("coin", 32, 32))

    page_ids = manager.build_texture_atlas()

    assert page_ids == ["atlas"]
    atlas_texture = manager.get_asset("atlas")
    assert manager.get_asset("hero") is atlas_texture
    assert manager.get_asset("coin") is atlas_texture
    assert manager.get_region_parent("hero") == "atlas"
    assert manager.get_region_parent("coin") == "atlas"

    hero_rect = manager.get_source_rect("hero")
    coin_rect = manager.get_source_rect("coin")
    assert hero_rect is not None and coin_rect is not None
    assert hero_rect[2:] == (64.0, 64.0)
    assert coin_rect[2:] == (32.0, 32.0)
    assert rects_are_disjoint(hero_rect, coin_rect, padding=2.0)
    assert manager.get_texture_data("atlas").source_rect == (0.0, 0.0, 98.0, 64.0)

    # The page is cropped to content: 64 + 2 padding + 32 = 98 wide, 64 tall.
    assert loader.created_images == [(98, 64)]
    # The old textures are unloaded exactly once; the page is not included.
    assert sorted(loader.unloaded_textures) == ["coin", "hero"]


def test_atlas_remaps_spritesheet_regions(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("sheet", 64, 64))
    inject_region(manager, "sheet", "tile", (16, 16, 16, 16))

    page_ids = manager.build_texture_atlas()

    assert page_ids == ["atlas"]
    atlas_texture = manager.get_asset("atlas")
    assert manager.get_asset("tile") is atlas_texture
    assert manager.get_source_rect("sheet") == (0.0, 0.0, 64.0, 64.0)
    assert manager.get_source_rect("tile") == (16.0, 16.0, 16.0, 16.0)
    assert manager.get_region_parent("tile") == "atlas"
    assert manager._regions["atlas"] == {"sheet", "tile"}
    assert "sheet" not in manager._regions
    assert loader.unloaded_textures == ["sheet"]


def test_atlas_skips_oversized_assets(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    big = FakeTexture("big", 4096, 4096)
    inject_asset(manager, big)
    inject_asset(manager, FakeTexture("coin", 32, 32))

    page_ids = manager.build_texture_atlas(max_size=2048)

    assert page_ids == ["atlas"]
    assert manager.get_asset("big") is big
    assert manager.get_region_parent("big") == "big"
    assert manager.get_source_rect("big") == (0.0, 0.0, 4096.0, 4096.0)
    assert "big" not in loader.unloaded_textures
    assert loader.unloaded_textures == ["coin"]


def test_atlas_creates_multiple_pages(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("a", 100, 50))
    inject_asset(manager, FakeTexture("b", 100, 50))
    inject_asset(manager, FakeTexture("c", 100, 50))

    page_ids = manager.build_texture_atlas(max_size=128)

    assert page_ids == ["atlas", "atlas_2"]
    atlas_texture = manager.get_asset("atlas")
    atlas_2_texture = manager.get_asset("atlas_2")
    assert atlas_texture is not atlas_2_texture
    assert manager.get_asset("a") is atlas_texture
    assert manager.get_asset("b") is atlas_texture
    assert manager.get_asset("c") is atlas_2_texture
    assert loader.unloaded_textures == ["a", "b", "c"]


def test_atlas_explicit_ids_pack_subset(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    hero = FakeTexture("hero", 64, 64)
    coin = FakeTexture("coin", 32, 32)
    inject_asset(manager, hero)
    inject_asset(manager, coin)

    page_ids = manager.build_texture_atlas(["hero"])

    assert page_ids == ["atlas"]
    assert manager.get_asset("hero") is manager.get_asset("atlas")
    assert manager.get_asset("coin") is coin
    assert manager.get_region_parent("coin") == "coin"
    assert loader.unloaded_textures == ["hero"]


def test_atlas_region_id_packs_parent_sheet(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("sheet", 64, 64))
    inject_region(manager, "sheet", "tile", (0, 0, 16, 16))

    page_ids = manager.build_texture_atlas(["tile"])

    assert page_ids == ["atlas"]
    assert manager.get_region_parent("tile") == "atlas"
    assert manager.get_source_rect("tile") == (0.0, 0.0, 16.0, 16.0)


def test_atlas_unknown_id_raises(isolated_registry: pu.UnitRegistry) -> None:
    _ = isolated_registry
    manager = make_manager(AtlasDummyLoader())
    with pytest.raises(KeyError, match="ghost"):
        manager.build_texture_atlas(["ghost"])


def test_atlas_empty_cache_returns_no_pages(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    manager = make_manager(AtlasDummyLoader())
    assert manager.build_texture_atlas() == []


def test_atlas_second_call_does_not_repack_pages(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("hero", 64, 64))

    first = manager.build_texture_atlas()
    second = manager.build_texture_atlas()

    assert first == ["atlas"]
    assert second == []
    assert loader.unloaded_textures == ["hero"]
    assert manager.get_region_parent("hero") == "atlas"


def test_atlas_page_id_avoids_collision(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("atlas", 32, 32))

    page_ids = manager.build_texture_atlas()

    assert page_ids == ["atlas_2"]
    assert manager.get_region_parent("atlas") == "atlas_2"
    assert manager.get_asset("atlas") is manager.get_asset("atlas_2")


def test_atlas_remaps_animation_frames(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    tall = FakeTexture("tall", 64, 100)
    sheet = FakeTexture("sheet", 64, 64)
    inject_asset(manager, tall)
    inject_asset(manager, sheet)
    inject_region(manager, "sheet", "tile", (16, 16, 16, 16))

    animations = Animations()
    clip = AnimationClip(
        name="run",
        frames=[
            AnimationFrame(asset_id="tile", source_rect=(0, 0, 8, 8), duration=0.1),
            AnimationFrame(asset_id="tile", duration=0.1),
            AnimationFrame(asset_id="tall", duration=0.1),
            AnimationFrame(texture=sheet, source_rect=(16, 16, 16, 16), duration=0.1),
        ],
    )
    animations.add_clip(clip)

    manager.build_texture_atlas(max_size=256)

    # tall (64x100) in the first shelf; sheet (64x64) beside it at x=66.
    assert manager.get_source_rect("sheet") == (66.0, 0.0, 64.0, 64.0)

    frame_id_rect = clip.frames[0].source_rect
    assert frame_id_rect == (66.0, 0.0, 8.0, 8.0)
    # Frames without source_rect stay None (lazy resolution via get_source_rect).
    assert clip.frames[1].source_rect is None
    assert clip.frames[2].source_rect is None

    texture_frame = clip.frames[3]
    assert texture_frame.texture is manager.get_asset("atlas")
    assert texture_frame.source_rect == (82.0, 16.0, 16.0, 16.0)


def test_atlas_destroy_unloads_each_page_once(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    inject_asset(manager, FakeTexture("hero", 64, 64))
    inject_asset(manager, FakeTexture("coin", 32, 32))
    manager.build_texture_atlas()

    loader.unloaded_textures.clear()
    manager.destroy()

    assert loader.unloaded_textures == ["page:98x64"]
    assert manager._textures == {}
    assert manager._atlases == set()


class RecordingRenderer(pu.ServiceUnit):
    def __init__(self) -> None:
        super().__init__(name="Renderer", tags={"service", "renderer"})
        self.calls: list[dict] = []

    def render_sprite(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_render_sends_region_source_rect(
    isolated_registry: pu.UnitRegistry,
) -> None:
    _ = isolated_registry
    loader = AtlasDummyLoader()
    manager = make_manager(loader)
    renderer = RecordingRenderer()
    inject_asset(manager, FakeTexture("hero", 64, 64))
    inject_region(manager, "hero", "tile", (16, 16, 16, 16))

    manager.render("tile", z=0, layer=0)
    assert renderer.calls[0]["source"] == (16.0, 16.0, 16.0, 16.0)

    manager.build_texture_atlas()
    renderer.calls.clear()
    manager.render("tile", z=0, layer=0)
    call = renderer.calls[0]
    assert call["texture"] is manager.get_asset("atlas")
    assert call["source"] == (16.0, 16.0, 16.0, 16.0)

    # An explicit override is still respected.
    renderer.calls.clear()
    manager.render("tile", z=0, layer=0, source=(0, 0, 8, 8))
    assert renderer.calls[0]["source"] == (0, 0, 8, 8)
