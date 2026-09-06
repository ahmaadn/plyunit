"""Text rendering service with a shaping cache and template selection.

Provides :class:`Text`, a ``ServiceUnit`` that shapes, measures, and
submits text to the renderer, sharing one LRU shaping cache between
``push``/``render``/``measure``.
"""

import logging
from collections import OrderedDict
from typing import Self

from plyunit.assets.types import ShapedText, ShapeKey
from plyunit.backends.interfaces.i_text import IFont
from plyunit.core.types import ColorType
from plyunit.core.units import ServiceUnit

logger = logging.getLogger(__name__)


class _ShapeCache:
    """Bounded LRU cache for shape_text results."""

    def __init__(self, maxsize: int = 256) -> None:
        """Initialize the cache with the given capacity."""
        self._maxsize = maxsize
        self._store: OrderedDict[ShapeKey, ShapedText] = OrderedDict()

    def get(self, key: ShapeKey) -> ShapedText | None:
        """Return the cached value for a key, refreshing its recency.

        Args:
            key: The cache key.

        Returns:
            The cached value, or ``None`` on a miss.
        """
        value = self._store.get(key)
        if value is not None:
            self._store.move_to_end(key)
        return value

    def set(self, key: ShapeKey, value: ShapedText) -> None:
        """Store a value under a key, evicting the least recently used entry when full.

        Args:
            key: The cache key.
            value: The value to store.
        """
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._store.clear()


class Text(ServiceUnit):
    """Text drawing service. ``push`` and ``measure`` share the shaping cache."""

    def __init__(self, font: IFont | None = None, tags: set[str] | None = None) -> None:
        """Initialize the text service.

        Args:
            font: Font implementation; when ``None`` the default backend
                font is used.
            tags: Extra tags added to the service unit's tag set.
        """
        super().__init__("Text", tags={"service", "text"} | (tags or set()))

        if font is None:
            from plyunit.backends.integrations import Font

            font = Font()
        self.font = font
        self._selected_template = self.font.get_template("base")
        self._shape_cache = _ShapeCache()
        self._font_version_seen = self.font.version

    def __getitem__(self, item: str) -> Self:
        """Select a template; chainable to draw/push/measure — do not store
        across frames."""
        template = self.font.templates.get(item)
        if template is None:
            logger.warning(
                "Template '%s' not found. Using 'base' template instead.", item
            )
            template = self.font.templates["base"]
        self._selected_template = template
        return self

    def _shaped(self, text: str, font_size: int | None, spacing: int | None):
        """Fetch the ShapedText from cache, or compute and store it on a miss."""
        if self.font.version != self._font_version_seen:
            self._shape_cache.clear()
            self._font_version_seen = self.font.version

        t = self._selected_template
        size = font_size or t.font_size
        gap = spacing if spacing is not None else t.spacing
        if gap is None:
            gap = size / 10.0
        gap = float(gap)
        key: ShapeKey = (t.font_name, text, size, gap)

        shaped = self._shape_cache.get(key)
        if shaped is None:
            font_obj = self.font.get_font(t.font_name)
            glyph_cache = self.font.glyph_index_cache.setdefault(t.font_name, {})
            shaped = self.font.shape_text(font_obj, text, size, gap, glyph_cache)
            self._shape_cache.set(key, shaped)
        return shaped

    def draw(
        self,
        text: str,
        *,
        pos: tuple[float, float],
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """DEBUG ONLY — immediate draw via canvas, fully bypassing the UBR buffer.

        Do not call in a production render loop; every call is a separate
        immediate-mode draw call and is not batched. Use :meth:`push`.
        """
        t = self._selected_template
        canvas = self.one("@Renderer").canvas
        canvas.draw_text(
            text=text,
            pos=pos,
            color=color,
            font_size=font_size or t.font_size,
            spacing=spacing if spacing is not None else t.spacing,
            font=self.font.get_font(t.font_name),
            origin=origin,
            rotation=rotation,
        )

    def push(
        self,
        text: str,
        *,
        pos: tuple[float, float],
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Hot path: shape → :meth:`Renderer.render_shaped_text` → FrameBuffer SoA.

        Text is not a special case — glyph quads are written to the same
        buffer as sprites. ``tex_id`` = ``font.texture.id``; the UBR sort
        groups the same font into one run/draw call. Shaping is cached;
        later frames only translate positions (numpy), never re-computing
        glyphs.
        """
        return self.render(
            text,
            pos=pos,
            color=color,
            font_size=font_size,
            z=z,
            layer=layer,
            origin=origin,
            rotation=rotation,
            spacing=spacing,
        )

    def render(
        self,
        text: str,
        *,
        pos: tuple[float, float],
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Hot path: shape → :meth:`Renderer.render_shaped_text` → FrameBuffer SoA.

        Text is not a special case — glyph quads are written to the same
        buffer as sprites. ``tex_id`` = ``font.texture.id``; the UBR sort
        groups the same font into one run/draw call. Shaping is cached;
        later frames only translate positions (numpy), never re-computing
        glyphs.
        """
        shaped = self._shaped(text, font_size, spacing)
        self.one("@Renderer").render_shaped_text(
            shaped,
            pos=pos,
            color=color,
            origin=origin,
            rotation=rotation,
            z=z,
            layer=layer,
        )

    def measure(
        self, text: str, font_size: int | None = None, spacing: float | None = None
    ) -> tuple[int, int]:
        """Measure width/height. Shares the cache with push() — no double shaping."""
        shaped = self._shaped(text, font_size, spacing)
        return int(shaped.total_width), int(shaped.total_height)


__all__ = ("Text",)
