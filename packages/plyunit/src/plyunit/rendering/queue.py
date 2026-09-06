"""Queue for non-sprite render items (primitives, text, custom).

Sprites are written directly to
:class:`~plyunit.rendering.frame_buffer.FrameBuffer`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .enum import PrimitiveKind, RenderKind

if TYPE_CHECKING:
    from plyunit.backends.interfaces import ICanvas2D


@dataclass(slots=True)
class PrimitiveItem:
    """A single primitive item flushed through ``draw_primitive``.

    Attributes:
        kind: The primitive kind (``PrimitiveKind``).
        payload: Kwargs dict forwarded to the ``canvas.draw_*`` method.
    """

    kind: PrimitiveKind
    payload: Any


@dataclass(slots=True)
class TextItem:
    """Text payload; ``payload`` holds kwargs for ``canvas.draw_text``."""

    payload: dict[str, Any]


@dataclass(slots=True)
class CustomItem:
    """Custom draw call payload; ``draw_func`` is invoked at flush time."""

    draw_func: Callable[[ICanvas2D], None]


@dataclass(slots=True)
class RenderItem:
    """A single non-sprite entry in the renderer queue."""

    kind: RenderKind
    payload: PrimitiveItem | TextItem | CustomItem
    pass_name: str
    layer: int
    sort_key: float
    submit_index: int
    state_id: int
    screen_space: bool

    @property
    def batch_key(self) -> tuple[Any, ...]:
        """Grouping key used to batch compatible render items together."""
        material = None
        if isinstance(self.payload, PrimitiveItem):
            material = self.payload.kind
        return (self.pass_name, self.layer, self.state_id, self.kind, material)


_Y_SORT_LAYERS: set[int] = set()

__all__ = [
    "_Y_SORT_LAYERS",
    "CustomItem",
    "RenderItem",
    "TextItem",
]
