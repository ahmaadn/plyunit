"""Stateful image and GPU test doubles for the dedicated raylib asset API."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from plyunit.backends.integrations.raylib.handler import Image, Texture2D


@dataclass(eq=False)
class RawImage:
    width: int
    height: int
    name: str = "image"
    format: int = 7
    data: bytes = b"pixels"
    valid: bool = True
    unloaded: bool = False


@dataclass(eq=False)
class RawTexture:
    id: int
    width: int
    height: int
    name: str
    format: int = 7
    mipmaps: int = 1
    valid: bool = True
    unloaded: bool = False


class FakeImages:
    """Record image processing while enforcing live CPU-image ownership."""

    def __init__(self) -> None:
        self.loaded: list[Path] = []
        self.created: list[RawImage] = []
        self.unloaded: list[RawImage] = []
        self.drawn: list[tuple[str, tuple[int, int]]] = []
        self.filters: list[dict] = []
        self.alpha: list[dict] = []
        self.memory: list[tuple[bytes, str]] = []
        self.dimensions = (100, 100)
        self.decode_valid = True
        self.readback_valid = True
        self.crop_error = False
        self.blit_error = False

    def _image(self, width: int, height: int, name: str) -> Image:
        raw = RawImage(width, height, name)
        self.created.append(raw)
        return Image(raw)

    def load_image(self, path: str | Path) -> Image:
        self.loaded.append(Path(path))
        image = self._image(*self.dimensions, Path(path).name)
        image.raw_image.valid = self.decode_valid
        return image

    def load_image_from_memory(self, data: bytes, file_type: str) -> Image:
        self.memory.append((data, file_type))
        image = self._image(*self.dimensions, "memory")
        image.raw_image.valid = self.decode_valid
        return image

    def load_image_from_texture(self, texture: Texture2D) -> Image:
        assert not texture.raw_texture.unloaded
        image = self._image(texture.width, texture.height, texture.raw_texture.name)
        image.raw_image.valid = self.readback_valid
        return image

    def gen_image_color(self, width: int, height: int, color=(0, 0, 0, 0)) -> Image:
        return self._image(width, height, f"canvas:{width}x{height}")

    def copy_image(self, image: Image) -> Image:
        raw = copy(image.raw_image)
        raw.unloaded = False
        self.created.append(raw)
        return Image(raw)

    def unload_image(self, image: Image | None) -> None:
        if image is not None:
            assert not image.raw_image.unloaded, "CPU image unloaded twice"
            image.raw_image.unloaded = True
            self.unloaded.append(image.raw_image)

    def is_image_valid(self, image: Image) -> bool:
        return image.raw_image.valid and not image.raw_image.unloaded

    def get_color(self, image: Image, x: int, y: int):
        return (255, 255, 255, 255)

    def get_alpha_border(self, image: Image, threshold: float):
        return (0.0, 0.0, float(image.width), float(image.height))

    def blit(self, dst: Image, src: Image, pos: tuple[int, int]) -> None:
        assert self.is_image_valid(dst) and self.is_image_valid(src)
        if self.blit_error:
            raise RuntimeError("blit failed")
        self.drawn.append((src.raw_image.name, pos))

    def transform(self, image: Image, *, crop_rect=None, **kwargs) -> None:
        if self.crop_error:
            raise RuntimeError("crop failed")
        if crop_rect is not None:
            image.raw_image.width = int(crop_rect[2])
            image.raw_image.height = int(crop_rect[3])

    def apply_filters(self, image: Image, **kwargs) -> None:
        self.filters.append(kwargs)

    def apply_alpha(self, image: Image, **kwargs) -> None:
        self.alpha.append(kwargs)


@dataclass
class FakeGPU:
    """Track allocations and reject double unload or use-after-unload calls."""

    textures: list[RawTexture] = field(default_factory=list)
    unloaded: list[RawTexture] = field(default_factory=list)
    calls: list[tuple] = field(default_factory=list)
    upload_valid: bool = True
    fail_upload_at: int | None = None
    upload_count: int = 0
    filter_error: bool = False

    def texture(self, name: str, width: int, height: int) -> Texture2D:
        raw = RawTexture(len(self.textures) + 1, width, height, name)
        self.textures.append(raw)
        return Texture2D.from_raw(raw)

    def upload(self, image: RawImage) -> RawTexture:
        assert not image.unloaded
        self.upload_count += 1
        if self.fail_upload_at == self.upload_count:
            raise RuntimeError("upload failed")
        raw = self.texture(
            f"page:{image.width}x{image.height}", image.width, image.height
        ).raw_texture
        raw.valid = self.upload_valid
        self.calls.append(("upload", raw))
        return raw

    def unload(self, raw: RawTexture) -> None:
        assert not raw.unloaded, "GPU texture unloaded twice"
        raw.unloaded = True
        self.unloaded.append(raw)
        self.calls.append(("unload", raw))

    def is_valid(self, raw: RawTexture) -> bool:
        return raw.valid and not raw.unloaded

    def set_filter(self, raw: RawTexture, mode: int) -> None:
        assert not raw.unloaded
        if self.filter_error:
            raise RuntimeError("filter failed")
        self.calls.append(("filter", raw, mode))

    def set_wrap(self, raw: RawTexture, mode: int) -> None:
        assert not raw.unloaded
        self.calls.append(("wrap", raw, mode))

    def mipmaps(self, raw: RawTexture) -> None:
        assert not raw.unloaded
        raw.mipmaps += 1
        self.calls.append(("mipmaps", raw))

    def update(self, raw: RawTexture, rect, data) -> None:
        assert not raw.unloaded
        self.calls.append(("update", raw, rect, data))

    def native_module(self) -> MagicMock:
        native = MagicMock()
        native.load_texture_from_image.side_effect = self.upload
        native.unload_texture.side_effect = self.unload
        native.is_texture_valid.side_effect = self.is_valid
        native.set_texture_filter.side_effect = self.set_filter
        native.set_texture_wrap.side_effect = self.set_wrap
        native.gen_texture_mipmaps.side_effect = self.mipmaps
        native.update_texture_rec.side_effect = self.update
        native.Rectangle.side_effect = lambda x, y, width, height: SimpleNamespace(
            x=x, y=y, width=width, height=height
        )
        return native
