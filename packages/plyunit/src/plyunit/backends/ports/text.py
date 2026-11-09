"""Backend-neutral text templates, metrics, and service contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, Self, runtime_checkable

from ._unit import IServiceUnit

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from plyunit.core.types import ColorType, Vec2Type

    from .handler import FontHandle, Texture2DHandle
    from .renderer import ICanvas2D

RESERVED_FONT_NAME: Final = "default"
"""Name of the backend's borrowed built-in font; cannot be overridden."""


@dataclass(frozen=True)
class ShapedText:
    """Reusable glyph quads relative to the pen origin.

    Attributes:
        offsets_xy: Read-only float32 glyph positions with shape ``(n, 2)``.
        sizes_wh: Read-only float32 glyph sizes with shape ``(n, 2)``.
        uv_rects: Read-only normalized atlas UVs with shape ``(n, 4)``.
        texture: Borrowed font-atlas handle. The font must remain loaded while
            these quads are queued or drawn.
        total_width: Maximum line advance, excluding trailing letter spacing.
        total_height: Line count multiplied by the requested font size.
    """

    offsets_xy: npt.NDArray[np.float32]
    sizes_wh: npt.NDArray[np.float32]
    uv_rects: npt.NDArray[np.float32]
    texture: Texture2DHandle
    total_width: float
    total_height: float


@dataclass(frozen=True)
class TemplateText:
    """Font and layout settings for a named text style.

    Attributes:
        font_name: Registered font name.
        spacing: Extra pixels between characters, or ``None`` for size-derived
            spacing.
        font_size: Positive target font size in pixels.
    """

    font_name: str
    spacing: float | None
    font_size: int


type TemplateConfig = Mapping[str, Mapping[str, str | int | float | None]]
"""JSON-compatible template settings, keyed by template name."""


@runtime_checkable
class ITextRenderer(Protocol):
    """Rendering operations used by a text service, independent of its backend."""

    @property
    def canvas(self) -> ICanvas2D:
        """Immediate-mode drawing surface."""
        ...

    def render_shaped_text(
        self,
        shaped: ShapedText,
        *,
        pos: Vec2Type,
        color: ColorType = (255, 255, 255, 255),
        origin: Vec2Type = (0, 0),
        rotation: float = 0,
        z: float = 0,
        layer: int = 0,
    ) -> None:
        """Queue glyph quads using their font-atlas handle."""
        ...


@runtime_checkable
class IText(IServiceUnit, Protocol):
    """Port for fonts, templates, shaping, measuring, and text submission."""

    def __getitem__(self, item: str) -> Self:
        """Select a template by name, falling back to ``base``; return this service.

        Selection is shared mutable service state, not a separate style object.
        """
        ...

    def load(self, config_path: str | Path) -> None:
        """Load fonts and templates from a JSON config file."""
        ...

    def load_font(
        self,
        name: str,
        path: str | Path,
        color_key: ColorType = (255, 0, 255, 255),
        first_char: int = 32,
    ) -> FontHandle:
        """Load an owned font; the reserved name returns the borrowed default.

        A failed load leaves the previously registered font intact.
        """
        ...

    def get_font(self, name: str = RESERVED_FONT_NAME) -> FontHandle:
        """Return a font handle, lazily falling back to the default if missing."""
        ...

    def unload_fonts(self) -> None:
        """Release owned fonts and caches without unloading the built-in default.

        Call only after queued text using these fonts has been rendered.
        """
        ...

    def load_templates(self, templates: TemplateConfig) -> None:
        """Load templates from a ``{name: {font, spacing, size}}`` mapping."""
        ...

    def set_template(
        self,
        template_name: str,
        font_name: str,
        spacing: float | None = 0,
        size: int = 16,
    ) -> None:
        """Set or override a template, including the currently selected style."""
        ...

    def get_template(self, template_name: str) -> TemplateText:
        """Return a template by name, falling back to ``base``."""
        ...

    def shape(
        self, text: str, font_size: int | None = None, spacing: float | None = None
    ) -> ShapedText:
        """Return cached glyph quads for the selected template, without rendering."""
        ...

    def draw(
        self,
        text: str,
        *,
        pos: Vec2Type,
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        origin: Vec2Type = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Draw immediately through the canvas, bypassing the batched buffer."""
        ...

    def push(
        self,
        text: str,
        *,
        pos: Vec2Type,
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: Vec2Type = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Queue text into the render buffer; equivalent to ``render``."""
        ...

    def render(
        self,
        text: str,
        *,
        pos: Vec2Type,
        color: ColorType = (255, 255, 255, 255),
        font_size: int | None = None,
        z: int = 0,
        layer: int = 0,
        origin: Vec2Type = (0, 0),
        rotation: float = 0,
        spacing: float | None = None,
    ) -> None:
        """Shape and queue text using the shared glyph cache."""
        ...

    def measure(
        self, text: str, font_size: int | None = None, spacing: float | None = None
    ) -> tuple[int, int]:
        """Return integer layout dimensions using the shared shaping cache."""
        ...


__all__ = (
    "RESERVED_FONT_NAME",
    "IText",
    "ITextRenderer",
    "ShapedText",
    "TemplateConfig",
    "TemplateText",
)
