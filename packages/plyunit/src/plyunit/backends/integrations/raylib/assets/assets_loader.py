"""Texture/image loader backed by raylib's C API via the cffi binding."""

import logging
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import pyray as pr
import raylib as rl

from plyunit.assets.types import ImageData, TextureProperty
from plyunit.core.types import ColorType, Texture

__all__ = (
    "FILTER_MODE_MAP",
    "WRAP_MODE_MAP",
    "apply_image_filters",
    "default",
    "gen_image_color",
    "gen_texture_mipmaps",
    "get_image_alpha_border",
    "get_image_color",
    "image_draw",
    "is_image_valid",
    "is_texture_valid",
    "load_image",
    "load_image_from_texture",
    "load_texture",
    "load_texture_from_dict",
    "load_texture_from_image",
    "process_image_alpha",
    "set_default_config_texture",
    "set_texture_filter",
    "set_texture_wrap",
    "transform_image",
    "unload_image",
    "unload_texture",
    "update_texture",
    "update_texture_rec",
)

logger = logging.getLogger(__name__)


# Texture filter mode mapping
FILTER_MODE_MAP = {
    "nearest": rl.TEXTURE_FILTER_POINT,
    "linear": rl.TEXTURE_FILTER_BILINEAR,
}

# Texture wrap mode mapping
WRAP_MODE_MAP = {
    "clamp": rl.TEXTURE_WRAP_CLAMP,
    "mirror": rl.TEXTURE_WRAP_MIRROR_CLAMP,
    "repeat": rl.TEXTURE_WRAP_REPEAT,
}

default = TextureProperty(
    filter="nearest",
    wrap="clamp",
    mipmap=False,
    srgb=True,
    premultiply_alpha=False,
    color_key=(0, 0, 0, 255),
)


def set_default_config_texture(
    *,
    filter_mode: Literal["nearest", "linear"] = "nearest",
    wrap_mode: Literal["repeat", "clamp", "mirror"] = "clamp",
    mipmap: bool = False,
    premultiply_alpha: bool = False,
    color_key: tuple[int, int, int, int] | None = None,
) -> None:
    """Set default parameters for texture loading.

    Args:
        filter_mode: Default texture filter mode.
        wrap_mode: Default texture wrap mode.
        mipmap: Whether to generate mipmaps by default.
        premultiply_alpha: Whether to pre-multiply the alpha channel by default.
        color_key: Default key color (RGBA); None = leave unchanged.
    """
    default.filter = filter_mode
    default.wrap = wrap_mode
    default.mipmap = mipmap
    default.premultiply_alpha = premultiply_alpha

    if (
        color_key is not None
        and isinstance(color_key, (tuple, list))
        and len(color_key) == 4
    ):
        default.color_key = tuple(color_key)  # type: ignore[assignment]

    logger.info(f"Default texture parameters updated: {asdict(default)}")


# ------------------------------------------------------------------ #
# Texture configuration
# ------------------------------------------------------------------ #
def set_texture_filter(texture: Any, filter_mode: str) -> None:
    """Apply a filter mode to a texture.

    Args:
        texture: The texture to filter.
        filter_mode: Filter mode ("nearest" or "linear").

    Raises:
        ValueError: If filter_mode is invalid.
    """
    if filter_mode not in FILTER_MODE_MAP:
        logger.error(f"Mode filter tidak dikenal {filter_mode!r}")
        raise ValueError(f"Mode filter tidak dikenal {filter_mode!r}")

    rl.SetTextureFilter(texture, FILTER_MODE_MAP[filter_mode])
    logger.debug(f"Filter mode '{filter_mode}' diterapkan")


def set_texture_wrap(texture: Any, wrap_mode: str) -> None:
    """Apply a wrap mode to a texture.

    Args:
        texture: The texture to set the wrap mode on.
        wrap_mode: Wrap mode ("clamp", "mirror", or "repeat").

    Raises:
        ValueError: If wrap_mode is invalid.
    """
    if wrap_mode not in WRAP_MODE_MAP:
        logger.error(f"Mode wrap tidak dikenal '{wrap_mode}'")
        raise ValueError(f"Mode wrap tidak dikenal '{wrap_mode}'")

    rl.SetTextureWrap(texture, WRAP_MODE_MAP[wrap_mode])
    logger.debug(f"Wrap mode '{wrap_mode}' diterapkan")


def gen_texture_mipmaps(texture: Texture) -> None:
    """Generate mipmaps for a texture (mutates the texture in place)."""
    rl.GenTextureMipmaps(texture)


def load_image(path: str | Path) -> Any:
    """Load a CPU-side image from a file.

    Args:
        path: Path to the image file.

    Returns:
        A raylib image handle.
    """
    return pr.load_image(str(path))


def unload_image(image: Any) -> None:
    """Unload a CPU-side image from memory (no-op if None)."""
    if image is not None:
        pr.unload_image(image)


def is_image_valid(image: Any) -> bool:
    """Return ``True`` if the image handle is still valid."""
    return rl.IsImageValid(image)


def gen_image_color(width: int, height: int, color: ColorType = (0, 0, 0, 0)) -> Any:
    """Create a plain CPU-side image of ``width x height`` filled with a solid color.

    Used to prepare in-memory texture atlas canvases.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: RGBA fill color (default fully transparent).

    Returns:
        A raylib image handle.
    """
    return pr.gen_image_color(int(width), int(height), pr.Color(*color))


def load_image_from_texture(texture: Texture) -> Any:
    """Copy pixels from a GPU texture into a CPU-side image (readback).

    Args:
        texture: The texture to read back.

    Returns:
        A raylib image handle holding a copy of the texture's pixels.
    """
    # pyrefly: ignore [bad-argument-type]
    return rl.LoadImageFromTexture(texture)


def image_draw(dst: Any, src: Any, pos: tuple[int, int]) -> None:
    """Blit image ``src`` onto image ``dst`` at position ``(x, y)`` without scaling.

    Args:
        dst: Destination image (mutated in place).
        src: Source image.
        pos: Top-left corner position in the destination image.
    """
    pr.image_draw(
        dst,
        src,
        pr.Rectangle(0, 0, src.width, src.height),
        pr.Rectangle(int(pos[0]), int(pos[1]), src.width, src.height),
        pr.WHITE,
    )


def transform_image(
    image: Any,
    *,
    crop_rect: Any | None = None,
    resize: tuple[int, int] | None = None,
    resize_mode: Literal["bilinear", "nn", "canvas"] = "bilinear",
    canvas_offset: tuple[int, int] = (0, 0),
    canvas_fill: Any | None = None,
    flip_h: bool = False,
    flip_v: bool = False,
    rotate_deg: int = 0,
    to_pot: bool = False,
) -> None:
    """Apply a series of geometric transforms to an image in order."""

    if crop_rect is not None:
        rl.ImageCrop(image, crop_rect)

    if resize is not None:
        w, h = resize
        if resize_mode == "nn":
            rl.ImageResizeNN(image, w, h)
        elif resize_mode == "canvas":
            fill = canvas_fill if canvas_fill else rl.BLANK
            rl.ImageResizeCanvas(image, w, h, canvas_offset[0], canvas_offset[1], fill)
        else:
            rl.ImageResize(image, w, h)

    if flip_h:
        rl.ImageFlipHorizontal(image)

    if flip_v:
        rl.ImageFlipVertical(image)

    if rotate_deg != 0:
        if rotate_deg == 90:
            rl.ImageRotateCW(image)
        elif rotate_deg in (-90, 270):
            rl.ImageRotateCCW(image)
        else:
            rl.ImageRotate(image, rotate_deg)

    if to_pot:
        fill = canvas_fill if canvas_fill else rl.BLANK
        rl.ImageToPOT(image, fill)


def apply_image_filters(
    image: Any,
    *,
    replace_color: tuple[ColorType, ColorType] | None = None,
    tint: Any | None = None,
    brightness: int = 0,
    contrast: int = 0,
    invert: bool = False,
    grayscale: bool = False,
    blur: int = 0,
) -> None:
    """Apply visual effects and color adjustments to an image."""

    if replace_color is not None:
        rl.ImageColorReplace(image, replace_color[0], replace_color[1])

    if tint is not None:
        rl.ImageColorTint(image, tint)

    if invert:
        rl.ImageColorInvert(image)

    if brightness != 0:
        rl.ImageColorBrightness(image, brightness)

    if contrast != 0:
        rl.ImageColorContrast(image, contrast)

    if grayscale:
        rl.ImageColorGrayscale(image)

    if blur > 0:
        rl.ImageBlurGaussian(image, blur)


def process_image_alpha(
    image: Any,
    *,
    premultiply: bool = False,
    clear_threshold: float | None = None,
    clear_color: ColorType | None = None,
    crop_threshold: float | None = None,
    mask_image: Any | None = None,
) -> None:
    """Manage the alpha (transparency) channel of an image."""

    if premultiply:
        rl.ImageAlphaPremultiply(image)

    if clear_threshold is not None:
        color = clear_color if clear_color else rl.BLANK
        rl.ImageAlphaClear(image, color, clear_threshold)

    if crop_threshold is not None:
        rl.ImageAlphaCrop(image, crop_threshold)

    if mask_image is not None:
        rl.ImageAlphaMask(image, mask_image)


def load_texture(
    path: Path,
    *,
    alpha_premultiply: bool = False,
    filter_mode: Literal["nearest", "linear"] = "nearest",
    wrap_mode: Literal["repeat", "clamp", "mirror"] = "clamp",
    mipmap: bool = False,
    color_key: tuple[int, int, int, int] | None = None,
) -> Texture:
    """Load a texture from disk and apply texture parameters.

    Args:
        path: Path to the image file.
        alpha_premultiply: Pre-multiply the alpha channel before upload.
        filter_mode: Texture filter mode ("nearest" or "linear").
        wrap_mode: Texture wrap mode ("repeat", "clamp", or "mirror").
        mipmap: Generate mipmaps after upload.
        color_key: Color replaced with transparency (default black).

    Returns:
        The loaded texture.

    Raises:
        ValueError: If filter_mode or wrap_mode is invalid.
    """
    logger.debug(f"Memuat tekstur dari: {path}")

    image = load_image(path)
    logger.debug(f"Gambar berhasil dimuat: {path.name} ({image.width}x{image.height})")

    if color_key is None:
        color_key = (0, 0, 0, 255)

    # Treat color_key as transparent for legacy assets
    pr.image_color_replace(image, pr.Color(*color_key), pr.Color(0, 0, 0, 0))

    if alpha_premultiply:
        pr.image_alpha_premultiply(image)
        logger.debug("Alpha channel di-pre-multiply")

    texture = load_texture_from_image(image)
    unload_image(image)
    logger.debug("Gambar berhasil dikonversi ke GPU texture")

    set_texture_filter(texture, filter_mode)
    set_texture_wrap(texture, wrap_mode)

    if mipmap:
        gen_texture_mipmaps(texture)
        logger.debug("Mipmaps berhasil dibuat")

    logger.info(f"Tekstur berhasil dimuat: {path.name}")
    return texture


def load_texture_from_image(image: Any) -> Texture:
    """Convert a CPU-side image into a GPU texture."""
    return rl.LoadTextureFromImage(image)


def load_texture_from_dict(
    data: Mapping[str, Any] | ImageData,
    *,
    image_path: Path | str | None = None,
) -> Texture:
    """Load a texture from a config dict or ``ImageData``.

    Args:
        data: JSON config dictionary or ``ImageData`` instance.
        image_path: Path to the image file (overrides the path in config).

    Returns:
        The loaded texture.

    Raises:
        ValueError: If image_path is not provided.
    """

    cfg = (
        data
        if isinstance(data, ImageData)
        else ImageData.from_dict(data, texture_default=default)
    )

    path = image_path if image_path is not None else cfg.image_path
    if not path:
        logger.error(
            "The image path must be provided in the configuration or as an argument."
        )
        raise ValueError(
            "The image path must be provided in the configuration or as an argument."
        )
    if isinstance(path, str):
        path = Path(path)

    logger.debug(
        f"Memuat tekstur dari dict dengan config: "
        f"filter={cfg.texture.filter}, wrap={cfg.texture.wrap}, "
        f"premultiply={cfg.texture.premultiply_alpha}, "
        f"color_key={cfg.texture.color_key}"
    )

    return load_texture(
        path,
        alpha_premultiply=cfg.texture.premultiply_alpha,
        filter_mode=cfg.texture.filter,
        wrap_mode=cfg.texture.wrap,
        mipmap=cfg.texture.mipmap,
        color_key=cfg.texture.color_key,
    )


def unload_texture(texture: Any) -> None:
    """Unload a GPU texture from VRAM.

    Args:
        texture: The texture to unload.
    """
    if texture is not None:
        rl.UnloadTexture(texture)


def is_texture_valid(texture: Any) -> bool:
    """Return ``True`` if the texture is still valid on the GPU."""
    return rl.IsTextureValid(texture)


def update_texture(texture: Any, pixels: Any) -> None:
    """Re-upload the entire texture's pixels."""
    rl.UpdateTexture(texture, pixels)


def update_texture_rec(texture: Any, rec: Any, pixels: Any) -> None:
    """Re-upload a portion of a texture matching a rectangle."""
    rl.UpdateTextureRec(texture, rec, pixels)


def get_image_color(image: Any, x: int, y: int) -> Any:
    """Get the pixel color at image coordinates (x, y)."""
    return rl.GetImageColor(image, x, y)


def get_image_alpha_border(image: Any, threshold: float) -> Any:
    """Compute the bounding-box rectangle for pixels with alpha >= threshold."""
    return rl.GetImageAlphaBorder(image, threshold)
