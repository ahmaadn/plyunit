"""Easing functions for tweens (map ``t`` in ``[0, 1]`` to an eased ``t``)."""

from __future__ import annotations

import math
from collections.abc import Callable

EaseFn = Callable[[float], float]


def linear(t: float) -> float:
    """Linear easing (no acceleration).

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: ``t`` unmodified.
    """
    return t


def quad_in(t: float) -> float:
    """Quadratic-in easing: slow acceleration at the start.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    return t * t


def quad_out(t: float) -> float:
    """Quadratic-out easing: slow deceleration at the end.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    return t * (2.0 - t)


def quad_in_out(t: float) -> float:
    """Quadratic in-out easing: accelerate then decelerate.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t < 0.5:
        return 2.0 * t * t
    return -1.0 + (4.0 - 2.0 * t) * t


def cubic_in(t: float) -> float:
    """Cubic-in easing: strong acceleration at the start.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    return t * t * t


def cubic_out(t: float) -> float:
    """Cubic-out easing: strong deceleration at the end.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    u = t - 1.0
    return u * u * u + 1.0


def cubic_in_out(t: float) -> float:
    """Cubic in-out easing: accelerate then decelerate.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t < 0.5:
        return 4.0 * t * t * t
    return (t - 1.0) * (2.0 * t - 2.0) * (2.0 * t - 2.0) + 1.0


def expo_in(t: float) -> float:
    """Exponential-in easing: sharp acceleration at the start.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t <= 0.0:
        return 0.0
    return math.pow(2.0, 10.0 * (t - 1.0))


def expo_out(t: float) -> float:
    """Exponential-out easing: sharp deceleration at the end.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t >= 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


def expo_in_out(t: float) -> float:
    """Exponential in-out easing: sharp at both ends.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 0.5 * math.pow(2.0, 20.0 * t - 10.0)
    return 1.0 - 0.5 * math.pow(2.0, -20.0 * t + 10.0)


def back_out(t: float) -> float:
    """Back-out easing: slight overshoot, then return to the target.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    c1 = 1.70158
    c3 = c1 + 1.0
    u = t - 1.0
    return 1.0 + c3 * u * u * u + c1 * u * u


def elastic_out(t: float) -> float:
    """Elastic-out easing: spring-like oscillation ending at the target.

    Args:
        t: Raw ``t`` value in ``[0, 1]``.

    Returns:
        float: The eased value.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


EASINGS: dict[str, EaseFn] = {
    "linear": linear,
    "quad_in": quad_in,
    "quad_out": quad_out,
    "quad_in_out": quad_in_out,
    "cubic_in": cubic_in,
    "cubic_out": cubic_out,
    "cubic_in_out": cubic_in_out,
    "expo_in": expo_in,
    "expo_out": expo_out,
    "expo_in_out": expo_in_out,
    "back_out": back_out,
    "elastic_out": elastic_out,
}


def get_easing(name: str | EaseFn) -> EaseFn:
    """Resolve an easing name or function into an ``EaseFn`` callable.

    Args:
        name: Easing name (str) or a callable that already is an easing.

    Returns:
        EaseFn: The easing function, ready to use.

    Raises:
        ValueError: If ``name`` is an unrecognized string.
    """
    if callable(name):
        return name
    key = str(name).lower()
    try:
        return EASINGS[key]
    except KeyError as exc:
        known = ", ".join(sorted(EASINGS))
        raise ValueError(f"unknown easing {name!r}; known: {known}") from exc
