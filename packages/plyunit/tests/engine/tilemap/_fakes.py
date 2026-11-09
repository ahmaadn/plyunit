"""Headless resource handles and canvas operations for tilemap tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

from plyunit._enums import TextureFilter
from plyunit.backends.ports.assets import IAssets
from plyunit.backends.ports.handler import (
    RenderTextureHandle,
    Texture2DHandle,
    TextureTarget,
)
from plyunit.core.types import RectType
from plyunit.services.assets.schemas import TextureProperty
from plyunit.tilemap.tile_geometry import tile_is_oversized
from plyunit.tilemap.tilemap import _GidEntry


@dataclass(frozen=True, slots=True)
class FakeTexture2D:
    """Provide logical texture metadata while rejecting raw resource access."""

    texture_id: str
    width: int
    height: int
    source_rect: RectType
    parent_id: str
    metadata: TextureProperty = field(default_factory=TextureProperty)
    format_id: int = 0

    @property
    def raw_texture(self) -> object:
        """Reject backend-only resource access in neutral tilemap code."""
        raise AssertionError("Tilemap must not inspect a raw texture")

    def derive(
        self, *, texture_id: str, parent_id: str, source_rect: RectType
    ) -> FakeTexture2D:
        """Return a region handle sharing this texture's metadata.

        Args:
            texture_id: Logical cache key for the derived handle.
            parent_id: Logical key of the owning texture.
            source_rect: Region in whole-texture coordinates.

        Returns:
            A new handle without changing the original.
        """
        return replace(
            self,
            texture_id=texture_id,
            parent_id=parent_id,
            source_rect=source_rect,
        )


def make_texture(
    texture_id: str,
    width: int = 16,
    height: int = 16,
    *,
    parent_id: str | None = None,
    source_rect: RectType | None = None,
) -> FakeTexture2D:
    """Create a texture handle without allocating GPU resources.

    Args:
        texture_id: Logical cache key, never a numeric GPU identifier.
        width: Width of the entire texture.
        height: Height of the entire texture.
        parent_id: Owning texture's key; defaults to the handle's key.
        source_rect: Region to draw; defaults to the entire texture.

    Returns:
        A root or region handle with opaque raw-resource properties.
    """
    return FakeTexture2D(
        texture_id=texture_id,
        width=width,
        height=height,
        source_rect=source_rect or (0.0, 0.0, float(width), float(height)),
        parent_id=texture_id if parent_id is None else parent_id,
    )


@dataclass(frozen=True, slots=True)
class FakeRenderTexture:
    """Expose a borrowed texture attachment without any raw struct fields."""

    texture: Texture2DHandle

    @property
    def width(self) -> int:
        """Return the render target's width in pixels."""
        return self.texture.width

    @property
    def height(self) -> int:
        """Return the render target's height in pixels."""
        return self.texture.height

    @property
    def raw_render_texture(self) -> object:
        """Reject backend-only target access."""
        raise AssertionError("Tilemap must not inspect a raw render target")

    @property
    def raw_texture(self) -> object:
        """Reject backend-only attachment access."""
        raise AssertionError("Tilemap must not inspect a raw attachment")


class FakeCanvas:
    """Record the canvas port operations used by tilemap baking."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.loads: list[tuple[int, int]] = []
        self.draws: list[tuple[Texture2DHandle, RectType, RectType]] = []
        self.unloaded: list[RenderTextureHandle] = []
        self.active_target: RenderTextureHandle | None = None

    def load_render_texture(self, width: int, height: int) -> FakeRenderTexture:
        self.calls.append(("load", width, height))
        self.loads.append((width, height))
        return FakeRenderTexture(make_texture(f"bake-{len(self.loads)}", width, height))

    def unload_render_texture(self, target: RenderTextureHandle) -> None:
        assert target is not self.active_target
        self.calls.append(("unload", target))
        self.unloaded.append(target)

    def begin_texture_mode(self, target: RenderTextureHandle) -> None:
        assert self.active_target is None
        self.calls.append(("begin", target))
        self.active_target = target

    def end_texture_mode(self) -> None:
        assert self.active_target is not None
        self.calls.append(("end",))
        self.active_target = None

    def clear_background(self, color: tuple[int, int, int, int]) -> None:
        assert self.active_target is not None
        self.calls.append(("clear", color))

    def draw_texture_region(
        self, texture: Texture2DHandle, source: RectType, dest: RectType
    ) -> None:
        assert self.active_target is not None
        assert isinstance(texture, Texture2DHandle)
        self.calls.append(("draw", texture, source, dest))
        self.draws.append((texture, source, dest))

    def gen_mipmaps(self, target: TextureTarget) -> None:
        self.calls.append(("mipmap", target))

    def set_texture_filter(
        self,
        target: TextureTarget,
        filter_mode: TextureFilter = TextureFilter.TRILINEAR,
    ) -> None:
        assert isinstance(filter_mode, TextureFilter)
        self.calls.append(("filter", target, filter_mode))


def make_assets(textures: Mapping[str, Texture2DHandle]) -> MagicMock:
    """Return an asset-port fake with strict missing-key behavior.

    Args:
        textures: The logical cache read by ``get_asset``.

    Returns:
        A mock limited to the new asset port, with no compatibility methods.
    """
    assets = MagicMock(spec_set=IAssets)
    assets.get_asset.side_effect = textures.__getitem__
    return assets


def gid_entry(texture: Texture2DHandle, tile_size: int = 16) -> _GidEntry:
    """Build a real GID entry from an opaque test handle.

    Args:
        texture: Root or region handle to submit.
        tile_size: Size of the grid cell in pixels.

    Returns:
        A domain entry with oversized geometry computed from its region.
    """
    source = texture.source_rect
    return _GidEntry(
        texture=texture,
        source_rect=source,
        asset_id=texture.texture_id,
        oversized=tile_is_oversized(tile_size, source[2], source[3]),
    )
