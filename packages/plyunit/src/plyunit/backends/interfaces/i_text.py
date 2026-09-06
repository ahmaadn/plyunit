"""Font loading and shaping contracts for the host backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from plyunit.assets.types import ShapedText, TemplateText
    from plyunit.core.types import ColorType, FontType


@runtime_checkable
class IFont(Protocol):
    """Font loading, template, and text shaping service.

    Attributes:
        version: Bump counter invalidating caches when fonts are reloaded.
        templates: Named text templates (font + size + spacing presets).
        font_cache: Loaded fonts keyed by font name.
        glyph_index_cache: Glyph index lookups keyed by font name.
    """

    # Attributes
    version: int
    templates: dict[str, TemplateText]
    font_cache: dict[str, FontType]
    glyph_index_cache: dict[str, dict[int, int]]

    # Methods
    def _build_default_templates(self) -> dict[str, TemplateText]:
        """Build the built-in default template set."""
        ...

    def get_font(self, font_name: str = "default") -> FontType:
        """Get a loaded font by name, falling back to the default font.

        Args:
            font_name: Font name to look up.

        Returns:
            The requested font, or the default font when not found.
        """
        ...

    def load(self, config_path: str) -> None:
        """Load fonts and templates from a config file.

        Args:
            config_path: Font config file path.
        """
        ...

    def unload(self) -> None:
        """Unload all cached fonts and templates."""
        ...

    def load_font(
        self,
        name: str,
        path: str,
        color_key: ColorType = (255, 0, 255, 255),
        first_char: int = 32,
    ) -> FontType:
        """Load a bitmap font from an image file and cache it by name.

        Args:
            name: Name to register the font under.
            path: Font image file path.
            color_key: Chroma-key color treated as transparent.
            first_char: Character code of the first glyph in the image.

        Returns:
            The loaded font handle.
        """
        ...

    def _load_font_resource(
        self, path: str, color_key: ColorType, first_char: int
    ) -> FontType:
        """Load the raw backend font resource from a file."""
        ...

    def load_templates(
        self, templates: dict[str, dict[str, str | int | float]]
    ) -> None:
        """Load multiple text templates from a raw mapping.

        Args:
            templates: Template definitions keyed by template name.
        """
        ...

    def set_template(
        self, template_name: str, font_name: str, spacing: float = 0, size: int = 16
    ) -> None:
        """Create or update a named text template.

        Args:
            template_name: Name to register the template under.
            font_name: Font the template uses.
            spacing: Letter spacing in pixels.
            size: Font size in pixels.
        """
        ...

    def get_template(self, template_name: str) -> TemplateText:
        """Get a text template by name.

        Args:
            template_name: Template name to look up.

        Returns:
            The template definition.
        """
        ...

    def shape_text(
        self,
        font: FontType,
        text: str,
        font_size: int,
        spacing: float,
        glyph_index_cache: dict[int, int],
    ) -> ShapedText:
        """Shape text into positioned glyphs for rendering.

        Args:
            font: Font to shape with.
            text: Text to shape.
            font_size: Font size in pixels.
            spacing: Letter spacing in pixels.
            glyph_index_cache: Mutable cache of codepoint-to-glyph-index
                lookups, filled in by this call.

        Returns:
            The shaped text (positioned glyph run).
        """
        ...


__all__ = ["IFont"]
