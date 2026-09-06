"""Canvas helper :class:`DrawScope` (circle/rect/line/texture + GPU modes).

Not the production sprite path (that is UBR via ``submit_*``). Used for
custom drawing / tools. Stencil: :meth:`DrawScope.stencil`.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from plyunit.core.types import ColorType, RectType, ShaderType
from plyunit.rendering.enum import BlendMode

if TYPE_CHECKING:
    from plyunit.rendering.renderer import Renderer


class _StencilSession:
    """Handle returned by :meth:`DrawScope.stencil` for the mask/content phases.

    Attributes:
        mask: Context manager that writes invisible stencil geometry
            (the shape(s) drawn inside become the mask).
    """

    __slots__ = ("_inverse", "_scope")

    def __init__(self, scope: DrawScope, *, inverse: bool) -> None:
        """Initializes a stencil session.

        Args:
            scope: Owning :class:`DrawScope`.
            inverse: ``True`` for inverse masking (content outside the shape).
        """
        self._scope = scope
        self._inverse = inverse

    @contextmanager
    def mask(self) -> Generator[None]:
        """Writes invisible stencil geometry (shapes become the mask).

        Yields:
            None: Duration of mask writing.

        Note:
            Automatically calls ``end_stencil_mask`` (or the inverse
            variant) when the block exits.
        """
        canvas = self._scope.canvas
        canvas.begin_stencil_mask()
        self._scope._stencil_active = True
        try:
            yield
        finally:
            if self._inverse:
                canvas.end_stencil_mask_inverse()
            else:
                canvas.end_stencil_mask()


class DrawScope:
    """Canvas helper + nested GPU state context managers.

    Scissor/blend/shader state opened inside is restored when the nested
    block exits.

    Attributes:
        canvas: The renderer's backend canvas.
    """

    def __init__(self, renderer: Renderer) -> None:
        """Initializes a ``DrawScope`` owned by ``renderer``.

        Args:
            renderer: :class:`Renderer` hosting this scope.
        """
        self._renderer = renderer
        self._scissor_stack: list[tuple[int, int, int, int] | None] = []
        self._blend_stack: list[int | None] = []
        self._shader_stack: list[Any | None] = []
        self._texture_stack: list[Any | None] = []
        self._active_scissor: tuple[int, int, int, int] | None = None
        self._active_blend: int | None = None
        self._active_shader: Any | None = None
        self._active_texture: Any | None = None
        self._stencil_active: bool = False

    @property
    def canvas(self):
        """The renderer's backend canvas (read-only)."""
        return self._renderer.canvas

    def force_reset(self) -> None:
        """Pops every open GPU mode (shader/blend/scissor/texture/stencil)."""
        canvas = self._renderer.canvas
        if self._active_shader is not None:
            canvas.end_shader_mode()
        self._shader_stack.clear()
        self._active_shader = None
        if self._active_blend is not None:
            canvas.end_blend_mode()
        self._blend_stack.clear()
        self._active_blend = None
        if self._active_scissor is not None:
            canvas.end_scissor_mode()
        self._scissor_stack.clear()
        self._active_scissor = None
        if self._active_texture is not None:
            canvas.end_texture_mode()
        self._texture_stack.clear()
        self._active_texture = None
        if self._stencil_active:
            canvas.end_stencil_mode()
            self._stencil_active = False

    def _resolve_shader(self, shader_or_handle: Any) -> ShaderType:
        """Resolves a handle/wrapped/raw shader into a backend shader.

        Args:
            shader_or_handle: Shader object or :class:`ShaderHandle`.

        Returns:
            ShaderType: Backend shader object ready to use.
        """
        raw = getattr(shader_or_handle, "raw", None)
        if raw is not None:
            return raw
        shader = getattr(shader_or_handle, "shader", None)
        if shader is not None and not callable(shader):
            return shader
        return shader_or_handle

    @contextmanager
    def scissor(self, x: float, y: float, w: float, h: float) -> Generator[None]:
        """Scissor context manager (clips rendering to a rect).

        Args:
            x: Left X of the clip area in pixels.
            y: Top Y of the clip area in pixels.
            w: Width of the clip area in pixels.
            h: Height of the clip area in pixels.

        Yields:
            None: Duration of the clip.

        Note:
            Raylib scissor is replace-mode: leaving the scope restores
            the parent scissor, if any.
        """
        # Raylib scissor is replace-mode: end current, begin new, restore parent.
        canvas = self.canvas
        prev = self._active_scissor
        self._scissor_stack.append(prev)
        if prev is not None:
            canvas.end_scissor_mode()
        rect = (int(x), int(y), int(w), int(h))
        canvas.begin_scissor_mode(*rect)
        self._active_scissor = rect
        try:
            yield
        finally:
            canvas.end_scissor_mode()
            self._scissor_stack.pop()
            self._active_scissor = prev
            if prev is not None:
                canvas.begin_scissor_mode(*prev)

    @contextmanager
    def blend(self, mode: BlendMode | int) -> Generator[None]:
        """Blend mode context manager (temporarily replaces the active mode).

        Args:
            mode: Blend mode (:class:`BlendMode` enum or int).

        Yields:
            None: Duration of the blend mode.

        Note:
            ``begin_blend_mode`` is replace-mode; no ``end`` is needed
            when nesting. On exit, the parent mode is restored.
        """
        canvas = self.canvas
        prev = self._active_blend
        self._blend_stack.append(prev)
        mode_i = int(mode)
        canvas.begin_blend_mode(mode_i)
        self._active_blend = mode_i
        try:
            yield
        finally:
            self._blend_stack.pop()
            self._active_blend = prev
            if prev is not None:
                canvas.begin_blend_mode(prev)
            else:
                canvas.end_blend_mode()

    @contextmanager
    def shader(self, shader_or_handle: Any) -> Generator[None]:
        """Shader context manager (temporarily replaces the active shader).

        Args:
            shader_or_handle: :class:`ShaderType` or :class:`ShaderHandle`.

        Yields:
            None: Duration of the shader.

        Note:
            ``begin_shader_mode`` is replace-mode; ``end_shader_mode``
            is only called when exiting the outermost scope.
        """
        canvas = self.canvas
        prev = self._active_shader
        self._shader_stack.append(prev)
        resolved = self._resolve_shader(shader_or_handle)
        canvas.begin_shader_mode(resolved)
        self._active_shader = resolved
        try:
            yield
        finally:
            self._shader_stack.pop()
            self._active_shader = prev
            if prev is not None:
                canvas.begin_shader_mode(prev)
            else:
                canvas.end_shader_mode()

    @contextmanager
    def texture_mode(self, target: Any) -> Generator[None]:
        """Render-to-texture context manager.

        Args:
            target: Backend render texture target.

        Yields:
            None: Duration of render-to-texture.

        Note:
            Automatically restores the parent texture target on block exit.
        """
        canvas = self.canvas
        prev = self._active_texture
        self._texture_stack.append(prev)
        if prev is not None:
            canvas.end_texture_mode()
        canvas.begin_texture_mode(target)
        self._active_texture = target
        try:
            yield
        finally:
            canvas.end_texture_mode()
            self._texture_stack.pop()
            self._active_texture = prev
            if prev is not None:
                canvas.begin_texture_mode(prev)

    @contextmanager
    def stencil(self, *, inverse: bool = False) -> Iterator[_StencilSession]:
        """Stencil masking session (write mask → test content → restore).

        Example::

            with draw.stencil() as st:
                with st.mask():
                    draw.circle(200, 200, 80)
                draw.rect((0, 0, 400, 400), (255, 0, 0, 255))  # clipped to circle

            with draw.stencil(inverse=True) as st:
                with st.mask():
                    draw.circle(200, 200, 80)
                draw.texture(...)  # only outside the circle
        """
        if self._stencil_active:
            raise RuntimeError("Nested DrawScope.stencil() is not supported")
        session = _StencilSession(self, inverse=inverse)
        try:
            yield session
        finally:
            if self._stencil_active:
                self.canvas.end_stencil_mode()
                self._stencil_active = False

    def circle(
        self,
        x: float,
        y: float,
        radius: float,
        color: ColorType = (255, 255, 255, 255),
    ) -> None:
        """Draws a filled circle at the given position.

        Args:
            x: Center X in pixels.
            y: Center Y in pixels.
            radius: Radius in pixels.
            color: RGBA color.
        """
        self.canvas.draw_circle(center=(x, y), radius=radius, color=color)

    def rect(
        self,
        rect: RectType,
        color: ColorType = (255, 255, 255, 255),
    ) -> None:
        """Draws a rectangle at the given coordinates and size.

        Args:
            rect: ``(x, y, w, h)`` in pixels.
            color: RGBA color.
        """
        self.canvas.draw_rectangle(rect=rect, color=color)

    def line(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: ColorType = (255, 255, 255, 255),
    ) -> None:
        """Draws a line between two points.

        Args:
            start: Start point ``(x, y)``.
            end: End point ``(x, y)``.
            color: RGBA color.
        """
        self.canvas.draw_line(start=start, end=end, color=color)

    def texture(self, **kwargs: Any) -> None:
        """Draws a texture, forwarding kwargs to ``canvas.draw_texture``.

        Args:
            **kwargs: Backend-specific parameters (texture, pos, source, etc.).
        """
        self.canvas.draw_texture(**kwargs)
