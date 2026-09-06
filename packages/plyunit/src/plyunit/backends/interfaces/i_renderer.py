"""Renderer-facing backend contracts: 2D canvas, window, render pass, UBR batch.

Defines the :class:`ICanvas2D`, :class:`IWindow`, :class:`IRenderPass`, and
:class:`IUnifiedBufferBatch` protocols that host backends must satisfy.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

    from plyunit.core.types import (
        ColorType,
        FontType,
        NPatchInfoType,
        RectType,
        RenderTexture,
        ShaderType,
        Texture,
        Vec2Type,
    )


@runtime_checkable
class ICanvas2D(Protocol):
    """Immediate-mode 2D drawing surface backed by the host renderer.

    Covers primitives (pixel/line/circle/ellipse/ring/rectangle/triangle/
    poly), texture drawing, GPU state modes (scissor/blend/shader/render
    texture), stencil masking, streaming textures, text, batched primitive
    submission, and baking primitives into :class:`Texture` objects.
    """

    # Primitive
    def draw_pixel(
        self, *, pos: Vec2Type = (0, 0), color: ColorType | None = None
    ) -> None:
        """Draw a single pixel.

        Args:
            pos: Pixel position ``(x, y)``.
            color: Pixel color; ``None`` uses the backend default.
        """
        ...

    def draw_line(
        self,
        *,
        start: Vec2Type = (0, 0),
        end: Vec2Type = (0, 0),
        color: ColorType | None = None,
        thickness: float = 1.0,
        bezier: bool = False,
        origin: Vec2Type | None = None,
        rotation: float = 0.0,
    ) -> None:
        """Draw a line (optionally as a quadratic bezier curve).

        Args:
            start: Start point ``(x, y)``.
            end: End point ``(x, y)``.
            color: Line color; ``None`` uses the backend default.
            thickness: Line thickness in pixels.
            bezier: Interpret ``start``/``end`` as control points of a
                quadratic bezier (with ``origin`` as the middle control).
            origin: Optional origin for rotation and bezier control point.
            rotation: Rotation in degrees around ``origin``.
        """
        ...

    def draw_circle(
        self,
        *,
        center: Vec2Type = (0, 0),
        radius: float = 10.0,
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        gradient_outer: ColorType | None = None,
        sector_angles: tuple[float, float] | None = None,
        segments: int = 36,
        origin: Vec2Type | None = None,
        rotation: float = 0.0,
    ) -> None:
        """Draw a circle, ring outline, gradient, or sector.

        Args:
            center: Circle center ``(x, y)``.
            radius: Circle radius in pixels.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional outline color (used with ``outline_only``
                or with ``thickness`` > 0).
            outline_only: Draw only the border, skipping the fill.
            thickness: Border thickness in pixels.
            gradient_outer: Optional outer color for a radial gradient
                (``color`` is the inner color).
            sector_angles: Optional ``(start, end)`` angles in degrees to
                draw a pie sector.
            segments: Number of edge segments.
            origin: Optional rotation origin.
            rotation: Rotation in degrees around ``origin``.
        """
        ...

    def draw_ellipse(
        self,
        *,
        center: Vec2Type = (0, 0),
        radius_h: float = 10.0,
        radius_v: float = 10.0,
        color: ColorType | None = None,
        outline_only: bool = False,
    ) -> None:
        """Draw an ellipse.

        Args:
            center: Ellipse center ``(x, y)``.
            radius_h: Horizontal radius in pixels.
            radius_v: Vertical radius in pixels.
            color: Fill color; ``None`` uses the backend default.
            outline_only: Draw only the outline, skipping the fill.
        """
        ...

    def draw_ring(
        self,
        *,
        center: Vec2Type = (0, 0),
        inner_radius: float = 5.0,
        outer_radius: float = 10.0,
        start_angle: float = 0.0,
        end_angle: float = 360.0,
        segments: int = 36,
        color: ColorType | None = None,
        outline_only: bool = False,
    ) -> None:
        """Draw a ring (annulus) or ring segment.

        Args:
            center: Ring center ``(x, y)``.
            inner_radius: Inner radius in pixels.
            outer_radius: Outer radius in pixels.
            start_angle: Start angle in degrees.
            end_angle: End angle in degrees.
            segments: Number of edge segments.
            color: Fill color; ``None`` uses the backend default.
            outline_only: Draw only the outer outline of the ring.
        """
        ...

    def draw_rectangle(
        self,
        *,
        rect: RectType = (0, 0, 10, 10),
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        roundness: float = 0.0,
        segments: int = 10,
        origin: Vec2Type | None = None,
        rotation: float = 0.0,
        gradient_v: tuple[ColorType, ColorType] | None = None,
        gradient_h: tuple[ColorType, ColorType] | None = None,
        gradient_ex: tuple[ColorType, ColorType, ColorType, ColorType] | None = None,
        round_tl: bool = True,
        round_tr: bool = True,
        round_bl: bool = True,
        round_br: bool = True,
    ) -> None:
        """Draw a rectangle with optional rounding, border, and gradients.

        Args:
            rect: Rectangle ``(x, y, width, height)``.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Draw only the border, skipping the fill.
            thickness: Border thickness in pixels.
            roundness: Corner roundness (0.0..1.0, fraction of half the
                smaller side).
            segments: Number of segments per rounded corner.
            origin: Optional rotation origin.
            rotation: Rotation in degrees around ``origin``.
            gradient_v: Optional vertical gradient ``(top, bottom)``.
            gradient_h: Optional horizontal gradient ``(left, right)``.
            gradient_ex: Optional 4-corner gradient ``(tl, tr, bl, br)``.
            round_tl: Round the top-left corner.
            round_tr: Round the top-right corner.
            round_bl: Round the bottom-left corner.
            round_br: Round the bottom-right corner.
        """
        ...

    def draw_triangle(
        self,
        *,
        v1: Vec2Type = (0, 0),
        v2: Vec2Type = (0, 0),
        v3: Vec2Type = (0, 0),
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        origin: Vec2Type | None = None,
        rotation: float = 0.0,
        gradient: tuple[ColorType, ColorType, ColorType] | None = None,
    ) -> None:
        """Draw a triangle with optional border and vertex gradient.

        Args:
            v1: First vertex ``(x, y)``.
            v2: Second vertex ``(x, y)``.
            v3: Third vertex ``(x, y)``.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Draw only the border, skipping the fill.
            thickness: Border thickness in pixels.
            origin: Optional rotation origin.
            rotation: Rotation in degrees around ``origin``.
            gradient: Optional per-vertex colors ``(v1, v2, v3)``.
        """
        ...

    def draw_poly(
        self,
        *,
        center: Vec2Type = (0, 0),
        sides: int = 3,
        radius: float = 10.0,
        rotation: float = 0.0,
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        origin: Vec2Type | None = None,
    ) -> None:
        """Draw a regular polygon.

        Args:
            center: Polygon center ``(x, y)``.
            sides: Number of sides (>= 3).
            radius: Circumradius in pixels.
            rotation: Rotation in degrees.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Draw only the border, skipping the fill.
            thickness: Border thickness in pixels.
            origin: Optional rotation origin.
        """
        ...

    # Texture
    def draw_texture(
        self,
        *,
        texture: Texture | None = None,
        pos: Vec2Type = (0, 0),
        tint: ColorType | None = None,
        rotation: float = 0.0,
        scale: float = 1.0,
        source: RectType | None = None,
        dest: RectType | None = None,
        origin: Vec2Type = (0, 0),
        npatch_info: NPatchInfoType | None = None,
    ) -> None:
        """Draw a texture with optional transform, sub-rectangle, or n-patch.

        Args:
            texture: Texture to draw.
            pos: Position ``(x, y)`` of the destination rectangle.
            tint: Tint color; ``None`` uses white.
            rotation: Rotation in degrees.
            scale: Uniform scale factor.
            source: Optional source rectangle within the texture.
            dest: Optional explicit destination rectangle (overrides
                ``pos``/``scale``).
            origin: Rotation and position origin within the sprite.
            npatch_info: Optional n-patch info for 9-slice drawing.
        """
        ...

    # GPU State Mode Methods
    def begin_scissor_mode(self, x: int, y: int, width: int, height: int) -> None:
        """Start scissor-mode clipping; drawing is cut to the given rectangle.

        Args:
            x: Clip rectangle x in pixels.
            y: Clip rectangle y in pixels.
            width: Clip rectangle width in pixels.
            height: Clip rectangle height in pixels.
        """
        ...

    def end_scissor_mode(self) -> None:
        """End scissor-mode clipping."""
        ...

    def begin_blend_mode(self, mode: int) -> None:
        """Start a blended render mode.

        Args:
            mode: Backend blend-mode constant (e.g. additive, multiplied).
        """
        ...

    def end_blend_mode(self) -> None:
        """End the blended render mode, restoring the default."""
        ...

    def begin_shader_mode(self, shader: ShaderType) -> None:
        """Start rendering with a shader applied.

        Args:
            shader: Shader handle to activate.
        """
        ...

    def end_shader_mode(self) -> None:
        """End shader-mode rendering, restoring the default shader."""
        ...

    def begin_texture_mode(self, target: RenderTexture) -> None:
        """Start rendering into an offscreen render texture.

        Args:
            target: Render texture to draw into.
        """
        ...

    def end_texture_mode(self) -> None:
        """End render-texture mode, returning to the backbuffer."""
        ...

    # Render texture
    def load_render_texture(self, width: int, height: int) -> Any:
        """Create an offscreen render texture.

        Args:
            width: Texture width in pixels.
            height: Texture height in pixels.

        Returns:
            The backend render texture handle.
        """
        ...

    def unload_render_texture(self, target: Any) -> None:
        """Unload a render texture and free its GPU memory.

        Args:
            target: Render texture handle to unload.
        """
        ...

    def clear_transparent(self) -> None:
        """Clear the current render target to fully transparent."""
        ...

    def draw_texture_region(
        self,
        texture: Any,
        source: tuple[float, float, float, float],
        dest: tuple[float, float, float, float],
    ) -> None:
        """Draw a sub-region of a texture at 1:1 scale.

        Args:
            texture: Source texture handle.
            source: Source rectangle ``(x, y, w, h)`` in texels.
            dest: Destination rectangle ``(x, y, w, h)`` in pixels.
        """
        ...

    def gen_mipmaps(self, target: Any) -> None:
        """Generate mipmaps for a texture.

        Args:
            target: Texture handle to process.
        """
        ...

    def set_texture_filter(
        self, target: Any, filter_mode: str = "trilinear"
    ) -> None:
        """Set the filtering mode of a texture.

        Args:
            target: Texture handle to update.
            filter_mode: Filter mode name (default ``"trilinear"``).
        """
        ...

    # stenci
    def init_stencil(self) -> bool:
        """Initialize the stencil buffer.

        Returns:
            True if the stencil buffer is available and initialized.
        """
        ...

    def begin_stencil_mask(self) -> None:
        """Start recording a stencil mask (drawing writes to the stencil)."""
        ...

    def end_stencil_mask(self) -> None:
        """Stop recording the stencil mask and render masked content."""
        ...

    def end_stencil_mask_inverse(self) -> None:
        """Stop recording and render the inverse (outside) of the stencil."""
        ...

    def end_stencil_mode(self) -> None:
        """End stencil mode, disabling stencil testing."""
        ...

    # Streaming
    def init_streaming(self) -> bool:
        """Initialize the streaming-texture pipeline.

        Returns:
            True if streaming textures are available.
        """
        ...

    def create_streaming_texture(
        self, width: int, height: int, *, channels: int = 4
    ) -> Any:
        """Create a CPU-writable texture for per-frame pixel streaming.

        Args:
            width: Texture width in pixels.
            height: Texture height in pixels.
            channels: Number of color channels per pixel (default 4 = RGBA).

        Returns:
            The streaming texture handle.
        """
        ...  # Use custom type

    def destroy_streaming_texture(self, streaming: Any) -> None:
        """Destroy a streaming texture and free its resources.

        Args:
            streaming: Streaming texture handle to destroy.
        """
        ...

    # Text
    def draw_text(
        self,
        *,
        text: str = "",
        pos: Vec2Type = (0, 0),
        font_size: float = 20,
        color: ColorType | None = None,
        font: FontType | None = None,
        spacing: float | None = None,
        origin: Vec2Type | None = None,
        rotation: float = 0.0,
        codepoint: int | None = None,
        codepoints: Sequence[int] | None = None,
    ) -> None:
        """Draw text with an optional custom font, transform, and glyph filter.

        Args:
            text: Text to draw.
            pos: Position ``(x, y)`` of the text.
            font_size: Font size in pixels.
            color: Text color; ``None`` uses the backend default.
            font: Optional custom font handle.
            spacing: Optional letter spacing; ``None`` uses font default.
            origin: Optional rotation/position origin.
            rotation: Rotation in degrees around ``origin``.
            codepoint: Optional single codepoint to draw instead of ``text``.
            codepoints: Optional codepoint sequence to draw instead of
                ``text``.
        """
        ...

    # batch primitive
    def draw_rectangle_batch(
        self,
        *,
        rects: Sequence[RectType] | None = None,
        colors: Sequence[ColorType] | None = None,
    ) -> None:
        """Draw many rectangles in one batched draw call.

        Args:
            rects: Rectangle sequence; ``None`` draws nothing.
            colors: Per-rectangle colors; ``None`` uses the default color.
        """
        ...

    def draw_circle_batch(
        self,
        *,
        centers: Sequence[Vec2Type] | None = None,
        radii: Sequence[float] | None = None,
        colors: Sequence[ColorType] | None = None,
    ) -> None:
        """Draw many circles in one batched draw call.

        Args:
            centers: Center sequence; ``None`` draws nothing.
            radii: Per-circle radii; ``None`` uses the default radius.
            colors: Per-circle colors; ``None`` uses the default color.
        """
        ...

    def draw_line_batch(
        self,
        *,
        starts: Sequence[Vec2Type] | None = None,
        ends: Sequence[Vec2Type] | None = None,
        colors: Sequence[ColorType] | None = None,
    ) -> None:
        """Draw many lines in one batched draw call.

        Args:
            starts: Start point sequence; ``None`` draws nothing.
            ends: End point sequence; ``None`` draws nothing.
            colors: Per-line colors; ``None`` uses the default color.
        """
        ...

    def draw_triangle_batch(
        self,
        *,
        v1s: Sequence[Vec2Type] | None = None,
        v2s: Sequence[Vec2Type] | None = None,
        v3s: Sequence[Vec2Type] | None = None,
        colors: Sequence[ColorType] | None = None,
    ) -> None:
        """Draw many triangles in one batched draw call.

        Args:
            v1s: First-vertex sequence; ``None`` draws nothing.
            v2s: Second-vertex sequence; ``None`` draws nothing.
            v3s: Third-vertex sequence; ``None`` draws nothing.
            colors: Per-triangle colors; ``None`` uses the default color.
        """
        ...

    # Texture creation (bake primitive -> Texture2D)
    def create_rect(
        self,
        *,
        rect: RectType = (0, 0, 10, 10),
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        roundness: float = 0.0,
        segments: int = 10,
        gradient_v: tuple[ColorType, ColorType] | None = None,
        gradient_h: tuple[ColorType, ColorType] | None = None,
        gradient_ex: tuple[ColorType, ColorType, ColorType, ColorType] | None = None,
        round_tl: bool = True,
        round_tr: bool = True,
        round_bl: bool = True,
        round_br: bool = True,
    ) -> Texture:
        """Bake a rectangle drawing into a texture.

        Args:
            rect: Rectangle ``(x, y, width, height)``.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Bake only the border, skipping the fill.
            thickness: Border thickness in pixels.
            roundness: Corner roundness (0.0..1.0).
            segments: Number of segments per rounded corner.
            gradient_v: Optional vertical gradient ``(top, bottom)``.
            gradient_h: Optional horizontal gradient ``(left, right)``.
            gradient_ex: Optional 4-corner gradient ``(tl, tr, bl, br)``.
            round_tl: Round the top-left corner.
            round_tr: Round the top-right corner.
            round_bl: Round the bottom-left corner.
            round_br: Round the bottom-right corner.

        Returns:
            The baked texture.
        """
        ...

    def create_rects(
        self,
        *,
        rects: Sequence[RectType] | None = None,
        colors: Sequence[ColorType] | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        roundness: float = 0.0,
        segments: int = 10,
        gradient_v: tuple[ColorType, ColorType] | None = None,
        gradient_h: tuple[ColorType, ColorType] | None = None,
        gradient_ex: tuple[ColorType, ColorType, ColorType, ColorType] | None = None,
        round_tl: bool = True,
        round_tr: bool = True,
        round_bl: bool = True,
        round_br: bool = True,
    ) -> list[Texture]:
        """Bake many rectangle drawings into textures.

        Args:
            rects: Rectangle sequence; ``None`` bakes nothing.
            colors: Per-rectangle fill colors; ``None`` uses the default.
            border_color: Optional shared border color.
            outline_only: Bake only the borders, skipping the fills.
            thickness: Border thickness in pixels.
            roundness: Corner roundness (0.0..1.0).
            segments: Number of segments per rounded corner.
            gradient_v: Optional shared vertical gradient ``(top, bottom)``.
            gradient_h: Optional shared horizontal gradient ``(left, right)``.
            gradient_ex: Optional shared 4-corner gradient
                ``(tl, tr, bl, br)``.
            round_tl: Round the top-left corners.
            round_tr: Round the top-right corners.
            round_bl: Round the bottom-left corners.
            round_br: Round the bottom-right corners.

        Returns:
            The list of baked textures.
        """
        ...

    def create_circle(
        self,
        *,
        radius: float = 10.0,
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        gradient_outer: ColorType | None = None,
        sector_angles: tuple[float, float] | None = None,
        segments: int = 36,
    ) -> Texture:
        """Bake a circle drawing into a texture.

        Args:
            radius: Circle radius in pixels.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Bake only the border, skipping the fill.
            thickness: Border thickness in pixels.
            gradient_outer: Optional outer color for a radial gradient.
            sector_angles: Optional ``(start, end)`` angles in degrees to
                bake a pie sector.
            segments: Number of edge segments.

        Returns:
            The baked texture.
        """
        ...

    def create_circles(
        self,
        *,
        radii: Sequence[float] | None = None,
        colors: Sequence[ColorType] | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        gradient_outer: ColorType | None = None,
        sector_angles: tuple[float, float] | None = None,
        segments: int = 36,
    ) -> list[Texture]:
        """Bake many circle drawings into textures.

        Args:
            radii: Per-circle radii; ``None`` bakes nothing.
            colors: Per-circle fill colors; ``None`` uses the default.
            border_color: Optional shared border color.
            outline_only: Bake only the borders, skipping the fills.
            thickness: Border thickness in pixels.
            gradient_outer: Optional shared outer color for radial gradients.
            sector_angles: Optional shared ``(start, end)`` sector angles in
                degrees.
            segments: Number of edge segments.

        Returns:
            The list of baked textures.
        """
        ...

    def create_line(
        self,
        *,
        start: Vec2Type = (0, 0),
        end: Vec2Type = (0, 0),
        color: ColorType | None = None,
        thickness: float = 1.0,
        bezier: bool = False,
    ) -> Texture:
        """Bake a line (optionally a quadratic bezier) into a texture.

        Args:
            start: Start point ``(x, y)``.
            end: End point ``(x, y)``.
            color: Line color; ``None`` uses the backend default.
            thickness: Line thickness in pixels.
            bezier: Treat ``start``/``end`` as bezier control points.

        Returns:
            The baked texture.
        """
        ...

    def create_lines(
        self,
        *,
        starts: Sequence[Vec2Type] | None = None,
        ends: Sequence[Vec2Type] | None = None,
        colors: Sequence[ColorType] | None = None,
        thickness: float = 1.0,
        bezier: bool = False,
    ) -> list[Texture]:
        """Bake many lines (optionally beziers) into textures.

        Args:
            starts: Start point sequence; ``None`` bakes nothing.
            ends: End point sequence; ``None`` bakes nothing.
            colors: Per-line colors; ``None`` uses the default.
            thickness: Line thickness in pixels.
            bezier: Treat points as bezier control points.

        Returns:
            The list of baked textures.
        """
        ...

    def create_poly(
        self,
        *,
        sides: int = 6,
        radius: float = 10.0,
        rotation: float = 0.0,
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
    ) -> Texture:
        """Bake a regular polygon drawing into a texture.

        Args:
            sides: Number of sides (>= 3).
            radius: Circumradius in pixels.
            rotation: Rotation in degrees.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Bake only the border, skipping the fill.
            thickness: Border thickness in pixels.

        Returns:
            The baked texture.
        """
        ...

    def create_polys(
        self,
        *,
        sides: Sequence[int] | None = None,
        radii: Sequence[float] | None = None,
        rotations: Sequence[float] | None = None,
        colors: Sequence[ColorType] | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
    ) -> list[Texture]:
        """Bake many regular polygon drawings into textures.

        Args:
            sides: Per-polygon side counts; ``None`` bakes nothing.
            radii: Per-polygon circumradii; ``None`` uses the default.
            rotations: Per-polygon rotations in degrees; ``None`` uses 0.
            colors: Per-polygon fill colors; ``None`` uses the default.
            border_color: Optional shared border color.
            outline_only: Bake only the borders, skipping the fills.
            thickness: Border thickness in pixels.

        Returns:
            The list of baked textures.
        """
        ...

    def create_triangle(
        self,
        *,
        v1: Vec2Type = (0, 0),
        v2: Vec2Type = (0, 0),
        v3: Vec2Type = (0, 0),
        color: ColorType | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        gradient: tuple[ColorType, ColorType, ColorType] | None = None,
    ) -> Texture:
        """Bake a triangle drawing into a texture.

        Args:
            v1: First vertex ``(x, y)``.
            v2: Second vertex ``(x, y)``.
            v3: Third vertex ``(x, y)``.
            color: Fill color; ``None`` uses the backend default.
            border_color: Optional border color.
            outline_only: Bake only the border, skipping the fill.
            thickness: Border thickness in pixels.
            gradient: Optional per-vertex colors ``(v1, v2, v3)``.

        Returns:
            The baked texture.
        """
        ...

    def create_triangles(
        self,
        *,
        v1s: Sequence[Vec2Type] | None = None,
        v2s: Sequence[Vec2Type] | None = None,
        v3s: Sequence[Vec2Type] | None = None,
        colors: Sequence[ColorType] | None = None,
        border_color: ColorType | None = None,
        outline_only: bool = False,
        thickness: float = 1.0,
        gradient: tuple[ColorType, ColorType, ColorType] | None = None,
    ) -> list[Texture]:
        """Bake many triangle drawings into textures.

        Args:
            v1s: First-vertex sequence; ``None`` bakes nothing.
            v2s: Second-vertex sequence; ``None`` bakes nothing.
            v3s: Third-vertex sequence; ``None`` bakes nothing.
            colors: Per-triangle fill colors; ``None`` uses the default.
            border_color: Optional shared border color.
            outline_only: Bake only the borders, skipping the fills.
            thickness: Border thickness in pixels.
            gradient: Optional shared per-vertex colors ``(v1, v2, v3)``.

        Returns:
            The list of baked textures.
        """
        ...

    def clear_background(color: ColorType) -> None:
        """Clear the backbuffer to the given color.

        Args:
            color: Clear color.
        """
        ...


@runtime_checkable
class IWindow(Protocol):
    """Window and frame-clock service contract.

    Covers native window lifecycle, drawing-frame control, screen queries,
    and the frame clock with fixed-timestep accumulator state.
    """

    # Frame clock state
    dt: float
    """Scaled delta time of the current frame (raw dt * time_scale)."""

    unscaled_dt: float
    """Clamped raw delta time of the current frame, ignoring time_scale."""

    total_time: float
    """Total unscaled elapsed time in seconds since the clock started."""

    frame_count: int
    """Number of frames processed since the clock started."""

    time_scale: float
    """Multiplier applied to raw delta time (e.g. for slow-mo)."""

    fixed_delta_time: float
    """Duration of one fixed-update step in seconds (e.g. 1/60)."""

    max_frame_delta_time: float
    """Upper clamp for raw frame delta time, guarding against spikes."""

    accumulator: float
    """Leftover scaled time not yet consumed by fixed steps."""

    alpha: float
    """Interpolation factor (0..1) of the accumulator within a fixed step."""

    fixed_steps: int
    """Total number of fixed steps consumed since the clock started."""

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def init_window(self, width: int, height: int, title: str) -> None:
        """Open the native window.

        Args:
            width: Window width in pixels. Must be > 0.
            height: Window height in pixels. Must be > 0.
            title: Window title text.

        Raises:
            ValueError: If width or height is not positive.
        """
        ...

    def close_window(self) -> None:
        """Close the native window and release backend resources."""
        ...

    def window_should_close(self) -> bool:
        """Return True if the OS or user has requested the window close."""
        ...

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def set_target_fps(self, fps: int) -> None:
        """Set the target frames-per-second cap for the render loop.

        Raises:
            ValueError: If fps is not > 0.
        """
        ...

    def begin_drawing(self) -> None:
        """Start a new drawing frame."""
        ...

    def end_drawing(self) -> None:
        """Finish the current drawing frame and swap buffers."""
        ...

    def clear_background(self, color: ColorType) -> None:
        """Clear the backbuffer to the given color."""
        ...

    def present_loading_frame(
        self,
        color: ColorType,
        text: str | None = None,
        *,
        text_color: ColorType | None = None,
        font_size: int = 20,
    ) -> None:
        """Present one static frame (loading screen) outside the main pipeline.

        Covers main-thread blocking startup work (imports, fonts, assets):
        the last presented frame stays visible until the main pipeline
        takes over.
        """
        ...

    def get_frame_time(self) -> float:
        """Return the raw, unclamped delta time reported by the backend."""
        ...

    def get_fps(self) -> int:
        """Return the backend-reported instantaneous FPS."""
        ...

    @property
    def average_fps(self) -> float:
        """FPS averaged over the most recent frame-time samples."""
        ...

    # ------------------------------------------------------------------
    # Screen / display queries
    # ------------------------------------------------------------------

    def get_screen_width(self) -> int:
        """Return the current window width in pixels."""
        ...

    def get_screen_height(self) -> int:
        """Return the current window height in pixels."""
        ...

    def get_screen_size(self) -> tuple[int, int]:
        """Return the current (width, height) window size in pixels."""
        ...

    def set_window_size(self, width: int, height: int) -> None:
        """Resize the native window.

        Raises:
            ValueError: If width or height is not positive.
        """
        ...

    def set_window_title(self, title: str) -> None:
        """Change the native window title."""
        ...

    def is_fullscreen(self) -> bool:
        """Return True if the window is currently fullscreen."""
        ...

    def toggle_fullscreen(self) -> None:
        """Toggle between windowed and fullscreen mode."""
        ...

    def is_focused(self) -> bool:
        """Return True if the window currently has input focus."""
        ...

    def is_resized(self) -> bool:
        """Return True if the window was resized on the last frame."""
        ...

    # ------------------------------------------------------------------
    # Frame clock / fixed timestep
    # ------------------------------------------------------------------

    def start_frame(self) -> None:
        """Capture the backend delta and advance the frame clock."""
        ...

    def consume_fixed_steps(self, max_steps: int) -> int:
        """Consume at most ``max_steps`` fixed updates from the accumulator.

        Args:
            max_steps: Maximum number of fixed steps to take this frame.

        Returns:
            The number of fixed steps actually consumed.

        Raises:
            ValueError: If max_steps is not > 0.
        """
        ...

    def set_time_scale(self, value: float) -> None:
        """Set the multiplier applied to raw delta time (e.g. for slow-mo).

        Raises:
            ValueError: If value is negative.
        """
        ...

    def set_fixed_timestep_hz(self, hz: int) -> None:
        """Set the fixed-update rate in hertz (e.g. 60 -> 1/60s steps).

        Raises:
            ValueError: If hz is not > 0.
        """
        ...

    @property
    def is_paused(self) -> bool:
        """Whether the frame clock is paused (time_scale == 0)."""
        ...

    def pause(self) -> None:
        """Pause the frame clock, remembering the current time scale."""
        ...

    def resume(self) -> None:
        """Resume the frame clock at the time scale active before pause()."""
        ...

    def reset(self) -> None:
        """Reset frame-clock state while leaving the native window untouched."""
        ...


@runtime_checkable
class IRenderPass(Protocol):
    """Named render pass entry.

    Attributes:
        name: Pass name.
        order: Sort order; lower values run first.
        enabled: Whether the pass is active.
    """

    name: str
    order: int
    enabled: bool


@runtime_checkable
class IUnifiedBufferBatch(Protocol):
    """Native UBR: init once, one ``submit_frame`` per flush."""

    @property
    def capacity(self) -> int:
        """Maximum number of sprites the batch can hold."""
        ...

    def init(self, max_sprites: int) -> None:
        """Initialize the batch with the given sprite capacity.

        Args:
            max_sprites: Maximum number of sprites per frame.

        Raises:
            RuntimeError: If native/rlgl is not ready (fail-fast).
        """
        ...

    def shutdown(self) -> None:
        """Release the batch's native buffers."""
        ...

    def submit_frame(
        self,
        *,
        pos_xy: np.ndarray,
        size_wh: np.ndarray,
        origin_xy: np.ndarray,
        rotation_deg: np.ndarray,
        rgba: np.ndarray,
        uv_rect: np.ndarray,
        run_starts: np.ndarray,
        run_counts: np.ndarray,
        run_tex_ids: np.ndarray,
        n_sprites: int,
        n_runs: int,
    ) -> None:
        """Submit a whole frame in a single FFI call: expand + upload + draw.

        Args:
            pos_xy: Per-sprite positions ``(n_sprites, 2)``.
            size_wh: Per-sprite sizes ``(n_sprites, 2)``.
            origin_xy: Per-sprite origins ``(n_sprites, 2)``.
            rotation_deg: Per-sprite rotations in degrees ``(n_sprites,)``.
            rgba: Per-sprite RGBA colors ``(n_sprites, 4)``.
            uv_rect: Per-sprite UV rectangles ``(n_sprites, 4)``.
            run_starts: Start index of each texture run ``(n_runs,)``.
            run_counts: Sprite count of each texture run ``(n_runs,)``.
            run_tex_ids: Texture id of each run ``(n_runs,)``.
            n_sprites: Total number of sprites.
            n_runs: Total number of texture runs.

        Raises:
            Exception: If the native submission fails.
        """
        ...


IBatchingBackend = IUnifiedBufferBatch


__all__ = [
    "IBatchingBackend",
    "ICanvas2D",
    "IRenderPass",
    "IUnifiedBufferBatch",
    "IWindow",
]
