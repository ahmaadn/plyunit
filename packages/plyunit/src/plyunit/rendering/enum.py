"""Enumerations for the rendering pipeline: kinds, blend modes, and layers."""

from __future__ import annotations

from enum import Enum, IntEnum, auto

__all__ = [
    "BlendMode",
    "Layer",
    "PrimitiveKind",
    "RenderKind",
]


class RenderKind(Enum):
    """Kind of payload stored in a ``RenderItem``.

    Attributes:
        SPRITE: A single sprite.
        SPRITE_BATCH: Many sprites batched together.
        PRIMITIVE: Primitive shape (pixel, line, circle, etc.).
        TEXT: Text rendered through a font.
        CUSTOM: Custom draw call (Callable).
    """

    SPRITE = auto()
    SPRITE_BATCH = auto()
    PRIMITIVE = auto()
    TEXT = auto()
    CUSTOM = auto()


class PrimitiveKind(Enum):
    """Primitive variant recognized by ``draw_primitive``.

    Attributes:
        PIXEL: A single pixel.
        LINE: A single line.
        CIRCLE: A circle.
        ELLIPSE: An ellipse.
        RING: A ring (annulus).
        RECTANGLE: A single rectangle.
        TRIANGLE: A single triangle.
        POLY: A regular polygon.
        RECTANGLES: Batch of rectangles.
        CIRCLES: Batch of circles.
        LINES: Batch of lines.
        TRIANGLES: Batch of triangles.
    """

    PIXEL = auto()
    LINE = auto()
    CIRCLE = auto()
    ELLIPSE = auto()
    RING = auto()
    RECTANGLE = auto()
    TRIANGLE = auto()
    POLY = auto()
    RECTANGLES = auto()
    CIRCLES = auto()
    LINES = auto()
    TRIANGLES = auto()


class BlendMode(IntEnum):
    """Supported blend modes (values align with raylib constants).

    Attributes:
        ALPHA: Standard alpha blending.
        ADDITIVE: Addition (light/glow effects).
        MULTIPLIED: Multiplication (shadow/darken effects).
        ADD_COLORS: Pure color addition.
        SUBTRACT_COLORS: Color subtraction.
        ALPHA_PREMULTIPLY: Premultiplied alpha.
        CUSTOM: Custom blend mode (configured via raylib).
        CUSTOM_SEPARATE: Custom blend mode with separate RGB/alpha parameters.
    """

    ALPHA = 0
    ADDITIVE = 1
    MULTIPLIED = 2
    ADD_COLORS = 3
    SUBTRACT_COLORS = 4
    ALPHA_PREMULTIPLY = 5
    CUSTOM = 6
    CUSTOM_SEPARATE = 7


class Layer(IntEnum):
    """Default render order. Lower values are drawn first.

    Attributes:
        BACKGROUND: World background.
        WORLD: General world layer.
        SHADOW: Entity shadows.
        ENTITIES: Standard entities (NPCs, objects).
        PLAYER: Player-specific layer.
        EFFECTS: Visual effects (damage numbers, spell VFX).
        UI_WORLD: UI elements bound to a world transform.
        UI: Screen-space UI elements.
        OVERLAY: Full-screen overlay (black during transitions).
        DEBUG: Debug visualizations (colliders, gizmos).
    """

    BACKGROUND = 0
    WORLD = 100
    SHADOW = 200
    ENTITIES = 300
    PLAYER = 400
    EFFECTS = 500
    UI_WORLD = 600
    UI = 800
    OVERLAY = 900
    DEBUG = 1000
