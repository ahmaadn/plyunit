"""raylib implementation of the text port — UBR integrated."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, cast

import numpy as np
import pyray as pr

from plyunit.backends.ports._unit import IServiceUnit
from plyunit.backends.ports.text import (
    RESERVED_FONT_NAME,
    ITextRenderer,
    ShapedText,
    TemplateConfig,
    TemplateText,
)
from plyunit.core.types import ColorType
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.services.text.shape import (
    BASE_TEMPLATE_NAME,
    DEFAULT_TEMPLATE_SIZE,
    ShapeCache,
    ShapeKey,
    build_default_templates,
    resolve_spacing,
    validate_font_size,
)
from plyunit.utils.io import read_json

from .handler import Font, Image

logger = logging.getLogger(__name__)

DEFAULT_TEXT_COLOR: ColorType = (255, 255, 255, 255)
DEFAULT_COLOR_KEY: ColorType = (255, 0, 255, 255)
DEFAULT_FIRST_CHAR = 32
_PNG_SUFFIX = ".png"

type ConfigReader = Callable[[str], Mapping[str, object] | None]
type Quad = tuple[
    tuple[float, float], tuple[float, float], tuple[float, float, float, float]
]  # (offset_xy, size_wh, uv_rect)


def _font_is_valid(font: pr.Font | None) -> bool:
    """Check the metrics and atlas needed for safe glyph access."""
    return bool(
        font is not None
        and font.baseSize > 0
        and font.glyphCount > 0
        and font.texture.id > 0
        and font.texture.width > 0
        and font.texture.height > 0
        and pr.is_font_valid(font)
    )


@dataclass(slots=True)
class _QuadBuffer:
    """Accumulates per-glyph offsets, sizes and UVs while shaping."""

    offsets: list[tuple[float, float]] = field(default_factory=list)
    sizes: list[tuple[float, float]] = field(default_factory=list)
    uvs: list[tuple[float, float, float, float]] = field(default_factory=list)

    def add(self, quad: Quad) -> None:
        """Append one glyph quad."""
        offset, size, uv = quad
        self.offsets.append(offset)
        self.sizes.append(size)
        self.uvs.append(uv)


def _to_array(rows: Sequence[Sequence[float]], columns: int) -> np.ndarray:
    """Convert rows to a read-only float32 array, including empty arrays."""
    array = np.asarray(rows, dtype=np.float32).reshape(-1, columns)
    array.setflags(write=False)
    return array


def _glyph_index(font: pr.Font, ch: str, glyph_index_cache: dict[int, int]) -> int:
    """Look up a glyph index through the per-font cache."""
    codepoint = ord(ch)
    glyph_idx = glyph_index_cache.get(codepoint)
    if glyph_idx is None:
        glyph_idx = int(pr.get_glyph_index(font, codepoint))
        glyph_index_cache[codepoint] = glyph_idx
    if not 0 <= glyph_idx < int(font.glyphCount):
        glyph_index_cache.pop(codepoint, None)
        raise ValueError(f"invalid glyph index {glyph_idx} for U+{codepoint:04X}")
    return glyph_idx


def _glyph_quad(
    font: pr.Font, glyph_idx: int, pen: tuple[float, float], scale: float
) -> Quad:
    """Compute offset, size and UV rect of one glyph at the pen position."""
    rec = font.recs[glyph_idx]
    glyph = font.glyphs[glyph_idx]
    tex_w = float(font.texture.width)
    tex_h = float(font.texture.height)
    padding = int(font.glyphPadding)
    offset = (
        pen[0] + (glyph.offsetX - padding) * scale,
        pen[1] + (glyph.offsetY - padding) * scale,
    )
    size = ((rec.width + 2 * padding) * scale, (rec.height + 2 * padding) * scale)
    uv = (
        (rec.x - padding) / tex_w,
        (rec.y - padding) / tex_h,
        (rec.x + rec.width + padding) / tex_w,
        (rec.y + rec.height + padding) / tex_h,
    )
    return offset, size, uv


def _glyph_advance(font: pr.Font, glyph_idx: int, scale: float) -> float:
    """Horizontal pen advance of a glyph (falls back to its rect width)."""
    glyph = font.glyphs[glyph_idx]
    advance = glyph.advanceX if glyph.advanceX != 0 else font.recs[glyph_idx].width
    return advance * scale


def shape_glyphs(
    font: Font,
    text: str,
    font_size: int,
    spacing: float,
    glyph_index_cache: dict[int, int],
) -> ShapedText:
    """Compute position/size/UV for each visible glyph in ``text``.

    Deterministic given the font; only ``glyph_index_cache`` is mutated, as a
    memo of codepoint → glyph index lookups.

    Args:
        font: Font handle returned by this adapter's text service.
        text: String to shape; ``"\\n"`` starts a new line.
        font_size: Target font size in pixels.
        spacing: Extra pixels between glyphs on a line.
        glyph_index_cache: Per-font codepoint → glyph index memo.

    Returns:
        ShapedText: Glyph quads relative to the pen origin ``(0, 0)``.
    """
    if not isinstance(font, Font):
        raise TypeError("expected a raylib Font handle")
    raw = font.raw_font
    if raw is None or not font._valid or not _font_is_valid(raw):
        raise ValueError("cannot shape text with an invalid font")
    validate_font_size(font_size)
    spacing = resolve_spacing(spacing, None, font_size)
    scale = font_size / font.base_size
    line_height = float(font_size)
    pen_x, pen_y, max_width = 0.0, 0.0, 0.0
    line_has_character = False
    quads = _QuadBuffer()

    for ch in text.replace("\r\n", "\n").replace("\r", "\n"):
        if ch == "\n":
            max_width = max(max_width, pen_x)
            pen_x, pen_y = 0.0, pen_y + line_height
            line_has_character = False
            continue

        if line_has_character:
            pen_x += spacing
        glyph_idx = _glyph_index(raw, ch, glyph_index_cache)
        if ch not in (" ", "\t"):
            quads.add(_glyph_quad(raw, glyph_idx, (pen_x, pen_y), scale))
        pen_x += _glyph_advance(raw, glyph_idx, scale)
        line_has_character = True

    return ShapedText(
        offsets_xy=_to_array(quads.offsets, 2),
        sizes_wh=_to_array(quads.sizes, 2),
        uv_rects=_to_array(quads.uvs, 4),
        texture=font.texture,
        total_width=max(max_width, pen_x),
        total_height=pen_y + line_height,
    )


def _load_font_resource(path: str, color_key: ColorType, first_char: int) -> pr.Font:
    """Load a font, releasing bitmap-image memory even if font creation fails."""
    if Path(path).suffix.lower() != _PNG_SUFFIX:
        return pr.load_font(path)

    key = pr.Color(*color_key)
    font_image = Image(pr.load_image(path))
    try:
        if not pr.is_image_valid(font_image.raw_image):
            raise OSError(f"failed to load bitmap font image {path!r}")
        return pr.load_font_from_image(font_image.raw_image, key, first_char)
    finally:
        pr.unload_image(font_image.raw_image)


class Text(ServiceUnit):
    """Text service (raylib): fonts, templates, shaping cache and drawing.

    The raylib default font is fetched lazily, so constructing the service
    does not require an initialized window/GL context. ``push``/``render``
    and ``measure`` share the shaping cache.
    """

    def __init__(
        self,
        tags: set[str] | None = None,
        config_reader: ConfigReader = read_json,
        *,
        renderer: ITextRenderer | None = None,
    ) -> None:
        """Initialize the text service.

        Args:
            tags: Extra tags added to the service unit's tag set.
            config_reader: Callable that reads a config file path into a
                mapping (``None`` on failure); injectable for tests.
            renderer: Rendering port; omitted to resolve ``@Renderer`` on demand.
        """
        super().__init__("Text", tags={"service", "text"} | (tags or set()))
        self._config_reader = config_reader
        self._renderer = renderer
        self._fonts: dict[str, Font] = {}
        self._font_generation = 0
        self._glyph_index_caches: dict[str, dict[int, int]] = {}
        self._templates = build_default_templates()
        self._selected_template_name = BASE_TEMPLATE_NAME
        self._shape_cache = ShapeCache()

    def __getitem__(self, item: str) -> Self:
        """Select a template on this service; do not treat the result as a view."""
        self.get_template(item)
        self._selected_template_name = (
            item if item in self._templates else BASE_TEMPLATE_NAME
        )
        return self

    def load(self, config_path: str | Path) -> None:
        """Load fonts and templates from a JSON config file.

        Args:
            config_path: Path to a config with optional ``fonts`` and
                ``templates`` sections.
        """
        config = self._config_reader(str(config_path))
        if not config:
            logger.error("Failed to load config from '%s'", config_path)
            return
        fonts = config.get("fonts", {})
        templates = config.get("templates", {})
        if not isinstance(fonts, Mapping) or not isinstance(templates, Mapping):
            raise ValueError("text config fonts and templates must be mappings")
        self._load_fonts(fonts)
        self.load_templates(cast(TemplateConfig, templates))

    def _load_fonts(self, fonts: Mapping[str, object]) -> None:
        """Load every font entry of a config ``fonts`` section."""
        for font_name, font_data in fonts.items():
            if not isinstance(font_data, Mapping):
                raise ValueError(f"font config {font_name!r} must be a mapping")
            path = font_data.get("path")
            if not path:
                logger.warning(
                    "Font '%s' is missing 'path' in config. Skipping.", font_name
                )
                continue
            color_key = cast(
                ColorType, tuple(font_data.get("color_key", DEFAULT_COLOR_KEY))
            )
            first_char = font_data.get("first_char", DEFAULT_FIRST_CHAR)
            self.load_font(font_name, path, color_key=color_key, first_char=first_char)

    def load_font(
        self,
        name: str,
        path: str | Path,
        color_key: ColorType = DEFAULT_COLOR_KEY,
        first_char: int = DEFAULT_FIRST_CHAR,
    ) -> Font:
        """Load a font from a path (.ttf/.otf or .png) and return it.

        Args:
            name: Name to register the font under; ``"default"`` is reserved.
            path: Font file path.
            color_key: Key color for bitmap (.png) fonts.
            first_char: First codepoint of bitmap (.png) fonts.

        Returns:
            The loaded handle, or the borrowed default when the name is reserved.

        Raises:
            OSError: If loading fails or raylib returns its default-font fallback.
            ValueError: If an existing font handle has been released.
        """
        if name == RESERVED_FONT_NAME:
            logger.error(
                "Font name '%s' is reserved for raylib's built-in font and "
                "cannot be used in config. Skipping load.",
                RESERVED_FONT_NAME,
            )
            return self._default_font()

        raw = _load_font_resource(str(path), color_key, first_char)
        default = pr.get_font_default()
        if int(default.texture.id) > 0 and int(raw.texture.id) == int(
            default.texture.id
        ):
            raise OSError(
                f"failed to load font {name!r} from {str(path)!r}; "
                "raylib returned the default font"
            )
        if not _font_is_valid(raw):
            pr.unload_font(raw)
            raise OSError(f"failed to load font {name!r} from {str(path)!r}")

        try:
            font = self._wrap_font(name, raw)
            previous = self._fonts.get(name)
            if previous is not None and previous.raw_font is not None:
                pr.unload_font(previous.raw_font)
        except BaseException:
            pr.unload_font(raw)
            raise

        if previous is not None:
            previous.raw_font = None
            previous._valid = False
        self._fonts[name] = font
        self._glyph_index_caches.pop(name, None)
        self._shape_cache.clear()
        logger.debug("Loaded font '%s' from '%s'", name, path)
        return font

    def get_font(self, name: str = RESERVED_FONT_NAME) -> Font:
        """Return a named font handle, falling back lazily to the default font.

        Args:
            name: Font name, independent of the selected text template.

        Returns:
            A borrowed handle managed by this text service.

        Raises:
            RuntimeError: If the default font is unavailable before window setup.
        """
        return self._resolve(name)[1]

    def _wrap_font(self, name: str, raw: pr.Font) -> Font:
        """Create a handle with a unique logical identity for its borrowed atlas."""
        self._font_generation += 1
        return Font.from_raw(
            raw,
            texture_id=f"font:{id(self)}:{name}:{self._font_generation}",
        )

    def unload_fonts(self) -> None:
        """Release owned fonts and caches after queued text has been rendered.

        Every font is attempted. Failed unloads remain tracked for retry; the
        built-in default is only forgotten, never passed to ``unload_font``.
        """
        self._glyph_index_caches.clear()
        self._shape_cache.clear()
        errors: list[Exception] = []
        for name, font in list(self._fonts.items()):
            try:
                if name != RESERVED_FONT_NAME and font.raw_font is not None:
                    pr.unload_font(font.raw_font)
            except Exception as exc:
                errors.append(exc)
                continue
            font.raw_font = None
            font._valid = False
            del self._fonts[name]
        if errors:
            raise ExceptionGroup("failed to unload fonts", errors)

    def _has_font(self, name: str) -> bool:
        """Return whether ``name`` is the default font or a loaded font."""
        return name == RESERVED_FONT_NAME or name in self._fonts

    def _default_font(self) -> Font:
        """Fetch a usable borrowed default font without caching pre-window results."""
        font = self._fonts.get(RESERVED_FONT_NAME)
        if font is None or not font._valid or not _font_is_valid(font.raw_font):
            self._glyph_index_caches.pop(RESERVED_FONT_NAME, None)
            self._shape_cache.clear()
            if font is not None:
                font.raw_font = None
                font._valid = False
                del self._fonts[RESERVED_FONT_NAME]
            raw = pr.get_font_default()
            if not _font_is_valid(raw):
                raise RuntimeError(
                    "raylib default font is unavailable; initialize the window first"
                )
            font = self._wrap_font(RESERVED_FONT_NAME, raw)
            self._fonts[RESERVED_FONT_NAME] = font
        return font

    def _resolve(self, name: str) -> tuple[str, Font]:
        """Resolve a name without fetching the default when a custom font exists."""
        if name != RESERVED_FONT_NAME:
            font = self._fonts.get(name)
            if font is not None:
                if not font._valid or not _font_is_valid(font.raw_font):
                    raise ValueError(f"font {name!r} is invalid")
                return name, font
            logger.warning("Font '%s' not found. Using the default font.", name)
        return RESERVED_FONT_NAME, self._default_font()

    def on_detach(self, app: IServiceUnit) -> None:
        """Release font resources before the owning app closes its window."""
        self.unload_fonts()

    def destroy(self) -> None:
        """Release fonts even if the service was never attached to an app."""
        self.unload_fonts()
        super().destroy()

    def load_templates(self, templates: TemplateConfig) -> None:
        """Load templates from a ``{name: {font, spacing, size}}`` mapping."""
        for template_name, data in templates.items():
            gap = data.get("spacing", 0)
            size = data.get("size", DEFAULT_TEMPLATE_SIZE)
            if size is None:
                raise ValueError(f"template {template_name!r} size must be an integer")
            self.set_template(
                template_name,
                str(data.get("font", RESERVED_FONT_NAME)),
                spacing=None if gap is None else float(gap),
                size=int(size),
            )

    def set_template(
        self,
        template_name: str,
        font_name: str,
        spacing: float | None = 0,
        size: int = DEFAULT_TEMPLATE_SIZE,
    ) -> None:
        """Set or override template ``template_name``. Always creates a new instance."""
        validate_font_size(size)
        gap = None if spacing is None else resolve_spacing(spacing, None, size)
        if not self._has_font(font_name):
            logger.warning(
                "Font '%s' is not loaded. Using the default until it is loaded.",
                font_name,
            )

        if template_name in self._templates:
            logger.warning("Template '%s' already exists. Overwriting.", template_name)

        self._templates[template_name] = TemplateText(
            font_name=font_name, spacing=gap, font_size=size
        )
        logger.debug("Set template '%s' with font '%s'", template_name, font_name)

    def get_template(self, template_name: str) -> TemplateText:
        """Get a template by name (falls back to ``base``)."""
        template = self._templates.get(template_name)
        if template is None:
            logger.warning(
                "Template '%s' not found. Using '%s' template instead.",
                template_name,
                BASE_TEMPLATE_NAME,
            )
            return self._templates[BASE_TEMPLATE_NAME]
        return template

    def shape(
        self, text: str, font_size: int | None = None, spacing: float | None = None
    ) -> ShapedText:
        """Return cached, read-only glyph quads for the currently selected template.

        Args:
            text: String to lay out; newlines start another line.
            font_size: Positive size override; ``None`` uses the template size.
            spacing: Letter-spacing override; zero disables added spacing.

        Returns:
            A reusable shape borrowing its loaded font's atlas handle.

        Raises:
            ValueError: If font size or spacing is invalid.
            RuntimeError: If a required default font is not yet available.
        """
        template = self.get_template(self._selected_template_name)
        size = validate_font_size(
            template.font_size if font_size is None else font_size
        )
        gap = resolve_spacing(spacing, template.spacing, size)
        name, font = self._resolve(template.font_name)
        key: ShapeKey = (name, text, size, gap)

        shaped = self._shape_cache.get(key)
        if shaped is None:
            glyph_cache = self._glyph_index_caches.setdefault(name, {})
            shaped = shape_glyphs(font, text, size, gap, glyph_cache)
            self._shape_cache.set(key, shaped)
        return shaped

    def _render_port(self) -> ITextRenderer:
        """Use the injected rendering port or resolve the registry-owned renderer."""
        if self._renderer is not None:
            return self._renderer
        return cast(ITextRenderer, self.one("@Renderer"))

    def draw(
        self,
        text: str,
        *,
        pos: tuple[float, float],
        color: ColorType = DEFAULT_TEXT_COLOR,
        font_size: int | None = None,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """DEBUG ONLY — immediate draw via canvas, fully bypassing the UBR buffer.

        Do not call in a production render loop; every call is a separate
        immediate-mode draw call and is not batched. Use :meth:`push`.
        """
        template = self.get_template(self._selected_template_name)
        size = validate_font_size(
            template.font_size if font_size is None else font_size
        )
        self._render_port().canvas.draw_text(
            text=text.replace("\r\n", "\n").replace("\r", "\n"),
            pos=pos,
            color=color,
            font_size=size,
            spacing=resolve_spacing(spacing, template.spacing, size),
            font=self._resolve(template.font_name)[1],
            origin=origin,
            rotation=rotation,
        )

    def push(
        self,
        text: str,
        *,
        pos: tuple[float, float],
        color: ColorType = DEFAULT_TEXT_COLOR,
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Queue shaped glyphs into the renderer; equivalent to ``render``."""
        self.render(
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
        color: ColorType = DEFAULT_TEXT_COLOR,
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: tuple[float, float] = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Shape and queue glyph quads using their borrowed atlas handle."""
        shaped = self.shape(text, font_size, spacing)
        self._render_port().render_shaped_text(
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
        """Measure integer layout dimensions using the shared shaping cache."""
        shaped = self.shape(text, font_size, spacing)
        return int(shaped.total_width), int(shaped.total_height)


__all__ = ["Text", "shape_glyphs"]
