"""Main plyunit renderer module managing the pass-based render pipeline.

Sprites: ``submit_*`` → FrameBuffer SoA → sort/runs → ``ubr_submit_frame``.
Non-sprites (primitives/text/custom) go through the ``RenderItem`` queue.
The tilemap, particle, debug, and UI sub-facades delegate to the same
submit calls.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any
from warnings import deprecated

import numpy as np

from plyunit.core.types import (
    ColorType,
    PrColor,
    RectType,
    RenderTexture,
    ShaderType,
    Texture,
    Vec2Type,
)
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.rendering.draw_primitive import draw_primitive
from plyunit.utils.geometry import aabb_intersection

from .draw_scope import DrawScope
from .enum import BlendMode, Layer, PrimitiveKind, RenderKind
from .frame_buffer import (
    MAX_SPRITES,
    FrameBuffer,
    build_depth_runs,
    build_runs,
    is_depth_sorted_layer,
    pass_name_hash,
    resolve_uv,
    runs_from_ordered,
    set_depth_sort_layers,
)
from .queue import _Y_SORT_LAYERS, CustomItem, PrimitiveItem, RenderItem, TextItem
from .render_state import (
    DEFAULT_RENDER_STATE,
    RenderContext,
    RenderPass,
    RenderStateCache,
)

if TYPE_CHECKING:
    from plyunit.backends.interfaces import ICamera2D
    from plyunit.backends.interfaces.i_renderer import ICanvas2D, IUnifiedBufferBatch

__all__ = [
    "_Y_SORT_LAYERS",
    "CustomItem",
    "RenderItem",
    "Renderer",
    "TextItem",
    "_intersect_rects",
]


def _xy(value: Vec2Type) -> tuple[float, float]:
    """Converts a vector-like to an ``(x, y)`` float tuple."""
    if hasattr(value, "x") and hasattr(value, "y"):
        return float(value.x), float(value.y)
    # pyrefly: ignore [unnecessary-type-conversion]
    return float(value[0]), float(value[1])


def _rgba(tint: ColorType) -> tuple[int, int, int, int]:
    """Converts a color-like to an ``(r, g, b, a)`` int tuple."""
    if hasattr(tint, "r"):
        return int(tint.r), int(tint.g), int(tint.b), int(tint.a)

    return int(tint[0]), int(tint[1]), int(tint[2]), int(tint[3])


class Renderer(ServiceUnit):
    """Typed, pass-based renderer facade for plyunit.

    Sprites go through the FrameBuffer SoA + native UBR. Non-sprites go
    through the ``RenderItem`` queue. Sub-facades: ``tilemaps``,
    ``particles``, ``debug``, ``ui``.

    Attributes:
        canvas: Backend canvas for primitives/text/custom.
        state_cache: Render state cache (scissor/blend/shader).
        tilemaps: Tilemap sub-facade.
        particles: Particle sub-facade.
        debug: Debug draw sub-facade.
        ui: UI sub-facade.
        draw: ``DrawScope`` canvas helper.
        profile_enabled: Per-frame profiling.
        frame_profile: Statistics for the frame in progress.
        last_frame_profile: Statistics of the finished frame.
    """

    def __init__(
        self,
        canvas: ICanvas2D,
        *,
        ubr: IUnifiedBufferBatch | None = None,
        frame_buffer: FrameBuffer | None = None,
        max_sprites: int = MAX_SPRITES,
    ) -> None:
        """Initializes the renderer with a canvas + UBR.

        Args:
            canvas: :class:`~plyunit.backends.interfaces.ICanvas2D` implementation.
            ubr: :class:`~plyunit.backends.interfaces.IUnifiedBufferBatch`
                from the composition root.
            frame_buffer: SoA frame buffer; created new when ``None``.
            max_sprites: FrameBuffer / UBR capacity.

        Raises:
            RuntimeError: If ``ubr`` is not provided.
        """
        super().__init__(name="Renderer", tags={"service", "renderer"})
        self.canvas = canvas
        self.state_cache = RenderStateCache()
        if ubr is None:
            raise RuntimeError(
                "C-extension UBR wajib di-wire (Renderer(ubr=...)). "
                "Tidak ada fallback Python. "
                "Gunakan init atau get_batching_backend()."
            )
        self._ubr = ubr
        self._frame_buffer = frame_buffer or FrameBuffer(capacity=max_sprites)
        self._frame_buffer.set_on_full(self._force_flush_sprites)
        self._last_active_state = 0

        self._items: list[RenderItem] = []
        self._render_passes: dict[str, RenderPass] = {}
        self._next_submit_index = 0
        self._is_rendering = False
        # pyrefly: ignore [bad-argument-type]
        self.draw = DrawScope(self)
        self.profile_enabled = False
        self.frame_profile: dict[str, float] = {}
        self.last_frame_profile: dict[str, float] = {}
        self._ensure_default_passes()

        # EFFECTS: depth-correct (not free texture sort). UI keeps submit order
        # via stable sort within layer groups.
        set_depth_sort_layers({int(Layer.EFFECTS)})

        # GPU setup must happen only after the host creates its graphics context.
        self._max_sprites = max_sprites
        self._ubr_init = False
        self._shutdown = False
        self.reset_frame()

    def init(self) -> None:
        """Initialize UBR resources after the graphics context exists."""
        if self._ubr_init:
            return
        if self._shutdown:
            raise RuntimeError("Cannot initialize a renderer after shutdown")
        self._ubr.init(self._max_sprites)
        self._ubr_init = True

    def reset_frame(self) -> None:
        """Begins a frame: resets the FrameBuffer, non-sprite queue, and state."""
        self._items.clear()
        self._frame_buffer.reset()
        self._next_submit_index = 0
        self.state_cache.clear()
        if self.profile_enabled:
            self.frame_profile = {
                "render_sort_ms": 0.0,
                "render_flush_ms": 0.0,
                "render_total_ms": 0.0,
                "render_item_count": 0.0,
                "primitive_item_count": 0.0,
                "custom_item_count": 0.0,
                "sprite_count": 0.0,
                "sprite_batch_count": 0.0,
                "texture_run_count": 0.0,
                "draw_call_count": 0.0,
            }

    def shutdown(self) -> None:
        """Frees the queue and UBR exactly once before the window closes."""
        if self._shutdown:
            return
        self._shutdown = True
        self._items.clear()
        self._frame_buffer.reset()
        self._next_submit_index = 0
        self._ubr.shutdown()
        self._ubr_init = False

    def intern_state(
        self,
        *,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
    ) -> int:
        """Interns a render state combination and returns its unique id.

        Args:
            scissor: Optional scissor rect.
            blend_mode: Blend mode (``BlendMode`` or int).
            shader: Optional shader to enable.

        Returns:
            int: The interned state id, reusable by subsequent items
            with identical state.
        """
        return self.state_cache.intern(
            scissor=scissor, blend_mode=blend_mode, shader=shader
        )

    def context_for_node(
        self,
        *,
        pass_name: str,
        layer: int,
        z: float,
        scissor: RectType | None,
        blend_mode: BlendMode | int,
        shader: ShaderType | None,
        y_sort: bool,
        y_sort_origin: float,
        world_transform=None,
        render_transform=None,
    ) -> RenderContext:
        """Builds a complete ``RenderContext`` for a scene node.

        Interns the render state and packs it together with pass,
        layer, Z, and transform information into a ``RenderContext``
        ready for use at flush time.

        Args:
            pass_name: Target pass name (``"world"``, ``"ui"``, etc.).
            layer: Render layer that determines automatic screen-space.
            z: Z value for depth ordering.
            scissor: Optional scissor rect.
            blend_mode: Blend mode to use.
            shader: Optional shader.
            y_sort: Whether to use Y-sort for this layer.
            y_sort_origin: Reference axis for Y-sort.
            world_transform: Optional world transform.
            render_transform: Optional render transform.

        Returns:
            RenderContext: The render context, ready to use.
        """
        state_id = self.intern_state(
            scissor=scissor, blend_mode=blend_mode, shader=shader
        )
        return RenderContext(
            pass_name=pass_name,
            layer=layer,
            z=z,
            screen_space=layer >= int(Layer.UI),
            scissor=scissor,
            blend_mode=BlendMode(blend_mode),
            shader=shader,
            state_id=state_id,
            y_sort=y_sort,
            y_sort_origin=float(y_sort_origin),
            world_transform=world_transform,
            render_transform=render_transform,
        )

    def _queue_item(
        self,
        *,
        kind: RenderKind,
        payload: PrimitiveItem | TextItem | CustomItem,
        z: float,
        layer: int,
        pass_name: str | None = None,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
        state_id: int | None = None,
        y_sort: bool = False,
        y_sort_origin: float = 0.0,
        screen_space: bool | None = None,
    ) -> None:
        """Internal: enqueues an item into this frame's render queue.

        Computes pass and screen-space automatically when not given,
        interns state when needed, and records profiling statistics
        when enabled.

        Args:
            kind: Render item kind (``RenderKind``).
            payload: Specific payload matching ``kind``.
            z: Z value for ordering.
            layer: Render layer.
            pass_name: Target pass name; defaults to ``world``/``ui``.
            scissor: Optional scissor rect.
            blend_mode: Blend mode for the item's state.
            shader: Shader for the item's state.
            state_id: Already-interned state id.
            y_sort: Force Y-sort for this item.
            y_sort_origin: Y-sort reference axis.
            screen_space: Force the item's screen-space flag.

        Raises:
            RuntimeError: If submitted while a flush is in progress
                (``flush_all``).
        """
        if self._is_rendering:
            raise RuntimeError("cannot submit to renderer during flush_all")

        layer_int = int(layer)
        item_pass = pass_name or ("ui" if layer_int >= int(Layer.UI) else "world")
        if item_pass == "default":
            item_pass = "world"
        item_screen_space = (
            layer_int >= int(Layer.UI) if screen_space is None else screen_space
        )
        item_state_id = state_id
        if item_state_id is None:
            item_state_id = self.intern_state(
                scissor=scissor, blend_mode=blend_mode, shader=shader
            )
        use_y_sort = y_sort or layer_int in _Y_SORT_LAYERS
        sort_key = float(y_sort_origin if use_y_sort else z)
        self._items.append(
            RenderItem(
                kind=kind,
                payload=payload,
                pass_name=item_pass,
                layer=layer_int,
                sort_key=sort_key,
                submit_index=self._next_submit_index,
                state_id=item_state_id,
                screen_space=item_screen_space,
            )
        )
        self._next_submit_index += 1
        if self.profile_enabled:
            self.frame_profile["render_item_count"] = (
                self.frame_profile.get("render_item_count", 0.0) + 1.0
            )
            if kind is RenderKind.CUSTOM:
                self.frame_profile["custom_item_count"] = (
                    self.frame_profile.get("custom_item_count", 0.0) + 1.0
                )
            elif kind is RenderKind.PRIMITIVE:
                self.frame_profile["primitive_item_count"] = (
                    self.frame_profile.get("primitive_item_count", 0.0) + 1.0
                )

    def render_sprite(
        self,
        *,
        texture: Texture,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        pos: Vec2Type = (0.0, 0.0),
        source: RectType | None = None,
        dest: RectType | None = None,
        origin: Vec2Type = (0.0, 0.0),
        rotation: float = 0.0,
        scale: float = 1.0,
        tint: ColorType = (255, 255, 255, 255),
        pass_name: str | None = None,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
        state_id: int | None = None,
        y_sort: bool = False,
        y_sort_origin: float = 0.0,
        screen_space: bool | None = None,
    ) -> None:
        """Writes a single sprite in place into the FrameBuffer (UBR).

        UV is resolved here; expand/upload/draw happens at flush via
        ``ubr_submit_frame``. A ``None`` ``texture`` is ignored.

        Args:
            texture: Source texture; ``None`` is ignored without error.
            z: Z value for ordering.
            layer: Render layer.
            pos: Sprite position in world space.
            source: Optional source rect on the texture.
            dest: Destination rect; when ``None`` uses ``pos`` + size.
            origin: Pivot point for rotation/scale.
            rotation: Rotation in degrees.
            scale: Scale factor.
            tint: RGBA tint color.
            pass_name: Target pass name.
            scissor: Optional scissor rect.
            blend_mode: Blend mode to use.
            shader: Optional shader.
            state_id: Already-interned state id.
            y_sort: Force Y-sort for this sprite.
            y_sort_origin: Y-sort reference axis.
            screen_space: Force screen-space for this sprite.
        """
        if texture is None:
            return
        if self._is_rendering:
            raise RuntimeError("cannot submit to renderer during flush_all")

        layer_int = int(layer)
        use_y_sort = y_sort or layer_int in _Y_SORT_LAYERS
        item_pass = pass_name or ("ui" if layer_int >= int(Layer.UI) else "world")
        if item_pass == "default":
            item_pass = "world"
        item_screen_space = (
            layer_int >= int(Layer.UI) if screen_space is None else screen_space
        )
        item_state_id = state_id
        if item_state_id is None:
            item_state_id = self.intern_state(
                scissor=scissor, blend_mode=blend_mode, shader=shader
            )
        sort_key = float(y_sort_origin if use_y_sort else z)

        tw = float(getattr(texture, "width", 1) or 1)
        th = float(getattr(texture, "height", 1) or 1)
        if dest is not None:
            px, py = float(dest[0]), float(dest[1])
            dw, dh = float(dest[2]), float(dest[3])
        else:
            px, py = _xy(pos)
            if source is not None:
                dw = abs(float(source[2])) * float(scale)
                dh = abs(float(source[3])) * float(scale)
            else:
                dw = tw * float(scale)
                dh = th * float(scale)
        ox, oy = _xy(origin)
        r, g, b, a = _rgba(tint)
        uv = resolve_uv(source, tw, th)
        idx = self._frame_buffer.append(
            pos=(px, py),
            size=(dw, dh),
            origin=(ox, oy),
            rotation=float(rotation),
            rgba=(r, g, b, a),
            uv=uv,
            tex_id=int(texture.id),
            sort_key=sort_key,
            layer=layer_int,
            state_id=int(item_state_id),
            pass_hash=pass_name_hash(item_pass),
            submit_index=self._next_submit_index,
            depth_sorted=is_depth_sorted_layer(layer_int, use_y_sort),
            screen_space=bool(item_screen_space),
        )
        self._next_submit_index += 1
        if idx < 0:
            return
        if self.profile_enabled:
            self.frame_profile["sprite_count"] = (
                self.frame_profile.get("sprite_count", 0.0) + 1.0
            )

    def render_batch(
        self,
        *,
        texture: Texture,
        positions: list[Vec2Type] | Any,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        source: RectType | None = None,
        origin: Vec2Type = (0.0, 0.0),
        rotation: float = 0.0,
        scale: float = 1.0,
        tint: ColorType = (255, 255, 255, 255),
        pass_name: str | None = None,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
        state_id: int | None = None,
        y_sort: bool = False,
        y_sort_origin: float = 0.0,
        screen_space: bool | None = None,
        pos_xy: Any | None = None,
    ) -> None:
        """Submits a batch of one sprite (one texture) at many positions.

        Sprites are drawn at many positions at once into the
        FrameBuffer (UBR).
        """
        if texture is None:
            return
        if self._is_rendering:
            raise RuntimeError("cannot submit to renderer during flush_all")
        if pos_xy is None and (positions is None or len(positions) == 0):
            return

        layer_int = int(layer)
        use_y_sort = y_sort or layer_int in _Y_SORT_LAYERS
        item_pass = pass_name or ("ui" if layer_int >= int(Layer.UI) else "world")
        if item_pass == "default":
            item_pass = "world"
        item_screen_space = (
            layer_int >= int(Layer.UI) if screen_space is None else screen_space
        )
        item_state_id = state_id
        if item_state_id is None:
            item_state_id = self.intern_state(
                scissor=scissor, blend_mode=blend_mode, shader=shader
            )
        sort_key = float(y_sort_origin if use_y_sort else z)

        tw = float(getattr(texture, "width", 1) or 1)
        th = float(getattr(texture, "height", 1) or 1)
        if source is not None:
            dw = abs(float(source[2])) * float(scale)
            dh = abs(float(source[3])) * float(scale)
        else:
            dw = tw * float(scale)
            dh = th * float(scale)
        ox, oy = _xy(origin)
        r, g, b, a = _rgba(tint)
        uv = resolve_uv(source, tw, th)

        if pos_xy is not None:
            arr = pos_xy
        else:
            import numpy as np

            n = len(positions)
            arr = np.empty((n, 2), dtype=np.float32)
            for i, p in enumerate(positions):
                arr[i, 0], arr[i, 1] = _xy(p)

        written = self._frame_buffer.append_batch(
            pos_xy=arr,
            size_wh=(dw, dh),
            origin_xy=(ox, oy),
            rotation=float(rotation),
            rgba=(r, g, b, a),
            uv=uv,
            tex_id=int(texture.id),
            sort_key=sort_key,
            layer=layer_int,
            state_id=int(item_state_id),
            pass_hash=pass_name_hash(item_pass),
            submit_index_start=self._next_submit_index,
            depth_sorted=is_depth_sorted_layer(layer_int, use_y_sort),
            screen_space=bool(item_screen_space),
        )
        self._next_submit_index += written
        if self.profile_enabled and written:
            self.frame_profile["sprite_count"] = self.frame_profile.get(
                "sprite_count", 0.0
            ) + float(written)
            self.frame_profile["sprite_batch_count"] = (
                self.frame_profile.get("sprite_batch_count", 0.0) + 1.0
            )

    def render_sprites(
        self,
        *,
        textures: Sequence[Texture] | Any,
        positions: Sequence[Vec2Type] | Any | None = None,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        sources: Sequence[RectType | None] | None = None,
        origins: Sequence[Vec2Type] | None = None,
        rotations: Sequence[float] | None = None,
        scales: Sequence[float] | None = None,
        tints: Sequence[ColorType] | None = None,
        pass_name: str | None = None,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
        state_id: int | None = None,
        y_sort: bool = False,
        y_sort_origin: float = 0.0,
        screen_space: bool | None = None,
        pos_xy: Any | None = None,
    ) -> None:
        """Submits N sprites (N distinct textures) at once to the FrameBuffer (UBR).

        The inverse of :meth:`render_batch` (one texture, many
        positions): ``render_sprites`` draws N distinct textures at N
        positions — e.g. the output of ``canvas.create_rects`` — without
        a per-sprite ``render_sprite`` loop. Render state (pass, layer,
        z, scissor, blend, shader) is interned once; only texture/UV/
        size/transform differ per sprite. ``None`` textures are ignored.

        Args:
            textures: Sequence of N textures; ``None`` entries are skipped.
            positions: Sequence of N positions ``(x, y)`` parallel to
                ``textures`` (shorter length truncates the batch).
            z: Z value for ordering (shared across the whole batch).
            layer: Render layer.
            sources: Optional sequence of N source rects (atlas /
                spritesheet regions); ``None`` uses the full texture.
            origins: Sequence of N pivot points; ``None`` means (0, 0).
            rotations: Sequence of N rotations in degrees; ``None`` means 0.
            scales: Sequence of N scale factors; ``None`` means 1.
            tints: Sequence of N RGBA tint colors; ``None`` means white.
            pass_name: Target pass name.
            scissor: Optional scissor rect.
            blend_mode: Blend mode to use.
            shader: Optional shader.
            state_id: Already-interned state id.
            y_sort: Force Y-sort for this batch.
            y_sort_origin: Y-sort reference axis.
            screen_space: Force screen-space for this batch.
            pos_xy: Position fast path: a contiguous ``(n, 2)`` float32
                array (replaces ``positions``).
        """
        if textures is None:
            return
        if self._is_rendering:
            raise RuntimeError("cannot submit to renderer during flush_all")

        if pos_xy is not None:
            pos_arr = np.ascontiguousarray(pos_xy, dtype=np.float32)
            if pos_arr.ndim == 1:
                pos_arr = pos_arr.reshape(-1, 2)
            n = min(len(textures), int(pos_arr.shape[0]))
            pos_arr = pos_arr[:n]
        else:
            if positions is None or len(positions) == 0:
                return
            n = min(len(textures), len(positions))
            pos_arr = np.empty((n, 2), dtype=np.float32)
        if n <= 0:
            return

        tex_ids = np.empty(n, dtype=np.int32)
        sizes = np.empty((n, 2), dtype=np.float32)
        uvs = np.empty((n, 4), dtype=np.float32)
        orig = np.zeros((n, 2), dtype=np.float32)
        rots = np.zeros(n, dtype=np.float32)
        rgba = np.empty((n, 4), dtype=np.uint8)
        keep = np.ones(n, dtype=np.bool_)

        for i in range(n):
            texture = textures[i]
            if texture is None:
                keep[i] = False
                continue
            tw = float(getattr(texture, "width", 1) or 1)
            th = float(getattr(texture, "height", 1) or 1)
            tex_ids[i] = int(texture.id)
            source = sources[i] if sources is not None else None
            if source is not None:
                uvs[i] = resolve_uv(source, tw, th)
                sw = abs(float(source[2]))
                sh = abs(float(source[3]))
            else:
                uvs[i] = (0.0, 0.0, 1.0, 1.0)
                sw, sh = tw, th
            scale = float(scales[i]) if scales is not None else 1.0
            sizes[i, 0] = sw * scale
            sizes[i, 1] = sh * scale
            if origins is not None:
                ox, oy = _xy(origins[i])
                orig[i, 0] = ox
                orig[i, 1] = oy
            if rotations is not None:
                rots[i] = float(rotations[i])
            rgba[i] = _rgba(tints[i]) if tints is not None else (255, 255, 255, 255)
            if pos_xy is None:
                px, py = _xy(positions[i])  # type: ignore[index]
                pos_arr[i, 0] = px
                pos_arr[i, 1] = py

        if not bool(keep.all()):
            pos_arr = pos_arr[keep]
            tex_ids = tex_ids[keep]
            sizes = sizes[keep]
            uvs = uvs[keep]
            orig = orig[keep]
            rots = rots[keep]
            rgba = rgba[keep]
            n = int(pos_arr.shape[0])
            if n == 0:
                return

        layer_int = int(layer)
        use_y_sort = y_sort or layer_int in _Y_SORT_LAYERS
        item_pass = pass_name or ("ui" if layer_int >= int(Layer.UI) else "world")
        if item_pass == "default":
            item_pass = "world"
        item_screen_space = (
            layer_int >= int(Layer.UI) if screen_space is None else screen_space
        )
        item_state_id = state_id
        if item_state_id is None:
            item_state_id = self.intern_state(
                scissor=scissor, blend_mode=blend_mode, shader=shader
            )
        sort_key = float(y_sort_origin if use_y_sort else z)
        p_hash = pass_name_hash(item_pass)
        sid = int(item_state_id)
        depth = is_depth_sorted_layer(layer_int, use_y_sort)
        ss = bool(item_screen_space)

        fb = self._frame_buffer
        written = 0
        offset = 0
        while offset < n:
            space = fb.remaining()
            if space <= 0:
                fb._ensure_space(1)
                space = fb.remaining()
            chunk = min(n - offset, space)
            start = fb.count
            end = start + chunk
            sl = slice(offset, offset + chunk)
            fb.pos_xy[start:end] = pos_arr[sl]
            fb.size_wh[start:end] = sizes[sl]
            fb.origin_xy[start:end] = orig[sl]
            fb.rotation_deg[start:end] = rots[sl]
            fb.rgba[start:end] = rgba[sl]
            fb.uv_rect[start:end] = uvs[sl]
            fb.tex_id[start:end] = tex_ids[sl]
            fb.sort_key[start:end] = sort_key
            fb.layer[start:end] = layer_int
            fb.state_id[start:end] = sid
            fb.pass_hash[start:end] = p_hash
            fb.submit_index[start:end] = np.arange(
                self._next_submit_index + written,
                self._next_submit_index + written + chunk,
                dtype=np.int32,
            )
            fb.depth_sorted[start:end] = depth
            fb.screen_space[start:end] = ss
            fb.count = end
            written += chunk
            offset += chunk
            if offset < n and fb.remaining() == 0:
                fb._ensure_space(1)

        self._next_submit_index += written
        if self.profile_enabled and written:
            self.frame_profile["sprite_count"] = self.frame_profile.get(
                "sprite_count", 0.0
            ) + float(written)
            self.frame_profile["sprite_batch_count"] = (
                self.frame_profile.get("sprite_batch_count", 0.0) + 1.0
            )

    @deprecated("Gunakan render_shaped_text")
    def render_text(
        self,
        *,
        z: float = 0.0,
        layer: int = Layer.UI,
        pass_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Submits a text item to the render queue (legacy non-UBR path).

        Args:
            z: Z value for ordering.
            layer: Render layer (default ``Layer.UI``).
            pass_name: Target pass name.
            **kwargs: Text-specific arguments (``text``, ``font``,
                ``position``, ``size``, ``color``, and state).
        """
        state = self._extract_state(kwargs)
        self._queue_item(
            kind=RenderKind.TEXT,
            payload=TextItem(kwargs),
            z=z,
            layer=layer,
            pass_name=pass_name,
            **state,
        )

    def render_shaped_text(
        self,
        shaped: Any,
        *,
        pos: Vec2Type,
        color: ColorType = (255, 255, 255, 255),
        origin: Vec2Type = (0.0, 0.0),
        rotation: float = 0.0,
        z: float = 0.0,
        layer: int = Layer.UI,
        pass_name: str | None = None,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
        state_id: int | None = None,
        screen_space: bool | None = None,
    ) -> None:
        """Submits glyph quads from a ShapedText to the FrameBuffer SoA
        (same path as sprites).

        Not a special case: each glyph = one SoA row. ``tex_id`` =
        ``font.texture.id``; the UBR sort groups the same font into one run.
        Hot path is numpy vector ops only — no per-glyph Python loop.
        """
        import math

        n = int(shaped.offsets_xy.shape[0])
        if n == 0:
            return
        if self._is_rendering:
            raise RuntimeError("cannot submit to renderer during flush_all")

        layer_int = int(layer)
        item_pass = pass_name or ("ui" if layer_int >= int(Layer.UI) else "world")
        if item_pass == "default":
            item_pass = "world"
        item_screen_space = (
            layer_int >= int(Layer.UI) if screen_space is None else screen_space
        )
        item_state_id = (
            state_id
            if state_id is not None
            else self.intern_state(
                scissor=scissor, blend_mode=blend_mode, shader=shader
            )
        )
        sort_key = float(z)
        px, py = _xy(pos)
        ox, oy = _xy(origin)
        r, g, b, a = _rgba(color)
        rot = float(rotation)

        offsets = shaped.offsets_xy
        if rot == 0.0:
            world_pos = (
                offsets
                + np.array((px, py), dtype=np.float32)
                - np.array((ox, oy), dtype=np.float32)
            )
        else:
            rad = math.radians(rot)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            local = offsets - np.array((ox, oy), dtype=np.float32)
            rx = local[:, 0] * cos_r - local[:, 1] * sin_r + px
            ry = local[:, 0] * sin_r + local[:, 1] * cos_r + py
            world_pos = np.stack([rx, ry], axis=1)

        sizes = shaped.sizes_wh
        uvs = shaped.uv_rects
        tex_id = int(shaped.tex_id)
        p_hash = pass_name_hash(item_pass)
        depth = is_depth_sorted_layer(layer_int, False)
        sid = int(item_state_id)
        ss = bool(item_screen_space)

        fb = self._frame_buffer
        written = 0
        offset = 0
        while offset < n:
            space = fb.remaining()
            if space <= 0:
                fb._ensure_space(1)
                space = fb.remaining()
            chunk = min(n - offset, space)
            start = fb.count
            end = start + chunk
            sl = slice(offset, offset + chunk)
            # Bulk SoA write — same principle as the sprite UBR, no per-glyph loop
            fb.pos_xy[start:end] = world_pos[sl]
            fb.size_wh[start:end] = sizes[sl]
            fb.origin_xy[start:end] = 0.0
            fb.rotation_deg[start:end] = rot
            fb.rgba[start:end] = (r, g, b, a)
            fb.uv_rect[start:end] = uvs[sl]
            fb.tex_id[start:end] = tex_id
            fb.sort_key[start:end] = sort_key
            fb.layer[start:end] = layer_int
            fb.state_id[start:end] = sid
            fb.pass_hash[start:end] = p_hash
            fb.submit_index[start:end] = np.arange(
                self._next_submit_index + written,
                self._next_submit_index + written + chunk,
                dtype=np.int32,
            )
            fb.depth_sorted[start:end] = depth
            fb.screen_space[start:end] = ss
            fb.count = end
            written += chunk
            offset += chunk
            if offset < n and fb.remaining() == 0:
                fb._ensure_space(1)

        self._next_submit_index += written
        if self.profile_enabled and written:
            self.frame_profile["sprite_count"] = self.frame_profile.get(
                "sprite_count", 0.0
            ) + float(written)

    def render_custom(
        self,
        *,
        draw_func: Callable[[ICanvas2D], None],
        z: float = 0.0,
        layer: int = Layer.WORLD,
        pass_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Submits a custom drawing callback to the render queue.

        The callback is invoked when the related pass is flushed, with
        full access to the backend ``Canvas``.

        Args:
            draw_func: A ``(Canvas) -> None`` function performing
                drawing directly on the backend.
            z: Z value for ordering.
            layer: Render layer.
            pass_name: Target pass name.
            **kwargs: Additional state arguments (scissor, blend, etc.).
        """
        self._queue_item(
            kind=RenderKind.CUSTOM,
            payload=CustomItem(draw_func),
            z=z,
            layer=layer,
            pass_name=pass_name,
            **kwargs,
        )

    def _queue_primitive(
        self,
        kind: PrimitiveKind,
        payload: dict[str, Any],
        *,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        pass_name: str | None = None,
        **state: Any,
    ) -> None:
        """Internal: enqueues a primitive item into the render queue.

        Args:
            kind: Primitive kind (``PrimitiveKind``).
            payload: Primitive payload matching ``kind``.
            z: Z value for ordering.
            layer: Render layer.
            pass_name: Target pass name.
            **state: Additional render state arguments.
        """
        self._queue_item(
            kind=RenderKind.PRIMITIVE,
            payload=PrimitiveItem(kind, payload),
            z=z,
            layer=layer,
            pass_name=pass_name,
            **state,
        )

    @deprecated("Gunakan canvas.create_rect + render_sprite")
    def render_rect(
        self,
        *,
        rect: RectType,
        color: ColorType | None = None,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        **kwargs: Any,
    ) -> None:
        """Submits a rectangle primitive (deprecated).

        Args:
            rect: Rectangle ``(x, y, w, h)``.
            color: Optional RGBA color.
            z: Z value for ordering.
            layer: Render layer.
            **kwargs: Additional state arguments.
        """
        payload = {"rect": rect, **kwargs}
        if color is not None:
            payload["color"] = color
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.RECTANGLE, payload, z=z, layer=layer, **state
        )

    @deprecated("Gunakan canvas.create_circle + render_sprite")
    def render_circle(
        self,
        *,
        center: Vec2Type,
        radius: float,
        color: ColorType | None = None,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        **kwargs: Any,
    ) -> None:
        """Submits a circle primitive (deprecated).

        Args:
            center: Circle center position ``(x, y)``.
            radius: Circle radius.
            color: Optional RGBA color.
            z: Z value for ordering.
            layer: Render layer.
            **kwargs: Additional state arguments.
        """
        payload = {"center": center, "radius": radius, **kwargs}
        if color is not None:
            payload["color"] = color
        state = self._extract_state(payload)
        self._queue_primitive(PrimitiveKind.CIRCLE, payload, z=z, layer=layer, **state)

    @deprecated("Gunakan canvas.create_line + render_sprite")
    def render_line(
        self,
        *,
        start: Vec2Type,
        end: Vec2Type,
        color: ColorType | None = None,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        **kwargs: Any,
    ) -> None:
        """Submits a line primitive (deprecated).

        Args:
            start: Start point ``(x, y)``.
            end: End point ``(x, y)``.
            color: Optional RGBA color.
            z: Z value for ordering.
            layer: Render layer.
            **kwargs: Additional state arguments.
        """
        payload = {"start": start, "end": end, **kwargs}
        if color is not None:
            payload["color"] = color
        state = self._extract_state(payload)
        self._queue_primitive(PrimitiveKind.LINE, payload, z=z, layer=layer, **state)

    @deprecated("Gunakan canvas.create_triangle + render_sprite")
    def render_triangle(
        self,
        *,
        v1: Vec2Type,
        v2: Vec2Type,
        v3: Vec2Type,
        color: ColorType | None = None,
        z: float = 0.0,
        layer: int = Layer.WORLD,
        **kwargs: Any,
    ) -> None:
        """Submits a triangle primitive (deprecated).

        Args:
            v1: First vertex ``(x, y)``.
            v2: Second vertex ``(x, y)``.
            v3: Third vertex ``(x, y)``.
            color: Optional RGBA color.
            z: Z value for ordering.
            layer: Render layer.
            **kwargs: Additional state arguments.
        """
        payload = {"v1": v1, "v2": v2, "v3": v3, **kwargs}
        if color is not None:
            payload["color"] = color
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.TRIANGLE, payload, z=z, layer=layer, **state
        )

    @deprecated("Gunakan canvas.create_rects + render_sprites")
    def render_rects(
        self, *, rects: list[RectType], colors: list[ColorType], **kwargs: Any
    ) -> None:
        """Submits a batch of many rectangles at once (deprecated).

        Args:
            rects: List of rectangles.
            colors: List of RGBA colors matching ``rects``.
            **kwargs: Additional state arguments (``z``, ``layer``, etc.).
        """
        payload = {"rects": rects, "colors": colors, **kwargs}
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.RECTANGLES,
            payload,
            z=state.pop("z", 0.0),
            layer=state.pop("layer", Layer.WORLD),
            **state,
        )

    @deprecated("Gunakan canvas.create_circles + render_sprites")
    def render_circles(
        self,
        *,
        centers: list[Vec2Type],
        radii: list[float],
        colors: list[ColorType],
        **kwargs: Any,
    ) -> None:
        """Submits a batch of many circles at once (deprecated).

        Args:
            centers: List of circle center positions.
            radii: List of radii matching ``centers``.
            colors: List of colors matching ``centers``.
            **kwargs: Additional state arguments (``z``, ``layer``, etc.).
        """
        payload = {"centers": centers, "radii": radii, "colors": colors, **kwargs}
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.CIRCLES,
            payload,
            z=state.pop("z", 0.0),
            layer=state.pop("layer", Layer.WORLD),
            **state,
        )

    @deprecated("Gunakan canvas.create_lines + render_sprites")
    def render_lines(
        self,
        *,
        starts: list[Vec2Type],
        ends: list[Vec2Type],
        colors: list[ColorType],
        **kwargs: Any,
    ) -> None:
        """Submits a batch of many lines at once (deprecated).

        Args:
            starts: List of line start points.
            ends: List of end points matching ``starts``.
            colors: List of colors matching ``starts``.
            **kwargs: Additional state arguments (``z``, ``layer``, etc.).
        """
        payload = {"starts": starts, "ends": ends, "colors": colors, **kwargs}
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.LINES,
            payload,
            z=state.pop("z", 0.0),
            layer=state.pop("layer", Layer.WORLD),
            **state,
        )

    @deprecated("Gunakan canvas.create_triangles + render_sprites")
    def render_triangles(
        self,
        *,
        v1s: list[Vec2Type],
        v2s: list[Vec2Type],
        v3s: list[Vec2Type],
        colors: list[ColorType],
        **kwargs: Any,
    ) -> None:
        """Submits a batch of many triangles at once (deprecated).

        Args:
            v1s: List of first vertices.
            v2s: List of second vertices matching ``v1s``.
            v3s: List of third vertices matching ``v1s``.
            colors: List of colors matching ``v1s``.
            **kwargs: Additional state arguments (``z``, ``layer``, etc.).
        """
        payload = {"v1s": v1s, "v2s": v2s, "v3s": v3s, "colors": colors, **kwargs}
        state = self._extract_state(payload)
        self._queue_primitive(
            PrimitiveKind.TRIANGLES,
            payload,
            z=state.pop("z", 0.0),
            layer=state.pop("layer", Layer.WORLD),
            **state,
        )

    def _ensure_default_passes(self) -> None:
        """Registers the default ``world``, ``ui``, and ``debug`` passes if absent."""
        self._render_passes.setdefault(
            "world",
            RenderPass(
                name="world",
                order=0,
                min_layer=Layer.BACKGROUND,
                max_layer=Layer.UI_WORLD,
                screen_space=False,
            ),
        )
        self._render_passes.setdefault(
            "ui",
            RenderPass(
                name="ui",
                order=10,
                min_layer=Layer.UI,
                max_layer=Layer.OVERLAY,
                screen_space=True,
            ),
        )
        self._render_passes.setdefault(
            "debug",
            RenderPass(
                name="debug",
                order=20,
                min_layer=Layer.DEBUG,
                max_layer=Layer.DEBUG,
                screen_space=True,
            ),
        )

    @staticmethod
    def enable_y_sort_layer(layer: int, enabled: bool = True) -> None:
        """Enables/disables Y sorting for a given ``layer``.

        Args:
            layer: Layer index.
            enabled: True to add to the set; False to remove.
        """
        if enabled:
            _Y_SORT_LAYERS.add(int(layer))
        else:
            _Y_SORT_LAYERS.discard(int(layer))

    def create_pass(
        self,
        name: str,
        *,
        target: RenderTexture | None = None,
        camera: Any | None = None,
        clear_color: PrColor | None = None,
        viewport_scissor: RectType | None = None,
        order: int = 0,
        min_layer: int | None = None,
        max_layer: int | None = None,
        screen_space: bool = False,
    ) -> RenderPass:
        """Creates and registers a new ``RenderPass``.

        Args:
            name: Unique pass name.
            target: Optional render texture the pass draws into.
            camera: Optional camera; ``None`` for screen-space.
            clear_color: Optional clear color.
            viewport_scissor: Optional viewport scissor rect.
            order: Pass execution order (ascending).
            min_layer: Minimum layer of items the pass accepts.
            max_layer: Maximum layer of items the pass accepts.
            screen_space: True for a pass without a camera.

        Returns:
            RenderPass: The newly created and registered pass object.
        """
        render_pass = RenderPass(
            name=name,
            target=target,
            camera=camera,
            clear_color=clear_color,
            viewport_scissor=viewport_scissor,
            order=order,
            min_layer=min_layer,
            max_layer=max_layer,
            screen_space=screen_space,
        )
        self._render_passes[name] = render_pass
        return render_pass

    def get_pass(self, name: str) -> RenderPass | None:
        """Retrieves a ``RenderPass`` by name; ``default`` maps to ``world``.

        Args:
            name: Pass name (or ``"default"``).

        Returns:
            RenderPass | None: The matching pass, or ``None`` if not found.
        """
        if name == "default":
            return self._render_passes.get("world")
        return self._render_passes.get(name)

    def remove_pass(self, name: str) -> None:
        """Removes a pass by name; built-in passes cannot be removed.

        Args:
            name: Name of the pass to remove.
        """
        if name in {"default", "world", "ui", "debug"}:
            return
        self._render_passes.pop(name, None)

    def flush_all(self, camera: ICamera2D | None = None) -> None:
        """Flush every enabled render pass in order, then reset the frame.

        Convention: ``flush_all(camera=...)`` is the single owner of
        ``Camera2D.start_frame()`` / ``Camera2D.end_frame()`` — each pass
        begins and ends the camera internally (see ``_render_pass``). Callers
        must never call ``camera.start_frame()`` / ``camera.end_frame()``
        themselves, otherwise the camera is applied twice per frame.

        Args:
            camera: Active camera for the ``world`` pass (``None`` renders
                in screen space without camera transforms).
        """
        # self._ensure_ubr()
        profile_start = time.perf_counter() if self.profile_enabled else 0.0
        world = self._render_passes.get("world")
        if world is not None:
            world.camera = camera
            world.viewport_scissor = camera.viewport if camera is not None else None
        self._is_rendering = True
        try:
            for render_pass in sorted(
                self._render_passes.values(), key=lambda item: item.order
            ):
                if render_pass.enabled:
                    self._render_pass(render_pass)
            if camera is not None:
                camera.draw_letterbox()
        finally:
            self._is_rendering = False
            if self.profile_enabled:
                self.frame_profile["render_total_ms"] = (
                    self.frame_profile.get("render_total_ms", 0.0)
                    + (time.perf_counter() - profile_start) * 1000.0
                )
                self.last_frame_profile = dict(self.frame_profile)

            # End Frame
            self._items.clear()
            self._frame_buffer.reset()
            self._next_submit_index = 0

    def flush(
        self, *, min_layer: int | None = None, max_layer: int | None = None
    ) -> None:
        """Flushes queued items and sprites within a layer range immediately.

        Renders a temporary pass covering ``min_layer``..``max_layer``,
        then removes the flushed items from the queue. Unlike
        :meth:`flush_all`, the frame is not reset.

        Args:
            min_layer: Minimum layer to flush (``None`` for no lower bound).
            max_layer: Maximum layer to flush (``None`` for no upper bound).
        """
        temp = RenderPass(
            name="__flush__", order=0, min_layer=min_layer, max_layer=max_layer
        )
        self._is_rendering = True
        try:
            self._render_pass(temp, pass_names=None)
            self._items = [
                item for item in self._items if not self._pass_accepts(temp, item)
            ]
        finally:
            self._is_rendering = False

    def _force_flush_sprites(self) -> None:
        """Force-flush full FrameBuffer mid-submit (capacity overflow)."""
        # self._ensure_ubr()
        n = self._frame_buffer.count
        if n <= 0:
            return
        indices = np.arange(n, dtype=np.int64)
        self._flush_sprite_indices(indices)
        self._frame_buffer.reset()
        if self.profile_enabled:
            self.frame_profile["force_flush_count"] = (
                self.frame_profile.get("force_flush_count", 0.0) + 1.0
            )

    def _render_pass(
        self, render_pass: RenderPass, pass_names: set[str] | None = None
    ) -> None:
        """Renders one pass: filters, sorts, then dispatches its items.

        Opens the pass render texture, camera, and viewport scissor as
        configured, dispatches sprite and non-sprite items interleaved
        (or via the sprite-only fast path), and restores GPU state in
        the ``finally`` block.
        """
        names = (
            {render_pass.name}
            if pass_names is None and render_pass.name != "__flush__"
            else pass_names
        )

        sort_start = time.perf_counter() if self.profile_enabled else 0.0
        items: list[RenderItem] = []

        items = [
            item
            for item in self._items
            if (names is None or item.pass_name in names)
            and self._pass_accepts(render_pass, item)
            and item.kind not in {RenderKind.SPRITE, RenderKind.SPRITE_BATCH}
        ]
        if items:
            items.sort(
                key=lambda item: (
                    render_pass.order,
                    item.layer,
                    item.sort_key,
                    item.state_id,
                    item.submit_index,
                )
            )

        sprite_indices = self._sprite_indices_for_pass(render_pass, names)
        if self.profile_enabled:
            self.frame_profile["render_sort_ms"] = (
                self.frame_profile.get("render_sort_ms", 0.0)
                + (time.perf_counter() - sort_start) * 1000.0
            )

        if not items and sprite_indices.size == 0:
            return

        flush_start = time.perf_counter() if self.profile_enabled else 0.0
        if render_pass.target is not None:
            self.canvas.begin_texture_mode(render_pass.target)
        camera_active = False
        viewport_active = False
        try:
            if render_pass.clear_color is not None:
                # TODO: Re-check clear background
                self.canvas.clear_background(render_pass.clear_color)
            if render_pass.camera is not None and not render_pass.screen_space:
                render_pass.camera.start_frame()
                camera_active = True
            if render_pass.viewport_scissor is not None:
                x, y, w, h = render_pass.viewport_scissor
                self.canvas.begin_scissor_mode(int(x), int(y), int(w), int(h))
                viewport_active = True

            if items:
                self._dispatch_merged(
                    items, sprite_indices, render_pass, viewport_active
                )
            elif sprite_indices.size:
                # Hot path (bunny / particle batch): no 8k Python tuples.
                self._dispatch_sprites_fast(
                    sprite_indices, render_pass, viewport_active
                )
        finally:
            if self.profile_enabled:
                self.frame_profile["render_flush_ms"] = (
                    self.frame_profile.get("render_flush_ms", 0.0)
                    + (time.perf_counter() - flush_start) * 1000.0
                )
            self._reset_state(self._last_active_state, viewport_active)
            if camera_active and render_pass.camera is not None:
                render_pass.camera.end_frame()
            if render_pass.target is not None:
                self.canvas.end_texture_mode()

    def _sprite_indices_for_pass(
        self, render_pass: RenderPass, names: set[str] | None
    ) -> np.ndarray:
        """Returns FrameBuffer sprite indices accepted by a pass.

        Args:
            render_pass: Pass whose pass-hash and layer bounds filter sprites.
            names: Set of pass names to match (``None`` matches all).

        Returns:
            Sorted array of matching sprite indices.
        """
        fb = self._frame_buffer
        n = fb.count
        if n <= 0:
            return np.empty(0, dtype=np.int64)
        if render_pass.name == "__flush__" or names is None:
            m = np.ones(n, dtype=np.bool_)
        else:
            hashes = [pass_name_hash(p) for p in names]
            m = np.isin(fb.pass_hash[:n], hashes)
        if render_pass.min_layer is not None:
            m &= fb.layer[:n] >= int(render_pass.min_layer)
        if render_pass.max_layer is not None:
            m &= fb.layer[:n] <= int(render_pass.max_layer)
        return np.flatnonzero(m).astype(np.int64, copy=False)

    def _dispatch_sprites_fast(
        self,
        sprite_indices: np.ndarray,
        render_pass: RenderPass,
        viewport_active: bool,
    ) -> None:
        """Sprite-only flush: numpy lexsort, no per-sprite Python tuples."""
        fb = self._frame_buffer
        n = int(sprite_indices.size)
        if n <= 0:
            return

        layers = fb.layer[sprite_indices]
        sort_keys = fb.sort_key[sprite_indices]
        state_ids = fb.state_id[sprite_indices]
        submit_idx = fb.submit_index[sprite_indices]
        # Primary key last in lexsort.
        order = np.lexsort((submit_idx, state_ids, sort_keys, layers))
        ordered = sprite_indices[order]
        o_layers = layers[order]
        o_states = state_ids[order]

        if n == 1:
            bounds = (0, 1)
            group_starts = (0,)
        else:
            changed = (o_layers[1:] != o_layers[:-1]) | (o_states[1:] != o_states[:-1])
            split = np.flatnonzero(changed) + 1
            group_starts = np.concatenate(([0], split))
            bounds = None

        active_state = 0
        viewport = render_pass.viewport_scissor
        if bounds is not None:
            starts_ends = [(0, 1)]
        else:
            starts = group_starts
            ends = np.concatenate((group_starts[1:], [n]))
            starts_ends = zip(starts.tolist(), ends.tolist(), strict=True)

        for start, end in starts_ends:
            state_id = int(o_states[start])
            active_state = self._apply_state(
                active_state, state_id, viewport, viewport_active
            )
            self._flush_sprite_indices(ordered[start:end])
            if self.profile_enabled:
                self.frame_profile["draw_call_count"] = (
                    self.frame_profile.get("draw_call_count", 0.0) + 1.0
                )
                self.frame_profile["ubr_submit_count"] = (
                    self.frame_profile.get("ubr_submit_count", 0.0) + 1.0
                )
        self._last_active_state = active_state

    def _dispatch_merged(
        self,
        items: list[RenderItem],
        sprite_indices: np.ndarray,
        render_pass: RenderPass,
        viewport_active: bool,
    ) -> None:
        """Mixed sprite + primitive/text/custom — keep painter interleave."""
        fb = self._frame_buffer
        records: list[tuple[int, float, int, int, str, Any]] = []
        for idx in sprite_indices:
            i = int(idx)
            records.append((
                int(fb.layer[i]),
                float(fb.sort_key[i]),
                int(fb.state_id[i]),
                int(fb.submit_index[i]),
                "s",
                i,
            ))
        for item in items:
            records.append((
                item.layer,
                item.sort_key,
                item.state_id,
                item.submit_index,
                "i",
                item,
            ))
        records.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

        active_state = 0
        k = 0
        while k < len(records):
            kind = records[k][4]
            state_id = records[k][2]
            active_state = self._apply_state(
                active_state,
                state_id,
                render_pass.viewport_scissor,
                viewport_active,
            )
            if kind == "s":
                layer0 = records[k][0]
                j = k + 1
                while (
                    j < len(records)
                    and records[j][4] == "s"
                    and records[j][2] == state_id
                    and records[j][0] == layer0
                ):
                    j += 1
                batch_idx = np.fromiter(
                    (records[t][5] for t in range(k, j)),
                    dtype=np.int64,
                    count=j - k,
                )
                self._flush_sprite_indices(batch_idx)
                if self.profile_enabled:
                    self.frame_profile["draw_call_count"] = (
                        self.frame_profile.get("draw_call_count", 0.0) + 1.0
                    )
                    self.frame_profile["ubr_submit_count"] = (
                        self.frame_profile.get("ubr_submit_count", 0.0) + 1.0
                    )
                k = j
            else:
                self._draw_item(records[k][5])
                if self.profile_enabled:
                    self.frame_profile["draw_call_count"] = (
                        self.frame_profile.get("draw_call_count", 0.0) + 1.0
                    )
                k += 1
        self._last_active_state = active_state

    def _flush_sprite_indices(self, indices: np.ndarray) -> None:
        """Sorts by texture/depth + one ``ubr.submit_frame`` call."""
        if indices.size == 0:
            return

        fb = self._frame_buffer
        n_idx = int(indices.size)

        # Zero-copy hot path: full opaque buffer in submit order, one texture.
        if (
            n_idx == fb.count
            and n_idx > 0
            and int(indices[0]) == 0
            and int(indices[n_idx - 1]) == n_idx - 1
            and (n_idx <= 2 or int(indices[1]) == 1)
            and not bool(np.any(fb.depth_sorted[:n_idx]))
            and (n_idx == 1 or not bool(np.any(fb.tex_id[:n_idx] != fb.tex_id[0])))
        ):
            n = n_idx
            fb._g_run_starts[0] = 0
            fb._g_run_counts[0] = n
            fb._g_run_tex[0] = np.uint32(fb.tex_id[0])
            self._ubr.submit_frame(
                pos_xy=fb.pos_xy[:n],
                size_wh=fb.size_wh[:n],
                origin_xy=fb.origin_xy[:n],
                rotation_deg=fb.rotation_deg[:n],
                rgba=fb.rgba[:n],
                uv_rect=fb.uv_rect[:n],
                run_starts=fb._g_run_starts[:1],
                run_counts=fb._g_run_counts[:1],
                run_tex_ids=fb._g_run_tex[:1],
                n_sprites=n,
                n_runs=1,
            )
            if self.profile_enabled:
                # sprite_count is already counted at submit time; here we
                # only track texture runs (run count is known at flush).
                self.frame_profile["texture_run_count"] = (
                    self.frame_profile.get("texture_run_count", 0.0) + 1.0
                )
            return

        depth_mask = fb.depth_sorted[indices]
        if not np.any(depth_mask):
            order, _ = build_runs(fb.tex_id[indices], n_idx)
            ordered = indices[order]
        elif np.all(depth_mask):
            order, _ = build_depth_runs(fb.tex_id[indices], fb.sort_key[indices], n_idx)
            ordered = indices[order]
        else:
            opaque_idx = indices[~depth_mask]
            depth_idx = indices[depth_mask]
            chunks: list[np.ndarray] = []
            if opaque_idx.size:
                order, _ = build_runs(fb.tex_id[opaque_idx], int(opaque_idx.size))
                chunks.append(opaque_idx[order])
            if depth_idx.size:
                order, _ = build_depth_runs(
                    fb.tex_id[depth_idx],
                    fb.sort_key[depth_idx],
                    int(depth_idx.size),
                )
                chunks.append(depth_idx[order])
            ordered = np.concatenate(chunks)

        n = int(ordered.size)
        # Gather into preallocated scratch (one alloc set per FrameBuffer life).
        pos = fb._g_pos[:n]
        size = fb._g_size[:n]
        origin = fb._g_origin[:n]
        rot = fb._g_rot[:n]
        rgba = fb._g_rgba[:n]
        uv = fb._g_uv[:n]
        tex = fb._g_tex[:n]
        np.take(fb.pos_xy, ordered, axis=0, out=pos)
        np.take(fb.size_wh, ordered, axis=0, out=size)
        np.take(fb.origin_xy, ordered, axis=0, out=origin)
        np.take(fb.rotation_deg, ordered, axis=0, out=rot)
        np.take(fb.rgba, ordered, axis=0, out=rgba)
        np.take(fb.uv_rect, ordered, axis=0, out=uv)
        np.take(fb.tex_id, ordered, axis=0, out=tex)

        runs = runs_from_ordered(tex, n)
        n_runs = int(runs.shape[0])
        if n_runs > 0:
            run_starts = fb._g_run_starts[:n_runs]
            run_counts = fb._g_run_counts[:n_runs]
            run_tex = fb._g_run_tex[:n_runs]
            run_starts[:] = runs[:, 0]
            run_counts[:] = runs[:, 1]
            run_tex[:] = runs[:, 2]
        else:
            run_starts = fb._g_run_starts[:0]
            run_counts = fb._g_run_counts[:0]
            run_tex = fb._g_run_tex[:0]

        self._ubr.submit_frame(
            pos_xy=pos,
            size_wh=size,
            origin_xy=origin,
            rotation_deg=rot,
            rgba=rgba,
            uv_rect=uv,
            run_starts=run_starts,
            run_counts=run_counts,
            run_tex_ids=run_tex,
            n_sprites=n,
            n_runs=n_runs,
        )
        if self.profile_enabled:
            # sprite_count is already counted at submit time; here we
            # only track texture runs (run count is known at flush).
            self.frame_profile["texture_run_count"] = self.frame_profile.get(
                "texture_run_count", 0.0
            ) + float(n_runs)

    @staticmethod
    def _pass_accepts(render_pass: RenderPass, item: RenderItem) -> bool:
        """Returns whether an item's layer falls within a pass's bounds."""
        return (
            render_pass.min_layer is None or item.layer >= render_pass.min_layer
        ) and (render_pass.max_layer is None or item.layer <= render_pass.max_layer)

    def _apply_state(
        self,
        active_state_id: int,
        next_state_id: int,
        viewport: RectType | None,
        viewport_active: bool,
    ) -> int:
        """Transitions GPU state, returning the new active state id.

        Resets the previous state, then enables the next state's
        scissor (clipped to the viewport), blend mode, and shader.

        Args:
            active_state_id: Currently active state id.
            next_state_id: State id to transition to.
            viewport: Active viewport scissor rect, if any.
            viewport_active: Whether a viewport scissor is currently set.

        Returns:
            The new active state id.
        """
        if active_state_id == next_state_id:
            return active_state_id
        self._reset_state(active_state_id, viewport_active)
        state = self.state_cache.get(next_state_id)
        if state.scissor is not None:
            sx, sy, sw, sh = (
                _intersect_rects(viewport, state.scissor)
                if viewport is not None
                else state.scissor
            )
            self.canvas.begin_scissor_mode(int(sx), int(sy), int(sw), int(sh))
        elif viewport_active and viewport is not None:
            vx, vy, vw, vh = viewport
            self.canvas.begin_scissor_mode(int(vx), int(vy), int(vw), int(vh))
        if state.blend_mode != BlendMode.ALPHA:
            self.canvas.begin_blend_mode(int(state.blend_mode))
        if state.shader is not None:
            self.canvas.begin_shader_mode(state.shader)
        return next_state_id

    def _reset_state(self, state_id: int, viewport_active: bool) -> None:
        """Ends the GPU modes enabled by a state (shader/blend/scissor).

        Args:
            state_id: State id whose modes should be ended.
            viewport_active: Whether a viewport scissor must also be ended.
        """
        state = (
            self.state_cache.get(state_id) if state_id != 0 else DEFAULT_RENDER_STATE
        )
        if state.shader is not None:
            self.canvas.end_shader_mode()
        if state.blend_mode != BlendMode.ALPHA:
            self.canvas.end_blend_mode()
        if state.scissor is not None or viewport_active:
            self.canvas.end_scissor_mode()

    def _draw_item(self, item: RenderItem) -> None:
        """Draws one queued non-sprite item (primitive/text/custom)."""
        payload = item.payload
        if isinstance(payload, PrimitiveItem):
            draw_primitive(self.canvas, payload)
        elif isinstance(payload, TextItem):
            self.canvas.draw_text(**payload.payload)
        elif isinstance(payload, CustomItem):
            payload.draw_func(self.canvas)

    @staticmethod
    def _extract_state(payload: dict[str, Any]) -> dict[str, Any]:
        """Internal: separates state keys from a primitive item payload.

        Takes the keys ``z``, ``layer``, ``pass_name``, ``scissor``,
        ``blend_mode``, ``shader``, ``state_id``, ``y_sort``,
        ``y_sort_origin``, ``screen_space`` out of ``payload`` and
        returns them as a separate dict. The keys are removed from
        ``payload`` (in-place mutation).

        Args:
            payload: Primitive payload dictionary; will be mutated.

        Returns:
            dict[str, Any]: Dictionary containing only the state keys
            found in ``payload``.
        """
        state: dict[str, Any] = {}
        for key in (
            "z",
            "layer",
            "pass_name",
            "scissor",
            "blend_mode",
            "shader",
            "state_id",
            "y_sort",
            "y_sort_origin",
            "screen_space",
        ):
            if key in payload:
                state[key] = payload.pop(key)
        return state


def _intersect_rects(a: RectType | None, b: RectType) -> RectType:
    """Intersects two rects, returning ``b`` when ``a`` is ``None``."""
    return aabb_intersection(a, b) if a is not None else b
