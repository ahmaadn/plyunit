"""Texture and image load/unload/config contracts for the host backend.

This module defines :class:`IAssetsLoader` — the protocol that every asset
loader backend must satisfy. Backends implement it as a module of functions
(mirroring the audio backend) and expose it as the active loader. The
engine ``Assets`` service reads ``default`` for fallback texture params and
delegates texture load/unload to these functions; the image manipulation,
generation, and query helpers cover asset preprocessing pipelines (resize /
flip / color ops / procedural images / pixel sampling).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from plyunit.core.types import ColorType, Texture

if TYPE_CHECKING:
    from plyunit.assets.types import ImageData, TextureProperty


@runtime_checkable
class IAssetsLoader(Protocol):
    """Backend ops for textures and CPU-side images.

    Backends implement this as a module of functions (mirroring the audio
    backend) and expose it as the active loader. The engine ``Assets``
    service reads ``default`` for fallback texture params and delegates
    texture load / unload to these functions; the image manipulation,
    generation, and query helpers cover asset preprocessing pipelines
    (resize / flip / color ops / procedural images / pixel sampling).
    """

    default: TextureProperty
    """Default texture configuration used as the fallback for loads."""

    def set_default_config_texture(
        self,
        *,
        filter_mode: Literal["nearest", "linear"] = "nearest",
        wrap_mode: Literal["repeat", "clamp", "mirror"] = "clamp",
        mipmap: bool = False,
        premultiply_alpha: bool = False,
        color_key: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Set the default texture configuration used as the load fallback.

        Args:
            filter_mode: Texture filtering mode (``"nearest"`` or ``"linear"``).
            wrap_mode: Texture wrapping mode (``"repeat"``, ``"clamp"``, or
                ``"mirror"``).
            mipmap: Whether to generate mipmaps.
            premultiply_alpha: Whether to premultiply alpha on load.
            color_key: Optional chroma-key color treated as transparent.
        """
        ...

    def set_texture_filter(self, texture: Texture, filter_mode: str) -> None:
        """Set the filtering mode of an existing texture.

        Args:
            texture: Texture to update.
            filter_mode: Filter mode name understood by the backend.
        """
        ...

    def set_texture_wrap(self, texture: Texture, wrap_mode: str) -> None:
        """Set the wrapping mode of an existing texture.

        Args:
            texture: Texture to update.
            wrap_mode: Wrap mode name understood by the backend.
        """
        ...

    def gen_texture_mipmaps(self, texture: Texture) -> None:
        """Generate mipmaps for an existing texture.

        Args:
            texture: Texture to regenerate mipmaps for.
        """
        ...

    def load_image(self, path: str | Path) -> Any:
        """Load an image from file into CPU memory.

        Args:
            path: Image file path.

        Returns:
            The backend image handle.
        """
        ...

    def unload_image(self, image: Any) -> None:
        """Unload a CPU-side image and free its memory.

        Args:
            image: Image handle to unload.
        """
        ...

    def is_image_valid(self, image: Any) -> bool:
        """Check whether an image handle is valid (loaded and not unloaded).

        Args:
            image: Image handle to check.

        Returns:
            True if the image is valid.
        """
        ...

    def gen_image_color(
        self, width: int, height: int, color: ColorType = (0, 0, 0, 0)
    ) -> Any:
        """Create a new image filled with a solid color.

        Args:
            width: Image width in pixels.
            height: Image height in pixels.
            color: Fill color (RGBA).

        Returns:
            The backend image handle.
        """
        ...

    def load_image_from_texture(self, texture: Texture) -> Any:
        """Load a CPU-side image from GPU texture pixel data.

        Args:
            texture: Source texture.

        Returns:
            The backend image handle.
        """
        ...

    def image_draw(self, dst: Any, src: Any, pos: tuple[int, int]) -> None:
        """Draw a source image onto a destination image in place.

        Args:
            dst: Destination image.
            src: Source image.
            pos: Top-left position (x, y) in destination pixels.
        """
        ...

    def transform_image(
        self,
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
        """Apply geometric transforms to an image in place.

        Args:
            image: Image to transform.
            crop_rect: Optional source rectangle to crop to.
            resize: Optional target (width, height); ``None`` keeps the size.
            resize_mode: Resampling mode (``"bilinear"``, ``"nn"`` for
                nearest-neighbor, or ``"canvas"`` to paste onto a resized
                canvas).
            canvas_offset: Offset used in ``"canvas"`` mode.
            canvas_fill: Fill color used in ``"canvas"`` mode.
            flip_h: Flip horizontally.
            flip_v: Flip vertically.
            rotate_deg: Rotation in degrees (must be a multiple of 90).
            to_pot: Pad the image to power-of-two dimensions.
        """
        ...

    def apply_image_filters(
        self,
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
        """Apply color filters to an image in place.

        Args:
            image: Image to filter.
            replace_color: Optional ``(old, new)`` color pair; pixels matching
                ``old`` are recolored to ``new``.
            tint: Optional tint color mask.
            brightness: Brightness offset (-255..255).
            contrast: Contrast offset (-255..255).
            invert: Invert the color channels.
            grayscale: Convert the image to grayscale.
            blur: Blur kernel size (0 disables).
        """
        ...

    def process_image_alpha(
        self,
        image: Any,
        *,
        premultiply: bool = False,
        clear_threshold: float | None = None,
        clear_color: ColorType | None = None,
        crop_threshold: float | None = None,
        mask_image: Any | None = None,
    ) -> None:
        """Process the alpha channel of an image in place.

        Args:
            image: Image to process.
            premultiply: Premultiply RGB by alpha.
            clear_threshold: Optional alpha threshold below which pixels are
                cleared.
            clear_color: Color used when clearing pixels below the threshold.
            crop_threshold: Optional alpha threshold used to crop fully
                transparent borders.
            mask_image: Optional mask image; pixels where the mask is
                transparent are cleared.
        """
        ...

    # --- texture load / unload / update --------------------------------
    def load_texture(
        self,
        path: Path,
        *,
        alpha_premultiply: bool = False,
        filter_mode: Literal["nearest", "linear"] = "nearest",
        wrap_mode: Literal["repeat", "clamp", "mirror"] = "clamp",
        mipmap: bool = False,
        color_key: tuple[int, int, int, int] | None = None,
    ) -> Texture:
        """Load a GPU texture from an image file.

        Args:
            path: Image file path.
            alpha_premultiply: Whether to premultiply alpha on load.
            filter_mode: Texture filtering mode.
            wrap_mode: Texture wrapping mode.
            mipmap: Whether to generate mipmaps.
            color_key: Optional chroma-key color treated as transparent.

        Returns:
            The loaded texture handle.
        """
        ...

    def load_texture_from_image(self, image: Any) -> Texture:
        """Create a GPU texture from a CPU-side image.

        Args:
            image: Source image handle.

        Returns:
            The created texture handle.
        """
        ...

    def load_texture_from_dict(
        self,
        data: Mapping[str, Any] | ImageData,
        *,
        image_path: Path | str | None = None,
    ) -> Texture:
        """Load a texture from an image config mapping.

        Args:
            data: :class:`ImageData`-shaped mapping with load options.
            image_path: Optional base path used to resolve a relative image
                file.

        Returns:
            The loaded texture handle.
        """
        ...

    def unload_texture(self, texture: Texture) -> None:
        """Unload a GPU texture and free its memory.

        Args:
            texture: Texture to unload.
        """
        ...

    def is_texture_valid(self, texture: Texture) -> bool:
        """Check whether a texture handle is valid (loaded and not unloaded).

        Args:
            texture: Texture to check.

        Returns:
            True if the texture is valid.
        """
        ...

    def update_texture(self, texture: Texture, pixels: Any) -> None:
        """Update an entire texture with new pixel data.

        Args:
            texture: Texture to update.
            pixels: Raw pixel data buffer.
        """
        ...

    def update_texture_rec(self, texture: Texture, rec: Any, pixels: Any) -> None:
        """Update a rectangular region of a texture with new pixel data.

        Args:
            texture: Texture to update.
            rec: Destination rectangle within the texture.
            pixels: Raw pixel data buffer sized to the rectangle.
        """
        ...

    def get_image_color(self, image: Any, x: int, y: int) -> Any:
        """Sample the color of a single image pixel.

        Args:
            image: Image to sample.
            x: Pixel column.
            y: Pixel row.

        Returns:
            The backend color value at (x, y).
        """
        ...

    def get_image_alpha_border(self, image: Any, threshold: float) -> Any:
        """Compute the crop rectangle enclosing pixels above an alpha threshold.

        Args:
            image: Image to inspect.
            threshold: Alpha threshold (0.0..1.0) for border detection.

        Returns:
            The bounding rectangle of non-transparent pixels.
        """
        ...


__all__ = ["IAssetsLoader"]
