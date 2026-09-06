"""Spatial audio module (math helpers for 2D pan and attenuation).

Contains only the pure function ``compute_spatial``; no state.
"""

from __future__ import annotations

import math


def compute_spatial(
    listener: tuple[float, float],
    source: tuple[float, float],
    min_distance: float,
    max_distance: float,
    rolloff: float = 1.0,
) -> tuple[float, float]:
    """Compute ``(volume_mul, pan)`` for a 2D source relative to the listener.

    Args:
        listener: World listener position ``(x, y)``.
        source: Source position ``(x, y)``.
        min_distance: Distance below which volume = ``1.0`` (full volume).
        max_distance: Distance beyond which volume = ``0.0`` (inaudible).
        rolloff: Falloff exponent (``1.0`` = linear; ``>1`` falls off faster).

    Returns:
        tuple[float, float]: ``(volume_mul, pan)`` where:
            - ``volume_mul``: ``1.0`` when ``dist <= min_distance``,
              ``0.0`` when ``dist >= max_distance``, linear falloff in
              between (shaped by ``rolloff``).
            - ``pan``: ``0.0`` left … ``1.0`` right (``0.5`` center), from
              the signed ``dx``.
    """
    lx, ly = listener
    sx, sy = source
    dx = sx - lx
    dy = sy - ly
    dist = math.hypot(dx, dy)

    if max_distance <= min_distance:
        volume_mul = 1.0 if dist <= min_distance else 0.0
    elif dist <= min_distance:
        volume_mul = 1.0
    elif dist >= max_distance:
        volume_mul = 0.0
    else:
        t = (dist - min_distance) / (max_distance - min_distance)
        # rolloff > 1 falls off faster; 0 < rolloff < 1 slower.
        volume_mul = max(0.0, min(1.0, (1.0 - t) ** float(rolloff)))

    # Stereo pan from horizontal offset; scale so pan reaches edges near max_distance.
    span = max(max_distance, 1.0)
    pan = 0.5 + 0.5 * max(-1.0, min(1.0, dx / span))
    return volume_mul, pan
