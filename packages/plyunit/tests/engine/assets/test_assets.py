"""Dedicated resource handles, image editing, and upload failure regressions."""

from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from asset_fakes import FakeGPU, FakeImages, RawImage
from plyunit._enums import TextureFilter, TextureWrap
from plyunit.backends.integrations.raylib.assets import Assets, ImageProcessor
from plyunit.backends.integrations.raylib.handler import (
    Font,
    Image,
    RenderTexture,
    Shader,
)
from plyunit.backends.ports.assets import IImageProcessor
from plyunit.backends.ports.handler import (
    FontHandle,
    ImageHandle,
    RenderTextureHandle,
    ShaderHandle,
    Texture2DHandle,
)
from plyunit.services.assets.schemas import TextureProperty


def test_image_handle_reads_live_size_and_format() -> None:
    raw = RawImage(8, 4)
    image = Image(raw)
    assert isinstance(image, ImageHandle)
    raw.width, raw.height, raw.format = 4, 8, 3
    assert (image.width, image.height, image.format_id) == (4, 8, 3)


def test_render_texture_attachment_is_cached_and_raw_accessor_is_safe(
    gpu: FakeGPU,
) -> None:
    raw = gpu.texture("target", 32, 16).raw_texture
    target = RenderTexture(SimpleNamespace(texture=raw))
    assert isinstance(target, RenderTextureHandle)
    assert target.raw_texture is raw
    assert target.texture is target.texture
    assert target.texture.raw_texture is raw
    assert (target.width, target.height) == (32, 16)
    with pytest.raises(FrozenInstanceError):
        target.raw_render_texture = None


def test_shader_exposes_only_canonical_fields() -> None:
    raw = object()
    first = Shader.from_raw(raw)
    second = Shader.from_raw(raw)
    assert isinstance(first, ShaderHandle)
    assert first.raw_shader is raw
    first.locations["time"] = 4
    assert second.locations == {}
    assert first is not second
    assert not hasattr(first, "raw")
    assert not hasattr(first, "_locations")


@pytest.mark.parametrize("missing", ["texture", "base_size", "glyph_count"])
def test_font_protocol_requires_portable_metrics_and_atlas(missing: str) -> None:
    attributes = {
        "texture": object(),
        "base_size": 16,
        "glyph_count": 96,
    }
    assert isinstance(SimpleNamespace(**attributes), FontHandle)
    del attributes[missing]
    assert not isinstance(SimpleNamespace(**attributes), FontHandle)


def test_font_exposes_canonical_resource_and_stable_borrowed_atlas(
    manager: Assets, gpu: FakeGPU,
) -> None:
    raw_texture = gpu.texture("font-atlas", 32, 16).raw_texture
    raw_font = SimpleNamespace(texture=raw_texture, baseSize=16, glyphCount=96)
    font = Font.from_raw(raw_font, texture_id="font:default")
    assert isinstance(font, FontHandle)
    assert font.raw_font is raw_font
    assert font.base_size == 16
    assert font.glyph_count == 96
    assert isinstance(font.texture, Texture2DHandle)
    assert font.texture is font.texture
    assert font.texture.raw_texture is raw_texture
    assert font.texture.texture_id == font.texture.parent_id == "font:default"
    assert font.texture.source_rect == (0.0, 0.0, 32.0, 16.0)
    assert (font.texture.width, font.texture.height) == (32, 16)
    with pytest.raises(ValueError, match="borrowed"):
        manager.store_texture("font-atlas", font.texture)
    assert gpu.unloaded == []


@pytest.mark.parametrize("property_name", ["texture", "base_size", "glyph_count"])
def test_released_font_rejects_resource_access(
    gpu: FakeGPU, property_name: str,
) -> None:
    raw_texture = gpu.texture("font-atlas", 32, 16).raw_texture
    raw_font = SimpleNamespace(texture=raw_texture, baseSize=16, glyphCount=96)
    font = Font.from_raw(raw_font)
    font._valid = False
    font.raw_font = None
    with pytest.raises(ValueError, match="released"):
        getattr(font, property_name)
    assert raw_font.texture is raw_texture
    assert not raw_texture.unloaded


def test_texture_settings_respect_explicit_false() -> None:
    defaults = TextureProperty(mipmap=True, srgb=True, premultiply_alpha=True)
    prop = TextureProperty.from_dict(
        {"mipmap": False, "srgb": False, "premultiply_alpha": False}, default=defaults
    )
    assert (prop.mipmap, prop.srgb, prop.premultiply_alpha) == (False, False, False)
    assert defaults.mipmap and defaults.srgb and defaults.premultiply_alpha
    assert prop is not defaults


def test_texture_settings_round_trip_and_inheritance() -> None:
    defaults = TextureProperty(
        filter=TextureFilter.TRILINEAR, wrap=TextureWrap.MIRROR_REPEAT
    )
    assert (
        TextureProperty.from_dict({"srgb": False}, default=defaults).filter
        is TextureFilter.TRILINEAR
    )
    assert TextureProperty.from_dict(defaults.to_dict()) == defaults


@pytest.mark.parametrize(
    "settings",
    [
        {"filter": "unknown"},
        {"wrap": "unknown"},
        {"color_key": [0, 0]},
        {"color_key": [256, 0, 0, 0]},
    ],
)
def test_invalid_texture_settings_fail_explicitly(settings: dict) -> None:
    with pytest.raises(ValueError):
        TextureProperty.from_dict(settings)


def test_texture_validation_uses_enum_keys(manager: Assets, gpu: FakeGPU) -> None:
    for filter_mode in TextureFilter:
        for wrap_mode in TextureWrap:
            manager.load_from_image(
                f"{filter_mode.name}-{wrap_mode.name}",
                Image(RawImage(8, 4)),
                texture=TextureProperty(
                    filter=filter_mode, wrap=wrap_mode, mipmap=True
                ),
            )
    assert len(gpu.textures) == len(TextureFilter) * len(TextureWrap)
    assert [call[0] for call in gpu.calls[:4]] == [
        "upload",
        "mipmaps",
        "filter",
        "wrap",
    ]


def test_file_loading_prepares_and_releases_cpu_image(
    manager: Assets, images: FakeImages, tmp_path: Path
) -> None:
    (tmp_path / "hero.png").touch()
    manager.set_default_texture(TextureProperty(premultiply_alpha=True))
    manager.load_asset("hero.png")
    assert images.filters == [{"replace_color": ((0, 0, 0, 255), (0, 0, 0, 0))}]
    assert images.alpha == [{"premultiply": True}]
    assert len(images.unloaded) == 1


def test_staged_upload_does_not_prepare_caller_pixels(
    manager: Assets, images: FakeImages
) -> None:
    image = Image(RawImage(8, 4))
    manager.load_from_image(
        "staged", image, texture=TextureProperty(premultiply_alpha=True)
    )
    assert not image.raw_image.unloaded
    assert images.filters == [] and images.alpha == []
    manager.load_from_image("owned", image, take_ownership=True)
    assert image.raw_image.unloaded


@pytest.mark.parametrize("take_ownership", [True, False])
def test_upload_setup_failure_reclaims_vram_and_respects_cpu_ownership(
    manager: Assets, images: FakeImages, gpu: FakeGPU, take_ownership: bool
) -> None:
    gpu.filter_error = True
    image = Image(RawImage(8, 4))
    with pytest.raises(RuntimeError, match="filter failed"):
        manager.load_from_image("broken", image, take_ownership=take_ownership)
    assert len(gpu.unloaded) == 1
    assert image.raw_image.unloaded is take_ownership
    assert manager.all_assets == {}


def test_invalid_gpu_upload_is_not_cached(manager: Assets, gpu: FakeGPU) -> None:
    gpu.upload_valid = False
    image = Image(RawImage(8, 4))
    with pytest.raises(ValueError, match="upload texture"):
        manager.load_from_image("broken", image, take_ownership=True)
    assert image.raw_image.unloaded
    assert len(gpu.unloaded) == 1
    assert manager.all_assets == {}


def test_failed_decode_preserves_previous_asset(
    manager: Assets, images: FakeImages, gpu: FakeGPU, tmp_path: Path
) -> None:
    manager.store_texture("hero", gpu.texture("old", 8, 8))
    old = manager["hero"]
    images.decode_valid = False
    (tmp_path / "hero.png").touch()
    with pytest.raises(ValueError):
        manager.load_asset("hero.png")
    assert manager["hero"] is old
    assert gpu.unloaded == []
    assert len(images.unloaded) == 1


def test_memory_loading_normalizes_suffix_and_releases_image(
    manager: Assets, images: FakeImages
) -> None:
    manager.load_from_memory("embedded", b"png", "PNG")
    assert images.memory == [(b"png", ".png")]
    assert images.created[-1].unloaded
    with pytest.raises(ValueError, match="empty"):
        manager.load_from_memory("empty", b"", ".png")


def test_solid_color_upload_preserves_color_without_color_key(
    manager: Assets, images: FakeImages
) -> None:
    manager.create_solid_color("solid", 8, 4, (0, 0, 0, 255))
    assert manager["solid"].source_rect == (0.0, 0.0, 8.0, 4.0)
    assert images.filters == []
    assert images.created[-1].unloaded
    with pytest.raises(ValueError):
        manager.create_solid_color("empty", 0, 4, (0, 0, 0, 0))


def test_copy_and_update_region_keep_dedicated_handles(
    manager: Assets, images: FakeImages, gpu: FakeGPU
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 16, 16))
    manager._put(
        manager["sheet"].derive(
            texture_id="tile", parent_id="sheet", source_rect=(4.0, 4.0, 8.0, 8.0)
        )
    )
    image = manager.copy_image("tile")
    assert isinstance(image, Image)
    assert (image.width, image.height) == (8, 8)
    assert not image.raw_image.unloaded
    manager.update_from_image("tile", image)
    call = gpu.calls[-1]
    assert call[0] == "update"
    assert call[1] is manager["sheet"].raw_texture
    assert (call[2].x, call[2].y, call[2].width, call[2].height) == (4.0, 4.0, 8.0, 8.0)
    assert call[3] == image.raw_image.data
    assert not image.raw_image.unloaded
    images.unload_image(image)


@pytest.mark.parametrize("mode", ["crop", "invalid"])
def test_failed_readback_releases_cpu_image(
    manager: Assets, images: FakeImages, gpu: FakeGPU, mode: str
) -> None:
    manager.store_texture("sheet", gpu.texture("sheet", 16, 16))
    manager._put(
        manager["sheet"].derive(
            texture_id="tile", parent_id="sheet", source_rect=(4.0, 4.0, 8.0, 8.0)
        )
    )
    images.crop_error = mode == "crop"
    images.readback_valid = mode != "invalid"
    with pytest.raises((RuntimeError, ValueError)):
        manager.copy_image("tile")
    assert images.created[-1].unloaded


@pytest.mark.parametrize(
    "raw", [RawImage(7, 8), RawImage(8, 8, format=3), RawImage(8, 8, valid=False)]
)
def test_update_rejects_incompatible_or_invalid_pixels(
    manager: Assets, gpu: FakeGPU, raw: RawImage
) -> None:
    manager.store_texture("asset", gpu.texture("asset", 8, 8))
    with pytest.raises(ValueError):
        manager.update_from_image("asset", Image(raw))
    assert not any(call[0] == "update" for call in gpu.calls)


def test_image_processor_unwraps_handles_and_runs_operations_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("plyunit.backends.integrations.raylib.assets")
    native = MagicMock()
    monkeypatch.setattr(module, "pr", native)
    processor = ImageProcessor()
    assert isinstance(processor, IImageProcessor)
    raw = RawImage(8, 4)
    mask = Image(RawImage(8, 4))
    image = Image(raw)
    processor.transform(
        image,
        crop_rect=(0, 0, 4, 4),
        resize=(16, 8),
        flip_h=True,
        flip_v=True,
        rotate_deg=450,
        to_pot=True,
    )
    assert [call[0] for call in native.method_calls] == [
        "image_crop",
        "image_resize",
        "image_flip_horizontal",
        "image_flip_vertical",
        "image_rotate_cw",
        "image_to_pot",
    ]
    for call in native.method_calls:
        assert call.args[0] is raw
    native.reset_mock()
    processor.apply_filters(
        image,
        replace_color=((0, 0, 0, 255), (0, 0, 0, 0)),
        tint=(255, 255, 255, 255),
        invert=True,
        brightness=2,
        contrast=3,
        grayscale=True,
        blur=1,
    )
    assert [call[0] for call in native.method_calls] == [
        "image_color_replace",
        "image_color_tint",
        "image_color_invert",
        "image_color_brightness",
        "image_color_contrast",
        "image_color_grayscale",
        "image_blur_gaussian",
    ]
    native.reset_mock()
    processor.apply_alpha(
        image,
        premultiply=True,
        clear_threshold=0.1,
        crop_threshold=0.2,
        mask_image=mask,
    )
    assert [call[0] for call in native.method_calls] == [
        "image_alpha_premultiply",
        "image_alpha_clear",
        "image_alpha_crop",
        "image_alpha_mask",
    ]
    native.image_alpha_mask.assert_called_once_with(raw, mask.raw_image)


@pytest.mark.parametrize(
    "mode, operation",
    [
        ("nn", "image_resize_nn"),
        ("canvas", "image_resize_canvas"),
        ("bilinear", "image_resize"),
    ],
)
def test_image_processor_resize_modes(
    monkeypatch: pytest.MonkeyPatch, mode: str, operation: str
) -> None:
    module = importlib.import_module("plyunit.backends.integrations.raylib.assets")
    native = MagicMock()
    monkeypatch.setattr(module, "pr", native)
    ImageProcessor().transform(Image(RawImage(8, 4)), resize=(16, 8), resize_mode=mode)
    assert [call[0] for call in native.method_calls] == [operation]


def test_image_processor_rejects_bad_resize_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("plyunit.backends.integrations.raylib.assets")
    native = MagicMock()
    monkeypatch.setattr(module, "pr", native)
    with pytest.raises(ValueError, match="resize mode"):
        ImageProcessor().transform(
            Image(RawImage(8, 4)), resize=(16, 8), resize_mode="unknown"
        )
    assert native.method_calls == []
