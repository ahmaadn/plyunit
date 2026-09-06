"""raylib Font backend implementation — UBR integrated.
See the end of the file for UBR integration notes.
"""

from __future__ import annotations

import logging

import numpy as np
import pyray as pr

from plyunit.assets.types import ShapedText, TemplateText
from plyunit.core.types import ColorType, FontType
from plyunit.utils.io import read_json

logger = logging.getLogger(__name__)

RESERVED_FONT_NAME = "default"
DEFAULT_MEASURE_TEXT = ""  # placeholder, unused — measure via shape cache


def _build_default_templates() -> dict[str, TemplateText]:
    """Build the built-in default text templates."""
    return {
        "base": TemplateText(font_name="default", spacing=None, font_size=16),
        "small": TemplateText(font_name="default", spacing=None, font_size=12),
        "medium": TemplateText(font_name="default", spacing=None, font_size=16),
        "large": TemplateText(font_name="default", spacing=None, font_size=24),
        "huge": TemplateText(font_name="default", spacing=None, font_size=32),
    }


templates: dict[str, TemplateText] = _build_default_templates()
font_cache: dict[str, FontType] = {}
glyph_index_cache: dict[str, dict[int, int]] = {}
version: int = 0


def get_font(font_name: str = RESERVED_FONT_NAME) -> FontType:
    """Get a font object from the cache by name (falls back to default)."""
    global font_cache

    default_font = font_cache.get(RESERVED_FONT_NAME)
    if default_font is None or default_font.baseSize <= 0:
        font_cache[RESERVED_FONT_NAME] = pr.get_font_default()

    font = font_cache.get(font_name)
    if font is None:
        logger.warning(
            "Font '%s' not found in cache. Using default font instead.", font_name
        )
        font = font_cache.get(RESERVED_FONT_NAME)

    if font is None:
        logger.error("Default font not found in cache. This should never happen.")
        return pr.get_font_default()
    return font


def load(config_path: str) -> None:
    """Load fonts and templates from a JSON config file."""
    config = read_json(config_path)
    if not config:
        logger.error("Failed to load config from '%s'", config_path)
        return

    for font_name, font_data in config.get("fonts", {}).items():
        path = font_data.get("path")
        if not path:
            logger.warning(
                "Font '%s' is missing 'path' in config. Skipping.", font_name
            )
            continue
        color_key = tuple(font_data.get("color_key", (255, 0, 255, 255)))
        first_char = font_data.get("first_char", 32)
        load_font(font_name, path, color_key=color_key, first_char=first_char)

    load_templates(config.get("templates", {}))


def unload() -> None:
    """Unload all fonts from the cache (except the default)."""
    global font_cache, glyph_index_cache, version

    for font_name, font in font_cache.items():
        if font_name != RESERVED_FONT_NAME:
            pr.unload_font(font)
            logger.debug("Unloaded font '%s' from cache.", font_name)

    font_cache = {RESERVED_FONT_NAME: pr.get_font_default()}
    glyph_index_cache.clear()
    version += 1
    logger.info("All fonts have been unloaded from cache.")


def load_font(
    name: str,
    path: str,
    color_key: ColorType = (255, 0, 255, 255),
    first_char: int = 32,
) -> FontType:
    """Load a font from a path (.ttf/.otf or .png) and return it."""
    global font_cache, glyph_index_cache, version

    if name == RESERVED_FONT_NAME:
        logger.error(
            "Nama font '%s' dicadangkan untuk font bawaan raylib, tidak boleh "
            "dipakai di config. Skip load.",
            RESERVED_FONT_NAME,
        )
        return font_cache[RESERVED_FONT_NAME]

    font = _load_font_resource(path, color_key, first_char)

    if name in font_cache:
        logger.warning("Font '%s' is already loaded. Unloading previous font.", name)
        pr.unload_font(font_cache[name])

    font_cache[name] = font
    glyph_index_cache.pop(name, None)
    version += 1
    logger.debug("Loaded font '%s' from '%s'", name, path)
    return font


def _load_font_resource(path: str, color_key: ColorType, first_char: int) -> FontType:
    """Read a file into a raylib Font."""
    if not path.endswith(".png"):
        return pr.load_font(path)

    key = pr.Color(*color_key)
    font_image = pr.load_image(path)
    font = pr.load_font_from_image(font_image, key=key, firstChar=first_char)
    pr.unload_image(font_image)
    return font


def load_templates(templates: dict[str, dict[str, str | int | float]]) -> None:
    """Load templates from a ``{name: {font, spacing, size}}`` dict."""
    for template_name, template_data in templates.items():
        font_name = str(template_data.get("font", RESERVED_FONT_NAME))
        spacing = float(template_data.get("spacing", 0))
        size = int(template_data.get("size", 16))
        set_template(template_name, font_name, spacing=spacing, size=size)


def set_template(
    template_name: str, font_name: str, spacing: float = 0, size: int = 16
) -> None:
    """Set or override template ``template_name``. Always creates a new instance."""
    global font_cache, templates

    if font_name not in font_cache:
        logger.warning(
            "Font '%s' not found in cache. Using default font instead.", font_name
        )
        font_name = RESERVED_FONT_NAME

    if template_name in templates:
        logger.warning("Template '%s' already exists. Overwriting.", template_name)

    templates[template_name] = TemplateText(
        font_name=font_name, spacing=float(spacing), font_size=int(size)
    )
    logger.debug("Set template '%s' with font '%s'", template_name, font_name)


def get_template(template_name: str) -> TemplateText:
    """Get a template by name (falls back to ``base``)."""
    global templates

    template = templates.get(template_name)
    if template is None:
        logger.warning(
            "Template '%s' not found. Using 'base' template instead.", template_name
        )
        return templates["base"]
    return template


def shape_text(
    font: FontType,
    text: str,
    font_size: int,
    spacing: float,
    glyph_index_cache: dict[int, int],
) -> ShapedText:
    """Pure function: compute position/size/UV for each visible glyph in ``text``."""
    scale = font_size / font.baseSize if font.baseSize > 0 else 1.0
    tex_w = float(font.texture.width or 1)
    tex_h = float(font.texture.height or 1)

    pen_x, pen_y = 0.0, 0.0
    max_width = 0.0
    line_has_character = False
    offsets: list[tuple[float, float]] = []
    sizes: list[tuple[float, float]] = []
    uvs: list[tuple[float, float, float, float]] = []

    for ch in text:
        if ch == "\n":
            max_width = max(max_width, pen_x)
            pen_x, pen_y = 0.0, pen_y + font.baseSize * scale
            line_has_character = False
            continue

        if line_has_character:
            pen_x += spacing

        codepoint = ord(ch)
        glyph_idx = glyph_index_cache.get(codepoint)
        if glyph_idx is None:
            glyph_idx = pr.get_glyph_index(font, codepoint)
            glyph_index_cache[codepoint] = glyph_idx

        rec = font.recs[glyph_idx]
        glyph = font.glyphs[glyph_idx]

        if ch != " ":
            offsets.append((
                pen_x + glyph.offsetX * scale,
                pen_y + glyph.offsetY * scale,
            ))
            sizes.append((rec.width * scale, rec.height * scale))
            uvs.append((
                rec.x / tex_w,
                rec.y / tex_h,
                (rec.x + rec.width) / tex_w,
                (rec.y + rec.height) / tex_h,
            ))

        advance = glyph.advanceX if glyph.advanceX != 0 else rec.width
        pen_x += advance * scale
        line_has_character = True

    n = len(offsets)
    max_width = max(max_width, pen_x)
    return ShapedText(
        offsets_xy=np.array(offsets, dtype=np.float32)
        if n
        else np.empty((0, 2), np.float32),
        sizes_wh=np.array(sizes, dtype=np.float32)
        if n
        else np.empty((0, 2), np.float32),
        uv_rects=np.array(uvs, dtype=np.float32) if n else np.empty((0, 4), np.float32),
        tex_id=int(font.texture.id),
        total_width=max_width,
        total_height=pen_y + font.baseSize * scale,
    )


# ---------------------------------------------------------------------------
# UBR integration notes
# ---------------------------------------------------------------------------
#
# 1. Text is not a special case. push() → ShapedText (numpy offsets/sizes/UVs) →
#    Renderer.render_shaped_text → the same SoA FrameBuffer as sprites.
#    Hot path = numpy vector ops only; no per-glyph Python loop.
#
# 2. draw() immediate = DEBUG ONLY. Do not call it in a production render loop.
#
# 3. A text's tex_id = font.texture.id. UBR's global sorting automatically
#    groups every push() using the same font into one run/draw call — no
#    special text logic on the UBR side.
#
# 4. Do not merge font textures into the sprite atlas. raylib fonts are
#    already per-font atlases; the font count is usually small. Merging into
#    the sprite atlas adds a re-pack on every font load for marginal
#    draw-call gain. Treat fonts as their own texture group.
#
# 5. Shape cache: text that changes every frame (score, timer, input) always
#    cache-misses (the key includes the string). A static prefix / dynamic
#    suffix split optimization ("Score: " + number) should only be done if
#    profiling proves a bottleneck — do not implement it speculatively.
