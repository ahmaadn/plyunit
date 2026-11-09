"""Raylib resource handles with identity semantics.

Raw raylib structs are exposed only for use inside backend adapters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

import pyray as pr

from plyunit.backends.ports.handler import (
    FontHandle,
    ImageHandle,
    PixelBuffer,
    RenderTextureHandle,
    ShaderHandle,
    StreamingTextureHandle,
    Texture2DHandle,
)

if TYPE_CHECKING:
    from plyunit.core.types import RectType, TextureID
    from plyunit.services.assets.schemas import TextureProperty
    from plyunit.services.audio._types import VoiceId

__all__ = ("Font", "Image", "RenderTexture", "Shader", "StreamingTexture", "Texture2D")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, eq=False)
class Image(ImageHandle):
    """CPU image backed by a ``pyray.Image``.

    Size and format are read from the struct on every access because raylib
    edits images in place (crop / resize / rotate change them).
    """

    raw_image: pr.Image

    @property
    def width(self) -> int:
        """Current width in pixels."""
        return int(self.raw_image.width)

    @property
    def height(self) -> int:
        """Current height in pixels."""
        return int(self.raw_image.height)

    @property
    def format_id(self) -> int:
        """Raylib ``PixelFormat`` of the image."""
        return int(self.raw_image.format)


@dataclass(frozen=True, slots=True, eq=False)
class Texture2D(Texture2DHandle):
    """GPU texture (or a region of one) backed by a ``pyray.Texture``."""

    raw_texture: pr.Texture
    texture_id: TextureID
    parent_id: TextureID
    source_rect: RectType
    metadata: TextureProperty
    _owns_texture: bool = field(default=True, repr=False, kw_only=True)

    @classmethod
    def from_raw(
        cls,
        raw_texture: pr.Texture,
        *,
        texture_id: TextureID = "",
        metadata: TextureProperty | None = None,
    ) -> Texture2D:
        """Wrap an existing raylib texture as a root handle covering all of it.

        Use this for textures created outside ``Assets`` (e.g. baked from
        primitives) before passing them to ``IAssets.store_texture``, which
        assigns the final ID.
        """

        from plyunit.services.assets.schemas import TextureProperty

        return cls(
            raw_texture=raw_texture,
            texture_id=texture_id,
            parent_id=texture_id,
            source_rect=(
                0.0,
                0.0,
                float(raw_texture.width),
                float(raw_texture.height),
            ),
            metadata=metadata or TextureProperty(),
        )

    @property
    def width(self) -> int:
        """Width in pixels of the whole GPU texture."""
        return int(self.raw_texture.width)

    @property
    def height(self) -> int:
        """Height in pixels of the whole GPU texture."""
        return int(self.raw_texture.height)

    @property
    def format_id(self) -> int:
        """Raylib ``PixelFormat`` of the texture."""
        return int(self.raw_texture.format)

    def derive(
        self, *, texture_id: TextureID, parent_id: TextureID, source_rect: RectType
    ) -> Texture2D:
        """Return a handle on the same GPU texture with a new identity/region."""
        return replace(
            self,
            texture_id=texture_id,
            parent_id=parent_id,
            source_rect=source_rect,
            _owns_texture=self._owns_texture
            and self._is_root
            and parent_id == texture_id,
        )

    @property
    def _is_root(self) -> bool:
        """Return whether this handle names a root rather than a texture region."""
        return self.parent_id == self.texture_id


@dataclass(slots=True, eq=False)
class Shader(ShaderHandle):
    """Shader resource and its per-handle uniform-location cache.

    Attributes:
        raw_shader: Backend shader object, or ``None`` after unloading.
        locations: Resolved uniform locations keyed by name.
    """

    raw_shader: pr.Shader | None
    locations: dict[str, int] = field(default_factory=dict, repr=False)
    _valid: bool = field(default=True, repr=False)

    @classmethod
    def from_raw(cls, raw_shader: pr.Shader) -> Shader:
        """Wrap a newly loaded backend shader with an empty location cache."""
        return cls(raw_shader)


@dataclass(frozen=True, slots=True, eq=False)
class RenderTexture(RenderTextureHandle):
    """Offscreen render target backed by a ``pyray.RenderTexture``."""

    raw_render_texture: pr.RenderTexture
    _texture_cache: Texture2D | None = field(default=None, init=False, repr=False)

    @property
    def texture(self) -> Texture2D:
        """Return a stable handle for the render target's color attachment."""
        texture = self._texture_cache
        if texture is None:
            texture = replace(
                Texture2D.from_raw(self.raw_render_texture.texture), _owns_texture=False
            )
            object.__setattr__(self, "_texture_cache", texture)
        return texture

    @property
    def raw_texture(self) -> pr.Texture:
        """Return the backend color attachment, initializing its handle if needed."""
        return self.texture.raw_texture

    @property
    def width(self) -> int:
        """Render target width in pixels."""
        return int(self.texture.width)

    @property
    def height(self) -> int:
        """Render target height in pixels."""
        return int(self.texture.height)


class StreamingTexture(StreamingTextureHandle):
    """Own a raylib texture and two pixel-unpack buffers.

    Buffer names, upload state, and native texture IDs are backend internals.
    Consumers draw the borrowed ``texture`` handle and submit pixel buffers.
    """

    __slots__ = (
        "_channels",
        "_height",
        "_primed",
        "_texture",
        "_width",
        "alive",
        "buffer_size",
        "current_pbo",
        "pbo_ids",
    )

    def __init__(
        self,
        texture: Texture2D,
        width: int,
        height: int,
        channels: int,
        pbo_ids: list[int],
    ) -> None:
        """Wrap a texture and the pixel-unpack buffers that own its updates.

        Args:
            texture: Borrowed GPU texture receiving the streamed pixels.
            width: Width in pixels.
            height: Height in pixels.
            channels: Channels per pixel, either three or four.
            pbo_ids: Native names of the two pixel-unpack buffers.
        """
        self._texture = texture
        self._width = width
        self._height = height
        self._channels = channels
        self.pbo_ids = pbo_ids
        self.current_pbo = 0
        self.buffer_size = width * height * channels
        self.alive = True
        self._primed = False

    @property
    def texture(self) -> Texture2D:
        """Return the borrowed texture while the streaming resource is alive."""
        if not self.alive:
            raise ValueError("streaming texture handle has been released")
        return self._texture

    @property
    def width(self) -> int:
        """Return the width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Return the height in pixels."""
        return self._height

    @property
    def channels(self) -> int:
        """Return the number of channels per pixel."""
        return self._channels

    @property
    def texture_id(self) -> int:
        """Return the native GPU name for adapter use only."""
        return int(self.texture.raw_texture.id)

    def update(self, pixels: PixelBuffer) -> bool:
        """Upload a frame, showing the first frame without uninitialized pixels.

        Args:
            pixels: Exactly ``width * height * channels`` bytes of pixel data.

        Returns:
            Whether the upload succeeded. Later frames have one-frame latency.
        """
        from .renderer.streaming_texture import update_streaming_texture

        return update_streaming_texture(self, pixels)

    def destroy(self) -> None:
        """Release the buffers and texture before their graphics context closes."""
        from .renderer.streaming_texture import destroy_streaming_texture

        destroy_streaming_texture(self)


@dataclass(slots=True, eq=False)
class _Sound:
    """Own a sound's shared sample buffer and its loading defaults.

    Attributes:
        raw: Native sound owning the samples.
        path: Resolved asset file path.
        default_volume: Default per-play gain.
        group: Optional metadata label.
    """

    raw: pr.Sound
    path: Path
    default_volume: float = 1.0
    group: str | None = None
    _released: bool = field(default=False, init=False, repr=False)

    def release(self, *, device_ready: bool) -> bool:
        """Release samples once, after all aliases have been released.

        Args:
            device_ready: Whether native resource calls are still safe.

        Returns:
            Whether the samples were released or their device was lost.
        """
        if self._released:
            return True
        if device_ready:
            try:
                pr.unload_sound(self.raw)
            except Exception:
                logger.warning("Failed to unload sound %s", self.path, exc_info=True)
                return False
        self._released = True
        return True


@dataclass(slots=True, eq=False)
class _Music:
    """Own a music decoder and its stream-loading defaults.

    Attributes:
        raw: Native music stream and decoder.
        path: Resolved asset file path.
        default_volume: Default per-play gain.
        default_loop: Whether playback loops by default.
        group: Optional metadata label.
    """

    raw: pr.Music
    path: Path
    default_volume: float = 1.0
    default_loop: bool = True
    group: str | None = None
    _released: bool = field(default=False, init=False, repr=False)

    def stop(self) -> None:
        """Stop a live stream without releasing its decoder."""
        try:
            pr.stop_music_stream(self.raw)
        except Exception:
            logger.debug("Failed to stop music %s", self.path, exc_info=True)

    def release(self, *, device_ready: bool) -> bool:
        """Release the stream and decoder at most once.

        Args:
            device_ready: Whether native resource calls are still safe.

        Returns:
            Whether the decoder was released or its device was lost.
        """
        if self._released:
            return True
        if device_ready:
            try:
                pr.unload_music_stream(self.raw)
            except Exception:
                logger.warning("Failed to unload music %s", self.path, exc_info=True)
                return False
        self._released = True
        return True


@dataclass(slots=True, eq=False)
class _Voice:
    """Own an independent alias, never its source sound's shared samples.

    Attributes:
        voice_id: Service-local playback token.
        voice_raw: Native alias with independent playback state.
        sound_id: ID of the source sound owning the shared samples.
        instance_volume: Per-play gain before buses and attenuation.
        pitch: Pitch multiplier.
        pan: Public stereo position from zero (left) to one (right).
        attenuation: Spatial gain, frozen unless tracking is enabled.
        tracked: Whether source and listener movement updates spatial gain.
        x: Source world X coordinate.
        y: Source world Y coordinate.
    """

    voice_id: VoiceId
    voice_raw: pr.Sound
    sound_id: str
    instance_volume: float
    pitch: float
    pan: float
    attenuation: float = 1.0
    tracked: bool = False
    x: float = 0.0
    y: float = 0.0
    _released: bool = field(default=False, init=False, repr=False)

    def release(self, *, device_ready: bool) -> bool:
        """Stop and unload the alias once, even if stopping raises.

        Args:
            device_ready: Whether native resource calls are still safe.

        Returns:
            Whether the alias was released or its device was lost. A failed
            release must keep its source samples alive until a retry succeeds.
        """
        if self._released:
            return True
        if not device_ready:
            self._released = True
            return True
        try:
            pr.stop_sound(self.voice_raw)
        except Exception:
            logger.debug("Failed to stop voice %s", self.voice_id, exc_info=True)
        try:
            pr.unload_sound_alias(self.voice_raw)
        except Exception:
            logger.warning("Failed to unload voice %s", self.voice_id, exc_info=True)
            return False
        self._released = True
        return True


@dataclass(slots=True, eq=False)
class Font(FontHandle):
    """Font resource with a borrowed atlas owned by its text service.

    Attributes:
        raw_font: Backend font object, or ``None`` after release.

    The atlas must not be unloaded separately. Releasing this handle does not
    mutate the backend struct, which may belong to raylib's built-in font.
    """

    raw_font: pr.Font | None = field()
    _texture: Texture2D = field(repr=False)
    _valid: bool = field(default=True, repr=False)

    @classmethod
    def from_raw(cls, raw_font: pr.Font, *, texture_id: TextureID = "") -> Font:
        """Wrap a loaded font and give its atlas a logical texture identity.

        Args:
            raw_font: Backend font resource to wrap, not transfer or copy.
            texture_id: Logical atlas identity assigned by the text service.

        Returns:
            A font handle with a stable borrowed atlas handle.
        """
        return cls(
            raw_font,
            replace(
                Texture2D.from_raw(raw_font.texture, texture_id=texture_id),
                _owns_texture=False,
            ),
        )

    def _resource(self) -> pr.Font:
        """Return a live backend font for adapter use only."""
        if not self._valid or self.raw_font is None:
            raise ValueError("font handle has been released")
        return self.raw_font

    @property
    def base_size(self) -> int:
        """Return the atlas generation size, rejecting released handles."""
        return int(self._resource().baseSize)

    @property
    def glyph_count(self) -> int:
        """Return the glyph count, rejecting released handles."""
        return int(self._resource().glyphCount)

    @property
    def texture(self) -> Texture2D:
        """Return the stable borrowed atlas, rejecting released handles."""
        if not self._valid or self.raw_font is None:
            raise ValueError("font handle has been released")
        return self._texture
