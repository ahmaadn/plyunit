"""Backend-neutral text template and shaping-cache helpers.

The concrete text service belongs to its integration adapter; this module does
not select or wrap a backend.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Mapping

from plyunit.backends.ports.text import RESERVED_FONT_NAME, ShapedText, TemplateText

BASE_TEMPLATE_NAME = "base"
DEFAULT_TEMPLATE_SIZE = 16
SPACING_DIVISOR = 10.0

_DEFAULT_TEMPLATE_SIZES: Mapping[str, int] = {
    "base": 16,
    "small": 12,
    "medium": 16,
    "large": 24,
    "huge": 32,
}

type ShapeKey = tuple[str, str, int, float]
"""Effective font name, string, font size, and letter spacing."""


def build_default_templates() -> dict[str, TemplateText]:
    """Build independent built-in templates for one text service."""
    return {
        name: TemplateText(font_name=RESERVED_FONT_NAME, spacing=None, font_size=size)
        for name, size in _DEFAULT_TEMPLATE_SIZES.items()
    }


def validate_font_size(font_size: int) -> int:
    """Return a positive font size.

    Args:
        font_size: Requested size in pixels.

    Returns:
        The validated size.

    Raises:
        ValueError: If the size is not a positive integer.
    """
    if not isinstance(font_size, int) or font_size <= 0:
        raise ValueError("font_size must be a positive integer")
    return font_size


def resolve_spacing(
    spacing: float | None, template_spacing: float | None, font_size: int
) -> float:
    """Resolve explicit, template, or size-derived letter spacing.

    Args:
        spacing: Per-call override; zero is an explicit override.
        template_spacing: Template setting used when the override is absent.
        font_size: Positive target size in pixels.

    Returns:
        Finite extra pixels between characters.

    Raises:
        ValueError: If the resulting spacing is not finite.
    """
    gap = spacing if spacing is not None else template_spacing
    if gap is None:
        gap = font_size / SPACING_DIVISOR
    gap = float(gap)
    if not math.isfinite(gap):
        raise ValueError("spacing must be finite")
    return gap


class ShapeCache:
    """Bounded least-recently-used cache of shaped text."""

    def __init__(self, maxsize: int = 256) -> None:
        """Initialize the cache.

        Args:
            maxsize: Maximum entries; zero disables caching.

        Raises:
            ValueError: If the capacity is negative.
        """
        if maxsize < 0:
            raise ValueError("shape cache capacity must not be negative")
        self._maxsize = maxsize
        self._store: OrderedDict[ShapeKey, ShapedText] = OrderedDict()

    def get(self, key: ShapeKey) -> ShapedText | None:
        """Return a cached shape, refreshing its recency, or ``None`` on a miss."""
        value = self._store.get(key)
        if value is not None:
            self._store.move_to_end(key)
        return value

    def set(self, key: ShapeKey, value: ShapedText) -> None:
        """Store a shape, evicting the least recently used entry if necessary."""
        if self._maxsize == 0:
            return
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """Discard all cached shapes."""
        self._store.clear()


__all__ = (
    "BASE_TEMPLATE_NAME",
    "DEFAULT_TEMPLATE_SIZE",
    "ShapeCache",
    "ShapeKey",
    "build_default_templates",
    "resolve_spacing",
    "validate_font_size",
)
