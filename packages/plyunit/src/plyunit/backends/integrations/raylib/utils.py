import pyray as pr

from plyunit.core.types import ColorType, RectType


def tuple2color(value: ColorType | None, default: ColorType = (0, 0, 0, 0)) -> pr.Color:
    """Build a raylib color from an RGBA tuple (``None`` -> ``default``)."""
    return pr.Color(*(value if value is not None else default))


def create_rect(value: RectType) -> pr.Rectangle:
    """Build a raylib rectangle from an ``(x, y, w, h)`` tuple."""
    return pr.Rectangle(*value)
