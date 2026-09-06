"""SpriteRenderer component (binds texture + source rect + blend mode)."""

from __future__ import annotations

import logging
import weakref
from typing import TYPE_CHECKING

from plyunit.core.components import Component
from plyunit.core.types import ColorType, SourceRectType, Texture, Vec2Type
from plyunit.rendering.enum import Layer
from plyunit.rendering.render_context import RenderContext

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from plyunit.rendering.renderer import Renderer


class SpriteRenderer(Component):
    """Component that renders a sprite (2D image) on a unit.

    Manages texture, frame animation, flipping, scaling, and render order.
    Supports transform interpolation for smooth motion and source rects for
    sprite sheets.

    Attributes:
        layer: Render layer that determines draw order (lower values are drawn
            first).
        pivot: Pivot point for rotation, relative to the unit position (0,0 = top-left).
        visible: Whether the sprite is drawn during rendering.
        flip_x: Flip the sprite horizontally (mirror-x).
        flip_y: Flip the sprite vertically (mirror-y).
        use_interpolation: Use the interpolated transform for smooth motion.
        tint: RGBA filter color (0-255) applied to the sprite.
        source_rect: Region of the texture to draw, for sprite sheets.
    """

    renders = True
    render_kind = "sprite"

    def __init__(
        self,
        asset_key: str | None = None,
        texture: Texture | None = None,
        *,
        source_rect: SourceRectType | None = None,
        pivot: Vec2Type = (0.0, 0.0),
        visible: bool = True,
        name: str | None = None,
        flip_x: bool = False,
        flip_y: bool = False,
        use_interpolation: bool = True,
        tint: ColorType = (255, 255, 255, 255),
        scale: float = 1.0,
        layer: int | None = None,
        z_index: int | None = None,
    ) -> None:
        """Initializes the SpriteComponent.

        Args:
            asset_key: Key used to fetch the texture from the AssetManager.
            texture: Direct texture (alternative to asset_key).
            source_rect: Region (x, y, w, h) of the texture to draw.
                        None = use the entire texture.
            layer: Render layer (default WORLD). Lower values are drawn first.
            pivot: Rotation pivot point (default top-left).
            visible: Whether the sprite is visible (default True).
            name: Component name (optional).
            flip_x: Flip horizontally (default False).
            flip_y: Flip vertically (default False).
            use_interpolation: Use transform interpolation (default True).
            tint: RGBA filter color (default white = no tint).
            scale: Uniform scale multiplier applied to the sprite (default 1.0).
            z_index: Render order within the layer (default None). Lower values
                are drawn first.

        Raises:
            ValueError: If neither asset_key nor texture is provided.
        """
        super().__init__(name=name)
        self._asset_key = asset_key
        self._texture = texture
        # Weakref cache for the Assets service — resolving ``one("Assets")`` per
        # frame per sprite is a full registry query (render hot path). The weakref
        # is automatically invalidated when the service is replaced/destroyed
        # (e.g. in the editor).
        self._assets_ref: weakref.ref | None = None

        if self._asset_key is None and self._texture is None:
            raise ValueError("Either asset_key or texture must be provided")

        self.layer = layer
        self.pivot = pivot
        self.visible = visible
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.use_interpolation = use_interpolation
        self.tint = tint
        self.source_rect = source_rect if source_rect else None
        self.scale = scale
        self.z_index = z_index

    def _assets(self):
        """Resolves the Assets service with a weakref cache (see ``_assets_ref``)."""
        ref = self._assets_ref
        if ref is not None:
            assets = ref()
            if assets is not None:
                return assets
        if self.unit is None:
            return None
        assets = self.unit.one("Assets")
        self._assets_ref = weakref.ref(assets)
        return assets

    def texture(self) -> Texture:
        """Gets the current texture.

        If using asset_key, fetch it from the AssetManager.
        If using a direct texture, return that texture.

        Returns:
            Texture: The texture to be rendered.
        """
        if self._asset_key:
            assets = self._assets()
            if assets is None:
                raise RuntimeError(
                    "SpriteRenderer belum bisa resolve texture: unit belum "
                    "attach / service Assets tidak ditemukan."
                )
            return assets[self._asset_key]

        return self._texture

    def set_texture(
        self, *, asset_key: str | None = None, texture: Texture | None = None
    ) -> None:
        """Changes the sprite's texture.

        Args:
            asset_key: Key used to fetch the texture from the AssetManager.
            texture: Direct texture.

        Raises:
            ValueError: If neither asset_key nor texture is provided.
        """
        if asset_key is not None:
            self._asset_key = asset_key
            self._texture = None
        elif texture is not None:
            self._texture = texture
            self._asset_key = None
        else:
            raise ValueError("Either asset_key or texture must be provided")

    def set_source_rect(
        self, rect: tuple[float, float, float, float] | None = None
    ) -> None:
        """Changes the source rect for a sprite sheet.

        Args:
            rect: Region (x, y, w, h) of the texture to draw.
                  None = use the entire texture.
        """
        if rect is not None:
            self.source_rect = (
                rect[0],
                rect[1],
                rect[2],
                rect[3],
            )
        else:
            # Fallback using entire texture if source_rect is set to None
            # If source_rect is set to None, the entire texture is used as
            # the source rect. The source rect is auto-computed from the
            # current texture size, so setting None here is fine.
            self.source_rect = None

    def set_layer(self, layer: int) -> None:
        """Changes the sprite's render layer.

        Args:
            layer: Render layer (lower values are drawn first).
        """
        self.layer = layer

    def render_submit(
        self, renderer: Renderer, context: RenderContext | None = None
    ) -> None:
        """Submits the sprite to the render queue to be drawn.

        Called by the render system. Uses the interpolated transform for
        smooth motion if use_interpolation=True, otherwise uses the world
        transform.

        Args:
            renderer: Renderer instance.
        """
        if not self.visible:
            return

        if context is not None and context.render_transform is not None:
            transform = context.render_transform
        elif self.use_interpolation and self.unit:
            transform = self.unit.world_transform_lerp()
        else:
            transform = self.unit.transform.world

        texture = self.texture()

        z_index = self.z_index if self.z_index is not None else self.unit.z_index
        layer = self.layer if self.layer is not None else self.unit.layer

        pass_name = context.pass_name if context is not None else None
        state_id = context.state_id if context is not None else None
        y_sort = context.y_sort if context is not None else False
        y_sort_origin = context.y_sort_origin if context is not None else 0.0
        screen_space = context.screen_space if context is not None else None

        renderer.render_sprite(
            z=z_index,
            layer=Layer(layer),
            texture=texture,
            pos=transform.position,
            tint=self.tint,
            scale=self.scale,
            rotation=transform.rotation,
            origin=self.pivot,
            source=self._compute_flipped_source_rect(),
            pass_name=pass_name,
            state_id=state_id,
            y_sort=y_sort,
            y_sort_origin=y_sort_origin,
            screen_space=screen_space,
        )

    def render_submit_fast(
        self,
        renderer: Renderer,
        transform,
        *,
        pass_name: str | None,
        state_id: int,
        y_sort: bool,
        y_sort_origin: float,
        screen_space: bool | None,
    ) -> None:
        """Submit without allocating a RenderContext for common scene traversal."""
        if not self.visible:
            return

        layer = self.layer if self.layer is not None else self.unit.layer
        z_index = self.z_index if self.z_index is not None else self.unit.z_index

        renderer.render_sprite(
            z=z_index,
            layer=layer,
            texture=self.texture(),
            pos=transform.position,
            tint=self.tint,
            scale=self.scale,
            rotation=transform.rotation,
            origin=self.pivot,
            source=self._compute_flipped_source_rect(),
            pass_name=pass_name,
            state_id=state_id,
            y_sort=y_sort,
            y_sort_origin=y_sort_origin,
            screen_space=screen_space,
        )

    def get_render_bounds(self) -> tuple[float, float, float, float] | None:
        """Return world-space bounds for frustum culling."""
        if not self.visible:
            return None

        if self.use_interpolation and self.unit:
            transform = self.unit.world_transform_lerp()
        else:
            transform = self.unit.transform.world

        texture = self.texture()
        if texture.width <= 0 or texture.height <= 0:
            return None

        src = self.source_rect
        if src:
            w = abs(src[2]) * self.scale
            h = abs(src[3]) * self.scale
        else:
            w = texture.width * self.scale
            h = texture.height * self.scale

        px, py = transform.position
        ox, oy = self.pivot

        if transform.rotation != 0.0:
            import math

            rad = math.radians(transform.rotation)
            cos_r = abs(math.cos(rad))
            sin_r = abs(math.sin(rad))
            rw = w * cos_r + h * sin_r
            rh = w * sin_r + h * cos_r
            return (px - ox, py - oy, rw, rh)

        return (px - ox, py - oy, w, h)

    def _compute_flipped_source_rect(self) -> tuple[float, float, float, float] | None:
        """Computes the source rect while accounting for flip_x and flip_y.

        If source_rect is not provided, use the entire texture.
        If flip_x or flip_y is enabled, reverse the width or height direction
            (make the value negative).

        Raylib supports negative width/height for flipping. Examples:
        - source_rect=(0, 0, 100, 100) normal
        - source_rect=(100, 0, -100, 100) horizontal flip
        - source_rect=(0, 100, 100, -100) vertical flip

        Returns:
            tuple[float, float, float, float] | None: Source rect (x, y, w, h),
                or None if the texture is invalid.
        """
        source = self.source_rect
        if source is None and self._asset_key and self.unit:
            asset_manager = self._assets()
            if asset_manager is not None and hasattr(asset_manager, "get_source_rect"):
                source = asset_manager.get_source_rect(self._asset_key)

        if source is None:
            if not (self.flip_x or self.flip_y):
                return None

            texture = self.texture()
            width = texture.width
            height = texture.height

            # If the texture is invalid (e.g. width or height <= 0),
            # then there is no usable source rect
            if width <= 0.0 or height <= 0.0:
                return None

            # Flip needs an explicit source rect (negative w/h).
            source = (0.0, 0.0, width, height)

        if not (self.flip_x or self.flip_y):
            return source

        x, y, w, h = source
        if self.flip_x:
            x += w
            w = -w
        if self.flip_y:
            y += h
            h = -h
        return (x, y, w, h)
