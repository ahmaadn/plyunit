"""Misc math utilities."""


def lerp_vector2(
    a: tuple[float, float],
    b: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Linearly interpolate between two 2D positions (tuples).

    Args:
        a: Start position as an ``(x, y)`` tuple.
        b: End position as an ``(x, y)`` tuple.
        t: Interpolation factor [0.0, 1.0] (will be clamped).

    Returns:
        tuple[float, float]: The interpolated ``(x, y)``.
    """
    clamped_t = clamp(t, 0.0, 1.0)
    return (
        a[0] + (b[0] - a[0]) * clamped_t,
        a[1] + (b[1] - a[1]) * clamped_t,
    )


def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between two float values.

    Args:
        a: Start value.
        b: End value.
        t: Interpolation factor [0.0, 1.0] (will be clamped).

    Returns:
        float: The interpolated value.
    """
    clamped_t = clamp(t, 0.0, 1.0)
    return a + (b - a) * clamped_t


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Constrain ``value`` to lie between ``min_value`` and ``max_value``.

    Args:
        value: Source value.
        min_value: Lower bound.
        max_value: Upper bound.

    Returns:
        float: The clamped value.
    """
    return max(min_value, min(max_value, value))
