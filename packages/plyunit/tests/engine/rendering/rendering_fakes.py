"""Opaque resource and native-batch fakes for backend-neutral renderer tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from plyunit.core.types import RectType
from plyunit.services.assets.schemas import TextureProperty


@dataclass(eq=False)
class FakeTexture:
    """Texture handle whose backend resource must never be inspected by core.

    Attributes:
        native_id: Identifier only the fake batch adapter may inspect.
        width: Width of the owning texture.
        height: Height of the owning texture.
        texture_id: Logical asset or region identity, never a GPU name.
        parent_id: Logical identity of the owning texture.
        source_rect: Absolute region bounds on the owning texture.
        metadata: Portable sampling settings.
        format_id: Fake backend pixel format.
    """

    native_id: int
    width: int
    height: int
    texture_id: str
    parent_id: str
    source_rect: RectType
    metadata: TextureProperty = field(default_factory=TextureProperty)
    format_id: int = 7

    @property
    def raw_texture(self) -> Any:
        """Reject native-resource inspection by backend-neutral consumers."""
        raise AssertionError("Neutral renderer must not inspect raw_texture")

    def derive(
        self, *, texture_id: str, parent_id: str, source_rect: RectType
    ) -> FakeTexture:
        """Create a region sharing this texture's fake native identity.

        Args:
            texture_id: New logical region identity.
            parent_id: Logical identity of the owning texture.
            source_rect: Absolute region bounds.

        Returns:
            A region handle on the same native texture.
        """
        return replace(
            self, texture_id=texture_id, parent_id=parent_id, source_rect=source_rect
        )


def make_texture(
    native_id: int = 1,
    width: int = 8,
    height: int = 8,
    *,
    texture_id: str = "asset",
    source_rect: RectType | None = None,
) -> FakeTexture:
    """Create a texture or region with distinct logical and native identities.

    Args:
        native_id: Fake native identifier owned by the batch adapter.
        width: Owning texture width.
        height: Owning texture height.
        texture_id: Logical asset identity.
        source_rect: Region bounds, or the full texture when omitted.

    Returns:
        An opaque texture handle.
    """
    return FakeTexture(
        native_id, width, height, texture_id, texture_id,
        source_rect if source_rect is not None else (0.0, 0.0, float(width), float(height)),
    )


@dataclass(eq=False)
class FakeShader:
    """Opaque shader handle with no core-visible native program."""

    locations: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw_shader: Any) -> FakeShader:
        """Create a fake handle without exposing the supplied native value.

        Args:
            raw_shader: Ignored opaque backend value.

        Returns:
            A shader handle with an empty location cache.
        """
        return cls()

    @property
    def raw_shader(self) -> Any:
        """Reject raw shader inspection in the neutral renderer."""
        raise AssertionError("Neutral renderer must not inspect raw_shader")


@dataclass(eq=False)
class FakeRenderTexture:
    """Offscreen target exposing only its portable texture attachment."""

    texture: FakeTexture = field(default_factory=make_texture)

    @property
    def raw_render_texture(self) -> Any:
        """Reject native framebuffer inspection."""
        raise AssertionError("Neutral renderer must not inspect raw_render_texture")

    @property
    def raw_texture(self) -> Any:
        """Reject native attachment inspection."""
        raise AssertionError("Neutral renderer must not inspect raw_texture")

    @property
    def width(self) -> int:
        """Return the target width."""
        return self.texture.width

    @property
    def height(self) -> int:
        """Return the target height."""
        return self.texture.height


@dataclass(eq=False)
class FakeFont:
    """Font handle whose backend resource cannot be inspected by core."""

    base_size: int = 16
    glyph_count: int = 95

    @property
    def raw_font(self) -> Any:
        """Reject backend-specific font access."""
        raise AssertionError("Neutral renderer must not inspect raw_font")


class TextureIdAdapter:
    """Provide native ID extraction for existing batch test doubles."""

    def texture_id(self, handle: FakeTexture) -> int:
        """Resolve a fake texture's native ID at the adapter boundary.

        Args:
            handle: Opaque fake texture handle.

        Returns:
            Its native batching identity, unrelated to its logical asset ID.
        """
        assert isinstance(handle, FakeTexture)
        return handle.native_id


class RecordingBatch(TextureIdAdapter):
    """Record native batch calls and snapshot arrays before frame-buffer reuse."""

    def __init__(self) -> None:
        """Initialize batch counters and submitted frame snapshots."""
        self.capacity = 64
        self.submits: list[dict[str, Any]] = []
        self.texture_queries: list[FakeTexture] = []
        self.init_calls = 0
        self.shutdown_calls = 0

    def init(self, max_sprites: int | None = None) -> None:
        """Record initialization with an optional capacity.

        Args:
            max_sprites: Requested capacity.
        """
        if max_sprites is not None:
            self.capacity = max_sprites
        self.init_calls += 1

    def shutdown(self) -> None:
        """Record native resource teardown."""
        self.shutdown_calls += 1

    def texture_id(self, handle: FakeTexture) -> int:
        """Record and resolve one texture handle.

        Args:
            handle: Texture being submitted.

        Returns:
            The adapter's native ID.
        """
        self.texture_queries.append(handle)
        return super().texture_id(handle)

    def submit_frame(self, **kwargs: Any) -> None:
        """Snapshot one native submission.

        Args:
            **kwargs: Frame arrays and counts passed by the renderer.
        """
        self.submits.append({
            key: value.copy() if isinstance(value, np.ndarray) else value
            for key, value in kwargs.items()
        })
