"""raylib 2D drawing canvas (primitives, text, textures, render textures).

Module-level ``ICanvas2D`` implementation for the raylib backend: immediate-mode
primitives, GPU state modes (scissor/blend/shader/texture), stencil mask entry
points, streaming-texture helpers, batched draws, and primitive baking to
``Texture2D``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import TypeIs, cast

import pyray as pr
import raylib as rl
from raylib import ffi as _ffi

from plyunit._enums import TextureFilter
from plyunit.core.types import ColorType, NPatchInfo, RectType, Vec2Type

from ..handler import Font, Image, RenderTexture, Shader, Texture2D
from .gl_ffi import ctype_of
from .stencil import (
    begin_stencil_mask,
    end_stencil_mask,
    end_stencil_mask_inverse,
    end_stencil_mode,
    init_stencil,
)
from .streaming_texture import (
    create_streaming_texture,
    destroy_streaming_texture,
    init_streaming,
)

__all__ = (
    "begin_blend_mode",
    "begin_scissor_mode",
    "begin_shader_mode",
    "begin_stencil_mask",
    "begin_texture_mode",
    "color",
    "create_circle",
    "create_circles",
    "create_line",
    "create_lines",
    "create_poly",
    "create_polys",
    "create_rect",
    "create_rects",
    "create_streaming_texture",
    "create_triangle",
    "create_triangles",
    "destroy_streaming_texture",
    "draw_circle",
    "draw_circle_batch",
    "draw_ellipse",
    "draw_line",
    "draw_line_batch",
    "draw_pixel",
    "draw_poly",
    "draw_rectangle",
    "draw_rectangle_batch",
    "draw_ring",
    "draw_text",
    "draw_texture",
    "draw_texture_region",
    "draw_triangle",
    "draw_triangle_batch",
    "end_blend_mode",
    "end_scissor_mode",
    "end_shader_mode",
    "end_stencil_mask",
    "end_stencil_mask_inverse",
    "end_stencil_mode",
    "end_texture_mode",
    "gen_mipmaps",
    "init_stencil",
    "init_streaming",
    "load_render_texture",
    "rgb",
    "rgba",
    "set_texture_filter",
    "to_color",
    "to_rect",
    "to_vec2",
    "unload_render_texture",
)


type Vec2Like = pr.Vector2 | Vec2Type
type RectLike = pr.Rectangle | RectType
type ColorLike = pr.Color | ColorType

_cache_color: dict[tuple[int, int, int, int], pr.Color] = {}
_COLOR_CACHE_LIMIT = 1028

# pyray Vector2/Color/Rectangle are cffi constructor *functions*, not types.
# Cache ctype identities for O(1) native checks (tuple/list short-circuit first).
_VEC2_T = _ffi.typeof("struct Vector2")
_COLOR_T = _ffi.typeof("struct Color")
_RECT_T = _ffi.typeof("struct Rectangle")


def is_vec2(value: object) -> TypeIs[pr.Vector2]:
    """Check whether the value is a native/duck-typed Vector2 (not a sequence)."""
    t = type(value)
    if t is tuple or t is list:
        return False
    try:
        return ctype_of(value) is _VEC2_T
    except TypeError:
        return (
            getattr(value, "x", None) is not None
            and getattr(value, "y", None) is not None
        )


def is_color(value: object) -> TypeIs[pr.Color]:
    """Check whether the value is a native/duck-typed Color (not a sequence)."""
    t = type(value)
    if t is tuple or t is list:
        return False
    try:
        return ctype_of(value) is _COLOR_T
    except TypeError:
        return (
            getattr(value, "r", None) is not None
            and getattr(value, "g", None) is not None
            and getattr(value, "b", None) is not None
            and getattr(value, "a", None) is not None
        )


def is_rect(value: object) -> TypeIs[pr.Rectangle]:
    """Check whether the value is a native/duck-typed Rectangle (not a sequence)."""
    t = type(value)
    if t is tuple or t is list:
        return False
    try:
        return ctype_of(value) is _RECT_T
    except TypeError:
        return (
            getattr(value, "x", None) is not None
            and getattr(value, "y", None) is not None
            and getattr(value, "width", None) is not None
            and getattr(value, "height", None) is not None
        )


def to_vec2(v: Vec2Like) -> pr.Vector2:
    """Ensure the value is a ``pr.Vector2`` (converting from tuple if needed)."""
    if is_vec2(v):
        return cast(pr.Vector2, v)

    # Duck-typing untuk sequence / tuple / list
    try:
        return pr.Vector2(float(v[0]), float(v[1]))
    except (TypeError, IndexError, ValueError) as exc:
        raise TypeError(
            f"Invalid Vector2 input: {v}. Expected pr.Vector2 or (x, y)"
        ) from exc


def to_rect(r: RectLike) -> pr.Rectangle:
    """Ensure the value is a ``pr.Rectangle`` (converting from tuple/list if needed)."""
    if is_rect(r):
        return cast(pr.Rectangle, r)

    # Duck-typing untuk sequence / tuple / list
    try:
        return pr.Rectangle(float(r[0]), float(r[1]), float(r[2]), float(r[3]))
    except (TypeError, IndexError, ValueError) as exc:
        raise TypeError(
            f"Invalid Rectangle input: {r}. "
            "Expected pr.Rectangle or (x, y, width, height)"
        ) from exc


def _color_key(c: ColorLike) -> tuple[int, int, int, int]:
    """Normalise a Color struct or (r, g, b, [a]) sequence to a hashable int tuple."""
    # Jika c adalah Struct pr.Color
    if is_color(c):
        return (int(c.r), int(c.g), int(c.b), int(c.a))

    # Jika c adalah Sequence (tuple/list) seperti pr.RED (230, 41, 55, 255)
    try:
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        a = int(c[3]) if len(c) > 3 else 255
        return (r, g, b, a)
    except (TypeError, IndexError, ValueError) as exc:
        raise TypeError(
            f"Color must be pr.Color or (r, g, b, [a]) sequence, got: {c}"
        ) from exc


def to_color(c: ColorLike | None = None, default: ColorLike = pr.BLACK) -> pr.Color:
    """Ensure the value is a ``pr.Color`` struct.

    Fallback to ``default`` (default: ``pr.BLACK``) if ``c`` is None or invalid.
    """
    target = default if c is None else c

    if is_color(target):
        return cast(pr.Color, target)

    try:
        key = _color_key(target)
    except TypeError:
        try:
            key = _color_key(default)
        except TypeError:
            key = (0, 0, 0, 255)

    cached = _cache_color.get(key)
    if cached is not None:
        return cached

    if len(_cache_color) > _COLOR_CACHE_LIMIT:
        _cache_color.clear()

    col = pr.Color(key[0], key[1], key[2], key[3])
    _cache_color[key] = col
    return col


def color(c: ColorLike) -> pr.Color:
    """Alias for :func:`to_color`."""
    return to_color(c)


def rgb(r: int, g: int, b: int) -> pr.Color:
    """Create a ``pr.Color`` from RGB (alpha 255)."""
    return to_color((r, g, b, 255))


def rgba(r: int, g: int, b: int, a: int) -> pr.Color:
    """Create a ``pr.Color`` from RGBA."""
    return to_color((r, g, b, a))


def _apply_transform(
    origin_val: Vec2Like | None, rotation: float, default_pivot: Vec2Like
) -> bool:
    """Push a matrix transform (origin + rotation); return True if pushed."""
    if rotation != 0.0 or origin_val is not None:
        pr.rl_push_matrix()
        pivot = to_vec2(origin_val if origin_val is not None else default_pivot)
        pr.rl_translatef(pivot.x, pivot.y, 0.0)
        pr.rl_rotatef(rotation, 0.0, 0.0, 1.0)
        pr.rl_translatef(-pivot.x, -pivot.y, 0.0)
        return True
    return False


def _xy(v: Vec2Like) -> Vec2Type:
    """Get (x, y) from a Vector2/cdata or a sequence without allocating a struct."""
    if is_vec2(v):
        return v.x, v.y
    return v[0], v[1]


def draw_pixel(*, pos: Vec2Like = (0, 0), color: ColorLike | None = None) -> None:
    """Wrap DrawPixel and DrawPixelV."""
    pr.draw_pixel_v(pos, to_color(color))


def draw_line(
    *,
    start: Vec2Like = (0, 0),
    end: Vec2Like = (0, 0),
    color: ColorLike | None = None,
    thickness: float = 1.0,
    bezier: bool = False,
    origin: Vec2Like | None = None,
    rotation: float = 0.0,
) -> None:
    """Wrap the DrawLine functions (thickness, bezier, rotation)."""
    col = to_color(color)
    start_v = to_vec2(start)
    end_v = to_vec2(end)
    if thickness == 1.0 and not bezier and origin is None and rotation == 0.0:
        pr.draw_line_v(start_v, end_v, col)
        return
    use_transform = False
    if rotation != 0.0 or origin is not None:
        use_transform = _apply_transform(origin, rotation, start_v)
    if bezier:
        pr.draw_line_bezier(start_v, end_v, thickness, col)
    else:
        pr.draw_line_ex(start_v, end_v, thickness, col)
    if use_transform:
        pr.rl_pop_matrix()


def draw_circle(
    *,
    center: Vec2Like = (0, 0),
    radius: float = 10.0,
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    gradient_outer: ColorLike | None = None,
    sector_angles: tuple[float, float] | None = None,
    segments: int = 36,
    origin: Vec2Type | None = None,
    rotation: float = 0.0,
) -> None:
    """Wrap the DrawCircle functions (border, sector, gradient, transform)."""
    center = to_vec2(center)
    color = to_color(color)
    if border_color is not None:
        border_color = to_color(border_color)
    if gradient_outer is not None:
        gradient_outer = to_color(gradient_outer)

    # Hot path: filled circle, no extras
    if (
        border_color is None
        and not outline_only
        and origin is None
        and rotation == 0.0
        and sector_angles is None
        and gradient_outer is None
    ):
        pr.draw_circle_v(center, radius, color)
        return

    use_transform = False
    if rotation != 0.0 or origin is not None:
        use_transform = _apply_transform(origin, rotation, center)

    if not outline_only:
        if sector_angles is not None:
            pr.draw_circle_sector(
                center, radius, sector_angles[0], sector_angles[1], segments, color
            )
        elif gradient_outer is not None:
            pr.draw_circle_gradient(
                int(center.x), int(center.y), radius, color, gradient_outer
            )
        else:
            pr.draw_circle_v(center, radius, color)

    if border_color is not None or outline_only:
        b_color = to_color(border_color, default=color)
        if thickness > 1.0:
            # Thick borders are drawn inward (consistent with
            # draw_rectangle/draw_triangle) using a ring.
            inner_radius = max(0.0, radius - thickness)
            start_angle, end_angle = (
                sector_angles if sector_angles is not None else (0.0, 360.0)
            )
            pr.draw_ring(
                to_vec2(center),
                inner_radius,
                radius,
                start_angle,
                end_angle,
                segments,
                b_color,
            )
        elif sector_angles is not None:
            pr.draw_circle_sector_lines(
                center, radius, sector_angles[0], sector_angles[1], segments, b_color
            )
        else:
            pr.draw_circle_lines_v(center, radius, b_color)

    if use_transform:
        pr.rl_pop_matrix()


def draw_ellipse(
    *,
    center: Vec2Like = (0, 0),
    radius_h: float = 10.0,
    radius_v: float = 10.0,
    color: ColorLike | None = None,
    outline_only: bool = False,
) -> None:
    """Wrap the DrawEllipse functions (filled or outline)."""
    cx, cy = _xy(center)
    col = to_color(color)
    if outline_only:
        pr.draw_ellipse_lines(int(cx), int(cy), radius_h, radius_v, col)
    else:
        pr.draw_ellipse(int(cx), int(cy), radius_h, radius_v, col)


def draw_ring(
    *,
    center: Vec2Like = (0, 0),
    inner_radius: float = 5.0,
    outer_radius: float = 10.0,
    start_angle: float = 0.0,
    end_angle: float = 360.0,
    segments: int = 36,
    color: ColorLike | None = None,
    outline_only: bool = False,
) -> None:
    """Wrap the DrawRing functions (filled or outline)."""
    center = to_vec2(center)
    col = to_color(color)
    if outline_only:
        pr.draw_ring_lines(
            center, inner_radius, outer_radius, start_angle, end_angle, segments, col
        )
    else:
        pr.draw_ring(
            center, inner_radius, outer_radius, start_angle, end_angle, segments, col
        )


def _draw_advanced_rect(
    rect: pr.Rectangle,
    color: ColorLike,
    outline: bool,
    thick: float,
    roundness: float,
    segments: int,
    tl: bool,
    tr: bool,
    bl: bool,
    br: bool,
) -> None:
    """Draw a rectangle honoring roundness, per-corner flags, outline, and thickness."""
    w = rect.width
    h = rect.height

    if roundness <= 0 or (not tl and not tr and not bl and not br):
        if outline:
            if thick > 1.0:
                pr.draw_rectangle_lines_ex(rect, thick, color)
            else:
                pr.draw_rectangle_lines(int(rect.x), int(rect.y), int(w), int(h), color)
        else:
            pr.draw_rectangle_rec(rect, color)
        return

    if tl and tr and bl and br:
        if outline:
            if roundness > 0:
                pr.draw_rectangle_rounded_lines_ex(
                    rect, roundness, segments, thick, color
                )
        else:
            pr.draw_rectangle_rounded(rect, roundness, segments, color)
        return

    radius = (min(w, h) / 2.0) * roundness

    if not outline:
        # Filled
        pr.draw_rectangle_rounded(rect, roundness, segments, color)
        if not tl:
            pr.draw_rectangle(int(rect.x), int(rect.y), int(radius), int(radius), color)
        if not tr:
            pr.draw_rectangle(
                int(rect.x + w - radius),
                int(rect.y),
                int(radius),
                int(radius),
                color,
            )
        if not bl:
            pr.draw_rectangle(
                int(rect.x),
                int(rect.y + h - radius),
                int(radius),
                int(radius),
                color,
            )
        if not br:
            pr.draw_rectangle(
                int(rect.x + w - radius),
                int(rect.y + h - radius),
                int(radius),
                int(radius),
                color,
            )
    else:
        # Outline manually drawn edge by edge, corner by corner
        # Top
        x1 = rect.x + (radius if tl else 0)
        x2 = rect.x + w - (radius if tr else 0)
        pr.draw_line_ex(
            (x1, rect.y + thick / 2.0), (x2, rect.y + thick / 2.0), thick, color
        )

        # Bottom
        x1 = rect.x + (radius if bl else 0)
        x2 = rect.x + w - (radius if br else 0)
        pr.draw_line_ex(
            (x1, rect.y + h - thick / 2.0),
            (x2, rect.y + h - thick / 2.0),
            thick,
            color,
        )

        # Left
        y1 = rect.y + (radius if tl else 0)
        y2 = rect.y + h - (radius if bl else 0)
        pr.draw_line_ex(
            (rect.x + thick / 2.0, y1), (rect.x + thick / 2.0, y2), thick, color
        )

        # Right
        y1 = rect.y + (radius if tr else 0)
        y2 = rect.y + h - (radius if br else 0)
        pr.draw_line_ex(
            (rect.x + w - thick / 2.0, y1),
            (rect.x + w - thick / 2.0, y2),
            thick,
            color,
        )

        # Corners
        inner_r = max(0.0, radius - thick)
        if tl:
            pr.draw_ring(
                (rect.x + radius, rect.y + radius),
                inner_r,
                radius,
                180,
                270,
                segments,
                color,
            )
        if tr:
            pr.draw_ring(
                (rect.x + w - radius, rect.y + radius),
                inner_r,
                radius,
                270,
                360,
                segments,
                color,
            )
        if bl:
            pr.draw_ring(
                (rect.x + radius, rect.y + h - radius),
                inner_r,
                radius,
                90,
                180,
                segments,
                color,
            )
        if br:
            pr.draw_ring(
                (rect.x + w - radius, rect.y + h - radius),
                inner_r,
                radius,
                0,
                90,
                segments,
                color,
            )


def draw_rectangle(
    *,
    rect: RectLike = (0, 0, 10, 10),
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    roundness: float = 0.0,
    segments: int = 10,
    origin: Vec2Like | None = None,
    rotation: float = 0.0,
    gradient_v: tuple[ColorLike, ColorLike] | None = None,
    gradient_h: tuple[ColorLike, ColorLike] | None = None,
    gradient_ex: tuple[ColorLike, ColorLike, ColorLike, ColorLike] | None = None,
    round_tl: bool = True,
    round_tr: bool = True,
    round_bl: bool = True,
    round_br: bool = True,
) -> None:
    """Wrap DrawRectangle (rotation, corners, gradients)."""
    rect = to_rect(rect)
    if color is not None:
        color = to_color(color)
    if border_color is not None:
        border_color = to_color(border_color)

    # Hot path: solid fill, no extras — pass as-is
    if (
        border_color is None
        and not outline_only
        and thickness == 1.0
        and roundness == 0.0
        and origin is None
        and rotation == 0.0
        and gradient_v is None
        and gradient_h is None
        and gradient_ex is None
        and round_tl
        and round_tr
        and round_bl
        and round_br
    ):
        pr.draw_rectangle_rec(rect, pr.BLACK if color is None else color)
        return

    if color is None and border_color is None:
        color = pr.BLACK

    fill_color = pr.BLACK if color is None else color
    use_transform = rotation != 0.0 or origin is not None

    if use_transform:
        r = to_rect(rect)
        pr.rl_push_matrix()
        pr.rl_translatef(r.x, r.y, 0.0)
        pr.rl_rotatef(rotation, 0.0, 0.0, 1.0)
        orig_v = to_vec2(origin if origin else (0, 0))
        pr.rl_translatef(-orig_v.x, -orig_v.y, 0.0)
        draw_rect: pr.Rectangle = pr.Rectangle(0, 0, r.width, r.height)
    else:
        need_fields = (
            roundness > 0
            or not (round_tl and round_tr and round_bl and round_br)
            or gradient_v is not None
            or gradient_h is not None
            or outline_only
            or border_color is not None
            or thickness != 1.0
        )
        draw_rect = to_rect(rect) if need_fields and not is_rect(rect) else rect

    if (
        color is not None or gradient_v or gradient_h or gradient_ex
    ) and not outline_only:
        if gradient_v:
            if is_rect(draw_rect):
                pr.draw_rectangle_gradient_v(
                    int(draw_rect.x),
                    int(draw_rect.y),
                    int(draw_rect.width),
                    int(draw_rect.height),
                    gradient_v[0],
                    gradient_v[1],
                )
            else:
                pr.draw_rectangle_gradient_v(
                    int(draw_rect[0]),  # type: ignore[index]
                    int(draw_rect[1]),  # type: ignore[index]
                    int(draw_rect[2]),  # type: ignore[index]
                    int(draw_rect[3]),  # type: ignore[index]
                    gradient_v[0],
                    gradient_v[1],
                )
        elif gradient_h:
            if is_rect(draw_rect):
                pr.draw_rectangle_gradient_h(
                    int(draw_rect.x),
                    int(draw_rect.y),
                    int(draw_rect.width),
                    int(draw_rect.height),
                    gradient_h[0],
                    gradient_h[1],
                )
            else:
                pr.draw_rectangle_gradient_h(
                    int(draw_rect[0]),  # type: ignore[index]
                    int(draw_rect[1]),  # type: ignore[index]
                    int(draw_rect[2]),  # type: ignore[index]
                    int(draw_rect[3]),  # type: ignore[index]
                    gradient_h[0],
                    gradient_h[1],
                )
        elif gradient_ex:
            pr.draw_rectangle_gradient_ex(
                draw_rect,
                gradient_ex[0],
                gradient_ex[1],
                gradient_ex[2],
                gradient_ex[3],
            )
        elif (
            roundness <= 0
            and round_tl
            and round_tr
            and round_bl
            and round_br
            and border_color is None
        ):
            pr.draw_rectangle_rec(draw_rect, fill_color)
        else:
            if not is_rect(draw_rect):
                draw_rect = to_rect(draw_rect)
            _draw_advanced_rect(
                draw_rect,
                fill_color,
                False,
                thickness,
                roundness,
                segments,
                round_tl,
                round_tr,
                round_bl,
                round_br,
            )

    if border_color is not None or outline_only:
        b_color = (
            border_color
            if border_color is not None
            else color
            if color is not None
            else pr.BLACK
        )
        if not is_rect(draw_rect):
            draw_rect = to_rect(draw_rect)
        _draw_advanced_rect(
            draw_rect,
            b_color,
            True,
            thickness,
            roundness,
            segments,
            round_tl,
            round_tr,
            round_bl,
            round_br,
        )

    if use_transform:
        pr.rl_pop_matrix()


def _draw_triangle_gradient(
    v1: pr.Vector2,
    v2: pr.Vector2,
    v3: pr.Vector2,
    c1: pr.Color,
    c2: pr.Color,
    c3: pr.Color,
) -> None:
    """Approx per-vertex gradient as three half-color sub-triangles (no rlgl)."""
    cx = (v1.x + v2.x + v3.x) / 3.0
    cy = (v1.y + v2.y + v3.y) / 3.0
    mid = pr.Vector2(cx, cy)

    def _avg(a: pr.Color, b: pr.Color) -> pr.Color:
        return pr.Color(
            (int(a.r) + int(b.r)) // 2,
            (int(a.g) + int(b.g)) // 2,
            (int(a.b) + int(b.b)) // 2,
            (int(a.a) + int(b.a)) // 2,
        )

    c12 = _avg(c1, c2)
    c23 = _avg(c2, c3)
    c31 = _avg(c3, c1)
    pr.draw_triangle(v1, v2, mid, c12)
    pr.draw_triangle(v2, v3, mid, c23)
    pr.draw_triangle(v3, v1, mid, c31)


def draw_triangle(
    *,
    v1: Vec2Like = (0, 0),
    v2: Vec2Like = (0, 0),
    v3: Vec2Like = (0, 0),
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    origin: Vec2Type | None = None,
    rotation: float = 0.0,
    gradient: tuple[ColorLike, ColorLike, ColorLike] | None = None,
) -> None:
    """Wrap DrawTriangle and DrawTriangleLines."""
    v1 = to_vec2(v1)
    v2 = to_vec2(v2)
    v3 = to_vec2(v3)
    if color is not None:
        color = to_color(color)
    if border_color is not None:
        border_color = to_color(border_color)

    if (
        border_color is None
        and not outline_only
        and gradient is None
        and origin is None
        and rotation == 0.0
    ):
        pr.draw_triangle(v1, v2, v3, pr.BLACK if color is None else color)
        return

    if color is None and border_color is None and gradient is None:
        color = pr.BLACK

    use_transform = False
    if rotation != 0.0 or origin is not None:
        centroid = pr.Vector2((v1.x + v2.x + v3.x) / 3.0, (v1.y + v2.y + v3.y) / 3.0)
        use_transform = _apply_transform(origin, rotation, centroid)

    if (color is not None or gradient is not None) and not outline_only:
        if gradient is not None:
            c1 = to_color(gradient[0])
            c2 = to_color(gradient[1])
            c3 = to_color(gradient[2])
            _draw_triangle_gradient(v1, v2, v3, c1, c2, c3)
        else:
            pr.draw_triangle(v1, v2, v3, color if color is not None else pr.BLACK)

    if border_color is not None or outline_only:
        b_color = (
            border_color
            if border_color is not None
            else color
            if color is not None
            else pr.BLACK
        )
        if thickness > 1.0:
            pr.draw_line_ex(v1, v2, thickness, b_color)
            pr.draw_line_ex(v2, v3, thickness, b_color)
            pr.draw_line_ex(v3, v1, thickness, b_color)
            pr.draw_circle_v(v1, thickness / 2.0, b_color)
            pr.draw_circle_v(v2, thickness / 2.0, b_color)
            pr.draw_circle_v(v3, thickness / 2.0, b_color)
        else:
            pr.draw_triangle_lines(v1, v2, v3, b_color)

    if use_transform:
        pr.rl_pop_matrix()


def draw_poly(
    *,
    center: Vec2Like = (0, 0),
    sides: int = 3,
    radius: float = 10.0,
    rotation: float = 0.0,
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    origin: Vec2Type | None = None,
) -> None:
    """Wrap the DrawPoly functions (fill, outline, thickness)."""
    center = to_vec2(center)
    if color is not None:
        color = to_color(color)
    if border_color is not None:
        border_color = to_color(border_color)

    if color is None and border_color is None:
        color = pr.BLACK

    use_transform = False
    if origin is not None:
        use_transform = _apply_transform(origin, 0.0, center)

    if color is not None and not outline_only:
        pr.draw_poly(center, sides, radius, rotation, color)

    if border_color is not None or outline_only:
        b_color = (
            border_color
            if border_color is not None
            else color
            if color is not None
            else pr.BLACK
        )
        if thickness > 1.0:
            pr.draw_poly_lines_ex(center, sides, radius, rotation, thickness, b_color)
        else:
            pr.draw_poly_lines(center, sides, radius, rotation, b_color)

    if use_transform:
        pr.rl_pop_matrix()


def _rect_values(rect: RectLike) -> RectType:
    """Read signed pixel bounds from a tuple or backend rectangle."""
    if is_rect(rect):
        return rect.x, rect.y, rect.width, rect.height
    return rect[0], rect[1], rect[2], rect[3]


def draw_texture(
    *,
    texture: Texture2D | None = None,
    pos: Vec2Like = (0, 0),
    tint: ColorLike | None = None,
    rotation: float = 0.0,
    scale: float = 1.0,
    source: RectLike | None = None,
    dest: RectLike | None = None,
    origin: Vec2Like = (0, 0),
    npatch_info: NPatchInfo | None = None,
) -> None:
    """Wrap the DrawTexture functions (region, rotation, scale, n-patch)."""
    if texture is None:
        return

    raw = texture.raw_texture
    col = pr.WHITE if tint is None else to_color(tint)
    px, py = _xy(pos)

    if npatch_info is not None:
        area = dest if dest is not None else (px, py, texture.width, texture.height)
        layouts = {
            "nine_patch": rl.NPATCH_NINE_PATCH,
            "three_patch_vertical": rl.NPATCH_THREE_PATCH_VERTICAL,
            "three_patch_horizontal": rl.NPATCH_THREE_PATCH_HORIZONTAL,
        }
        patch = pr.NPatchInfo(
            to_rect(npatch_info.source),
            npatch_info.left,
            npatch_info.top,
            npatch_info.right,
            npatch_info.bottom,
            layouts[npatch_info.layout],
        )
        pr.draw_texture_n_patch(
            raw, patch, to_rect(area), to_vec2(origin), rotation, col
        )
        return

    full_source = (0.0, 0.0, float(texture.width), float(texture.height))
    if source is None and (
        dest is not None or texture.source_rect != full_source or _xy(origin) != (0, 0)
    ):
        source = texture.source_rect

    if source is not None:
        sx, sy, sw, sh = _rect_values(source)
        # Signed source sizes encode UV direction, not destination dimensions.
        if sw < 0:
            sx += sw
        if sh < 0:
            sy += sh
        target = (
            dest if dest is not None else (px, py, abs(sw) * scale, abs(sh) * scale)
        )
        pr.draw_texture_pro(
            raw,
            to_rect((sx, sy, sw, sh)),
            to_rect(target),
            to_vec2(origin),
            rotation,
            col,
        )
        return

    if rotation != 0.0 or scale != 1.0:
        pr.draw_texture_ex(raw, to_vec2(pos), rotation, scale, col)
    else:
        pr.draw_texture_v(raw, to_vec2(pos), col)


def begin_scissor_mode(x: int, y: int, width: int, height: int) -> None:
    """Begin scissor clipping in screen coordinates (with bounds clamping)."""
    ww = pr.get_screen_width()
    wh = pr.get_screen_height()

    # Clamp bounds
    cx = max(0, x)
    cy = max(0, y)
    cw = min(x + width, ww) - cx
    ch = min(y + height, wh) - cy

    if cw > 0 and ch > 0:
        pr.begin_scissor_mode(cx, cy, cw, ch)
    else:
        # If fully off-screen or empty, set to 0
        pr.begin_scissor_mode(0, 0, 0, 0)


def end_scissor_mode() -> None:
    """End scissor clipping."""
    pr.end_scissor_mode()


def begin_blend_mode(mode: int) -> None:
    """Begin blend mode. Use the BlendMode enum."""
    pr.begin_blend_mode(mode)


def end_blend_mode() -> None:
    """End blend mode."""
    pr.end_blend_mode()


def begin_shader_mode(shader: Shader) -> None:
    """Begin drawing with a live concrete shader handle.

    Raises:
        ValueError: If the shader has been released.
    """
    raw = shader.raw_shader
    if not shader._valid or raw is None:
        raise ValueError("shader handle has been released")
    pr.begin_shader_mode(raw)


def end_shader_mode() -> None:
    """End shader mode."""
    pr.end_shader_mode()


def begin_texture_mode(target: RenderTexture) -> None:
    """Begin drawing to a render texture."""
    pr.begin_texture_mode(target.raw_render_texture)


def end_texture_mode() -> None:
    """End drawing to a render texture."""
    pr.end_texture_mode()


def load_render_texture(width: int, height: int) -> RenderTexture:
    """Load an empty render texture sized ``(width, height)``."""
    return RenderTexture(pr.load_render_texture(width, height))


def unload_render_texture(target: RenderTexture) -> None:
    """Remove the render texture from the GPU."""
    pr.unload_render_texture(target.raw_render_texture)


def draw_texture_region(
    texture: Texture2D,
    source: RectType,
    dest: RectType,
) -> None:
    """Draw the ``source`` region of ``texture`` to ``dest`` (no rotation)."""
    sx, sy, sw, sh = source
    dx, dy, dw, dh = dest
    pr.draw_texture_pro(
        texture.raw_texture,
        pr.Rectangle(sx, sy, sw, sh),
        pr.Rectangle(dx, dy, dw, dh),
        pr.Vector2(0, 0),
        0.0,
        pr.WHITE,
    )


def _raw_texture_of(target: RenderTexture | Texture2D) -> pr.Texture:
    """Return the raw raylib texture of a texture or render-texture handle."""
    if isinstance(target, RenderTexture):
        return target.raw_render_texture.texture
    return target.raw_texture


def gen_mipmaps(target: RenderTexture | Texture2D) -> None:
    """Generate mipmaps for the ``target`` texture."""
    pr.gen_texture_mipmaps(_raw_texture_of(target))


def set_texture_filter(
    target: RenderTexture | Texture2D,
    filter_mode: TextureFilter = TextureFilter.TRILINEAR,
) -> None:
    """Apply a portable sampling mode to a backend-owned texture.

    Args:
        target: Texture or render target whose sampling state changes.
        filter_mode: Nearest, linear, or trilinear filtering.

    Raises:
        ValueError: If the mode is not a supported ``TextureFilter``.
    """
    if not isinstance(filter_mode, TextureFilter):
        raise ValueError("filter_mode must be a TextureFilter")
    filters = {
        TextureFilter.NEAREST: rl.TEXTURE_FILTER_POINT,
        TextureFilter.LINEAR: rl.TEXTURE_FILTER_BILINEAR,
        TextureFilter.TRILINEAR: rl.TEXTURE_FILTER_TRILINEAR,
    }
    pr.set_texture_filter(_raw_texture_of(target), filters[filter_mode])


def draw_text(
    *,
    text: str = "",
    pos: Vec2Like = (0, 0),
    font_size: float = 20,
    color: ColorLike | None = None,
    font: Font | None = None,
    spacing: float | None = None,
    origin: Vec2Type | None = None,
    rotation: float = 0.0,
    codepoint: int | None = None,
    codepoints: Sequence[int] | None = None,
) -> None:
    """Wrap the DrawText functions (font, spacing, rotation, codepoints)."""
    col = pr.BLACK if color is None else to_color(color)
    fnt = pr.get_font_default() if font is None else font._resource()
    pos = to_vec2(pos)

    if codepoint is not None and fnt:
        pr.draw_text_codepoint(fnt, codepoint, pos, font_size, col)
        return

    if codepoints is not None and fnt:
        sp = 1.0 if spacing is None else spacing
        pr.draw_text_codepoints(
            fnt, codepoints, len(codepoints), pos, font_size, sp, col
        )
        return

    sp = (font_size / 10.0) if spacing is None else spacing
    if origin is not None or rotation != 0.0:
        pr.draw_text_pro(
            fnt,
            text,
            pos,
            to_vec2(origin if origin is not None else (0, 0)),
            rotation,
            font_size,
            sp,
            col,
        )
    else:
        pr.draw_text_ex(fnt, text, pos, font_size, sp, col)


# ------------------------------------------------------------------
# Conversion Helpers
# ------------------------------------------------------------------


def _batch_len(*seqs: object) -> int:
    """Parallel length of batch sequences; 0 if any is empty."""
    n: int | None = None
    for s in seqs:
        if s is None:
            return 0
        try:
            length = len(s)  # type: ignore[arg-type]
        except TypeError:
            return 0
        if length <= 0:
            return 0
        n = length if n is None else min(n, length)
    return 0 if n is None else n


def draw_rectangle_batch(
    *,
    rects: Sequence[RectLike] | None = None,
    colors: Sequence[ColorLike] | None = None,
) -> None:
    """Batch draw many rectangles; tuples/natives are passed as-is to pyray."""
    count = _batch_len(rects, colors)
    if count <= 0:
        return
    assert rects is not None and colors is not None
    draw_fn = pr.draw_rectangle_rec
    for i in range(count):
        draw_fn(rects[i], colors[i])


def draw_circle_batch(
    *,
    centers: Sequence[Vec2Type] | None = None,
    radii: Sequence[float] | None = None,
    colors: Sequence[ColorLike] | None = None,
) -> None:
    """Batch draw many circles; tuples/natives are passed as-is to pyray."""
    count = _batch_len(centers, radii, colors)
    if count <= 0:
        return
    assert centers is not None and radii is not None and colors is not None
    draw_fn = pr.draw_circle_v
    for i in range(count):
        draw_fn(centers[i], float(radii[i]), colors[i])


def draw_line_batch(
    *,
    starts: Sequence[Vec2Type] | None = None,
    ends: Sequence[Vec2Type] | None = None,
    colors: Sequence[ColorLike] | None = None,
) -> None:
    """Batch draw many lines; tuples/natives are passed as-is to pyray."""
    count = _batch_len(starts, ends, colors)
    if count <= 0:
        return
    assert starts is not None and ends is not None and colors is not None
    draw_fn = pr.draw_line_v
    for i in range(count):
        draw_fn(starts[i], ends[i], colors[i])


def draw_triangle_batch(
    *,
    v1s: Sequence[Vec2Type] | None = None,
    v2s: Sequence[Vec2Type] | None = None,
    v3s: Sequence[Vec2Type] | None = None,
    colors: Sequence[ColorLike] | None = None,
) -> None:
    """Batch draw many triangles; tuples/natives are passed as-is to pyray."""
    count = _batch_len(v1s, v2s, v3s, colors)
    if count <= 0:
        return
    assert (
        v1s is not None and v2s is not None and v3s is not None and colors is not None
    )
    draw_fn = pr.draw_triangle
    for i in range(count):
        draw_fn(v1s[i], v2s[i], v3s[i], colors[i])


# ------------------------------------------------------------------
# Texture Creation (bake primitive -> Texture2D)
# ------------------------------------------------------------------


def _bake_to_texture(
    width: float, height: float, draw: Callable[[], None]
) -> Texture2D:
    """Bake drawing commands into a standalone GPU ``Texture2D``.

    The primitive is drawn once into a transparent render texture sized
    ``(width, height)``, read back to a CPU image, flipped vertically
    (render texture pixel rows are stored upside down — the OpenGL FBO
    convention), then re-uploaded as a standalone texture independent of
    the render texture's lifetime. The result is compatible with
    ``Assets.store_texture`` and ``build_texture_atlas``.

    Args:
        width: Texture width (rounded up, minimum 1).
        height: Texture height (rounded up, minimum 1).
        draw: Callback that draws the content to the active render target.

    Returns:
        The baked GPU texture.
    """
    w = max(1, math.ceil(float(width)))
    h = max(1, math.ceil(float(height)))
    target = load_render_texture(w, h)
    try:
        begin_texture_mode(target)
        try:
            pr.clear_background(pr.BLANK)
            draw()
        finally:
            end_texture_mode()
        image = Image(pr.load_image_from_texture(target.texture.raw_texture))
        try:
            pr.image_flip_vertical(image.raw_image)
            return Texture2D.from_raw(pr.load_texture_from_image(image.raw_image))
        finally:
            pr.unload_image(image.raw_image)
    finally:
        unload_render_texture(target)


def create_rect(
    *,
    rect: RectLike = (0, 0, 10, 10),
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    roundness: float = 0.0,
    segments: int = 10,
    gradient_v: tuple[ColorLike, ColorLike] | None = None,
    gradient_h: tuple[ColorLike, ColorLike] | None = None,
    gradient_ex: tuple[ColorLike, ColorLike, ColorLike, ColorLike] | None = None,
    round_tl: bool = True,
    round_tr: bool = True,
    round_bl: bool = True,
    round_br: bool = True,
) -> Texture2D:
    """Create a ``Texture2D`` from a single rectangle (drawn from origin 0,0).

    The ``(x, y)`` offset of ``rect`` is ignored — the texture is sized
    exactly ``(width, height)`` and the primitive is normalized to the
    top-left corner.
    """
    r = to_rect(rect)
    w = abs(float(r.width))
    h = abs(float(r.height))

    def _draw() -> None:
        draw_rectangle(
            rect=(0.0, 0.0, w, h),
            color=color,
            border_color=border_color,
            outline_only=outline_only,
            thickness=thickness,
            roundness=roundness,
            segments=segments,
            gradient_v=gradient_v,
            gradient_h=gradient_h,
            gradient_ex=gradient_ex,
            round_tl=round_tl,
            round_tr=round_tr,
            round_bl=round_bl,
            round_br=round_br,
        )

    return _bake_to_texture(w, h, _draw)


def create_rects(
    *,
    rects: Sequence[RectLike] | None = None,
    colors: Sequence[ColorLike] | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    roundness: float = 0.0,
    segments: int = 10,
    gradient_v: tuple[ColorLike, ColorLike] | None = None,
    gradient_h: tuple[ColorLike, ColorLike] | None = None,
    gradient_ex: tuple[ColorLike, ColorLike, ColorLike, ColorLike] | None = None,
    round_tl: bool = True,
    round_tr: bool = True,
    round_bl: bool = True,
    round_br: bool = True,
) -> list[Texture2D]:
    """Create many rectangle ``Texture2D``s at once (one per rect).

    Style (border, roundness, gradients, etc.) is shared across all rects;
    only ``rects`` and ``colors`` are per-item.
    """
    if not rects:
        return []
    count = len(rects)
    if colors is not None:
        count = min(count, len(colors))
    textures: list[Texture2D] = []
    for i in range(count):
        textures.append(
            create_rect(
                rect=rects[i],
                color=colors[i] if colors is not None else None,
                border_color=border_color,
                outline_only=outline_only,
                thickness=thickness,
                roundness=roundness,
                segments=segments,
                gradient_v=gradient_v,
                gradient_h=gradient_h,
                gradient_ex=gradient_ex,
                round_tl=round_tl,
                round_tr=round_tr,
                round_bl=round_bl,
                round_br=round_br,
            )
        )
    return textures


def create_circle(
    *,
    radius: float = 10.0,
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    gradient_outer: ColorLike | None = None,
    sector_angles: tuple[float, float] | None = None,
    segments: int = 36,
) -> Texture2D:
    """Create a ``Texture2D`` from a single circle (bounding box ``2r x 2r``)."""
    r = float(radius)

    def _draw() -> None:
        draw_circle(
            center=(r, r),
            radius=r,
            color=color,
            border_color=border_color,
            outline_only=outline_only,
            thickness=thickness,
            gradient_outer=gradient_outer,
            sector_angles=sector_angles,
            segments=segments,
        )

    return _bake_to_texture(2.0 * r, 2.0 * r, _draw)


def create_circles(
    *,
    radii: Sequence[float] | None = None,
    colors: Sequence[ColorLike] | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    gradient_outer: ColorLike | None = None,
    sector_angles: tuple[float, float] | None = None,
    segments: int = 36,
) -> list[Texture2D]:
    """Create many circle ``Texture2D``s at once (one per radius)."""
    if not radii:
        return []
    count = len(radii)
    if colors is not None:
        count = min(count, len(colors))
    textures: list[Texture2D] = []
    for i in range(count):
        textures.append(
            create_circle(
                radius=float(radii[i]),
                color=colors[i] if colors is not None else None,
                border_color=border_color,
                outline_only=outline_only,
                thickness=thickness,
                gradient_outer=gradient_outer,
                sector_angles=sector_angles,
                segments=segments,
            )
        )
    return textures


def create_line(
    *,
    start: Vec2Type = (0, 0),
    end: Vec2Type = (0, 0),
    color: ColorLike | None = None,
    thickness: float = 1.0,
    bezier: bool = False,
) -> Texture2D:
    """Create a ``Texture2D`` from a single line (bounding box + thickness/2 margin)."""
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    pad = max(0.0, float(thickness)) / 2.0
    x0 = min(sx, ex) - pad
    y0 = min(sy, ey) - pad
    x1 = max(sx, ex) + pad
    y1 = max(sy, ey) + pad

    def _draw() -> None:
        draw_line(
            start=(sx - x0, sy - y0),
            end=(ex - x0, ey - y0),
            color=color,
            thickness=thickness,
            bezier=bezier,
        )

    return _bake_to_texture(x1 - x0, y1 - y0, _draw)


def create_lines(
    *,
    starts: Sequence[Vec2Type] | None = None,
    ends: Sequence[Vec2Type] | None = None,
    colors: Sequence[ColorLike] | None = None,
    thickness: float = 1.0,
    bezier: bool = False,
) -> list[Texture2D]:
    """Create many line ``Texture2D``s at once (one per point pair)."""
    if starts is None or ends is None:
        return []
    count = min(len(starts), len(ends))
    if count <= 0:
        return []
    if colors is not None:
        count = min(count, len(colors))
    textures: list[Texture2D] = []
    for i in range(count):
        textures.append(
            create_line(
                start=starts[i],
                end=ends[i],
                color=colors[i] if colors is not None else None,
                thickness=thickness,
                bezier=bezier,
            )
        )
    return textures


def create_poly(
    *,
    sides: int = 6,
    radius: float = 10.0,
    rotation: float = 0.0,
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
) -> Texture2D:
    """Create a ``Texture2D`` from a single regular polygon with the given radius."""
    radius_f = float(radius)
    pad = thickness / 2.0 if (border_color is not None or outline_only) else 0.0
    diameter = 2.0 * radius_f + 2.0 * pad

    def _draw() -> None:
        draw_poly(
            center=(radius_f + pad, radius_f + pad),
            sides=sides,
            radius=radius_f,
            rotation=rotation,
            color=color,
            border_color=border_color,
            outline_only=outline_only,
            thickness=thickness,
        )

    return _bake_to_texture(diameter, diameter, _draw)


def create_polys(
    *,
    sides: Sequence[int] | None = None,
    radii: Sequence[float] | None = None,
    rotations: Sequence[float] | None = None,
    colors: Sequence[ColorLike] | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
) -> list[Texture2D]:
    """Create many polygon ``Texture2D``s at once."""
    if sides is None or radii is None:
        return []
    count = min(len(sides), len(radii))
    if rotations is not None:
        count = min(count, len(rotations))
    if colors is not None:
        count = min(count, len(colors))
    if count <= 0:
        return []

    textures: list[Texture2D] = []
    for i in range(count):
        textures.append(
            create_poly(
                sides=sides[i],
                radius=radii[i],
                rotation=rotations[i] if rotations is not None else 0.0,
                color=colors[i] if colors is not None else None,
                border_color=border_color,
                outline_only=outline_only,
                thickness=thickness,
            )
        )
    return textures


def create_triangle(
    *,
    v1: Vec2Type = (0, 0),
    v2: Vec2Type = (0, 0),
    v3: Vec2Type = (0, 0),
    color: ColorLike | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    gradient: tuple[ColorLike, ColorLike, ColorLike] | None = None,
) -> Texture2D:
    """Create a ``Texture2D`` from a single triangle
    (bounding box of its three vertices)."""
    ax, ay = _xy(v1)
    bx, by = _xy(v2)
    cx, cy = _xy(v3)
    pad = thickness / 2.0 if (border_color is not None or outline_only) else 0.0
    x0 = min(ax, bx, cx) - pad
    y0 = min(ay, by, cy) - pad
    x1 = max(ax, bx, cx) + pad
    y1 = max(ay, by, cy) + pad

    def _draw() -> None:
        draw_triangle(
            v1=(ax - x0, ay - y0),
            v2=(bx - x0, by - y0),
            v3=(cx - x0, cy - y0),
            color=color,
            border_color=border_color,
            outline_only=outline_only,
            thickness=thickness,
            gradient=gradient,
        )

    return _bake_to_texture(x1 - x0, y1 - y0, _draw)


def create_triangles(
    *,
    v1s: Sequence[Vec2Type] | None = None,
    v2s: Sequence[Vec2Type] | None = None,
    v3s: Sequence[Vec2Type] | None = None,
    colors: Sequence[ColorLike] | None = None,
    border_color: ColorLike | None = None,
    outline_only: bool = False,
    thickness: float = 1.0,
    gradient: tuple[ColorLike, ColorLike, ColorLike] | None = None,
) -> list[Texture2D]:
    """Create many triangle ``Texture2D``s at once (one per vertex triple)."""
    if v1s is None or v2s is None or v3s is None:
        return []
    count = min(len(v1s), len(v2s), len(v3s))
    if count <= 0:
        return []
    if colors is not None:
        count = min(count, len(colors))
    textures: list[Texture2D] = []
    for i in range(count):
        textures.append(
            create_triangle(
                v1=v1s[i],
                v2=v2s[i],
                v3=v3s[i],
                color=colors[i] if colors is not None else None,
                border_color=border_color,
                outline_only=outline_only,
                thickness=thickness,
                gradient=gradient,
            )
        )
    return textures


def clear_background(color: ColorType) -> None:
    """Clear the current render target's background with the given color."""
    pr.clear_background(color)
