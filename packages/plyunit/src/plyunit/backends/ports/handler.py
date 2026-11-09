"""Backend-neutral contracts for dedicated resource handles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from plyunit.core.types import RectType, TextureID
    from plyunit.services.assets.schemas import TextureProperty

__all__ = (
    "FontHandle",
    "ImageHandle",
    "PixelBuffer",
    "RenderTextureHandle",
    "ShaderHandle",
    "StreamingTextureHandle",
    "Texture2DHandle",
    "TextureTarget",
)


@runtime_checkable
class ImageHandle(Protocol):
    """A CPU-side image (pixels in system memory, RAM).

    Unlike a texture, an image is edited in place by ``IImageProcessor``, so
    ``width``, ``height``, and ``format_id`` reflect its current pixel data.
    Native resources are accessible only through the concrete backend handle.
    """

    @property
    def width(self) -> int:
        """Current width in pixels."""
        ...

    @property
    def height(self) -> int:
        """Current height in pixels."""
        ...

    @property
    def format_id(self) -> int:
        """Backend pixel-format identifier.

        Comparable only with ``format_id`` values of the same backend.
        """
        ...


@runtime_checkable
class Texture2DHandle(Protocol):
    """A borrowed view of a cached GPU texture, or a region of one.

    A root handle identifies the cache entry that owns the GPU texture
    (``parent_id == texture_id``). A region shares its parent's resource.
    Handles must not be used after their owner unloads, replaces, or repacks
    that resource; resolve the asset ID again to obtain its current handle.
    """

    @property
    def texture_id(self) -> TextureID:
        """The ID this handle is cached under."""
        ...

    @property
    def parent_id(self) -> TextureID:
        """ID of the root (or atlas page) that owns the GPU texture.

        Equal to ``texture_id`` for a root handle.
        """
        ...

    @property
    def source_rect(self) -> RectType:
        """``(x, y, w, h)`` region of the GPU texture covered by the handle."""
        ...

    @property
    def metadata(self) -> TextureProperty:
        """Filter / wrap / mipmap settings the texture was created with."""
        ...

    @property
    def width(self) -> int:
        """Width in pixels of the WHOLE GPU texture (not of ``source_rect``)."""
        ...

    @property
    def height(self) -> int:
        """Height in pixels of the WHOLE GPU texture (not of ``source_rect``)."""
        ...

    @property
    def format_id(self) -> int:
        """Backend pixel-format identifier (same scale as ``ImageHandle``)."""
        ...

    def derive(
        self,
        *,
        texture_id: TextureID,
        parent_id: TextureID,
        source_rect: RectType,
    ) -> Texture2DHandle:
        """Return a new handle on the same GPU texture with a new identity/region.

        The original handle is left untouched; the GPU resource and metadata
        are shared. Backend-neutral consumers can use this to describe regions
        without knowing the concrete handle class.
        """
        ...


@runtime_checkable
class ShaderHandle(Protocol):
    """Opaque shader identity owned and validated by its backend adapter.

    Native shader resources and uniform caches belong to the implementation,
    not to backend-neutral consumers.
    """

    __slots__ = ()


@runtime_checkable
class RenderTextureHandle(Protocol):
    """Opaque offscreen render target owned by a backend.

    The attachment is borrowed from the target and must not be unloaded or
    transferred to an asset cache independently of the render target.
    """

    @property
    def texture(self) -> Texture2DHandle:
        """Color attachment, usable anywhere a texture handle is accepted."""
        ...

    @property
    def width(self) -> int:
        """Render target width in pixels."""
        ...

    @property
    def height(self) -> int:
        """Render target height in pixels."""
        ...


@runtime_checkable
class FontHandle(Protocol):
    """Opaque loaded font with a borrowed glyph-atlas texture.

    The atlas belongs to the font and must not be unloaded or transferred to
    an asset cache separately. Releasing the font also invalidates its atlas.
    """

    @property
    def texture(self) -> Texture2DHandle:
        """Borrowed glyph atlas, valid only while the font remains loaded."""
        ...

    @property
    def base_size(self) -> int:
        """Size in pixels the glyph atlas was generated at."""
        ...

    @property
    def glyph_count(self) -> int:
        """Number of glyphs in the font."""
        ...


@runtime_checkable
class StreamingTextureHandle(Protocol):
    """CPU-writable texture for per-frame pixel uploads."""

    __slots__ = ()

    @property
    def texture(self) -> Texture2DHandle:
        """GPU texture that receives the streamed pixels."""

    @property
    def width(self) -> int:
        """Width in pixels."""

    @property
    def height(self) -> int:
        """Height in pixels."""

    @property
    def channels(self) -> int:
        """Colour channels per pixel (3 = RGB, 4 = RGBA)."""

    def update(self, pixels: PixelBuffer) -> bool:
        """Upload a full frame of pixels.

        Args:
            pixels: Raw pixel bytes, exactly ``width * height * channels`` long.

        Returns:
            ``False`` on size mismatch, destroyed handle, or backend failure.
        """

    def destroy(self) -> None:
        """Release the streaming buffers and the underlying texture."""


type PixelBuffer = bytes | bytearray | memoryview
"""Raw pixel memory accepted by streaming uploads."""

type TextureTarget = Texture2DHandle | RenderTextureHandle
"""Anything that owns a texture whose sampling state can be changed."""
