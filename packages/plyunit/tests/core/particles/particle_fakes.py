"""Opaque texture doubles for backend-neutral particle tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from plyunit.core.types import RectType
from plyunit.services.assets.schemas import TextureProperty


@dataclass(eq=False)
class FakeParticleTexture:
    """Opaque texture handle carrying only identity, size, and region.

    The concrete backend resource is intentionally unreachable so particle
    submission cannot depend on native texture access.

    Attributes:
        native_id: Fake GPU identity, used to tell two handles apart.
        width: Width of the owning texture in pixels.
        height: Height of the owning texture in pixels.
        texture_id: Logical asset identity.
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

    def derive(
        self, *, texture_id: str, parent_id: str, source_rect: RectType
    ) -> FakeParticleTexture:
        """Create a region sharing this texture's fake identity.

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
    native_id: int = 1, width: int = 8, height: int = 8, *, texture_id: str = "asset"
) -> FakeParticleTexture:
    """Build a fake texture handle covering the whole fake texture.

    Args:
        native_id: Fake native identifier.
        width: Owning texture width.
        height: Owning texture height.
        texture_id: Logical asset identity.

    Returns:
        An opaque texture handle.
    """
    return FakeParticleTexture(
        native_id, width, height, texture_id, texture_id,
        (0.0, 0.0, float(width), float(height)),
    )


__all__ = ("FakeParticleTexture", "make_texture")
