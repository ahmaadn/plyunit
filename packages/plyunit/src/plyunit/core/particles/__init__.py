"""Particle pool subpackage.

Contains the NumPy Structure-of-Arrays (SoA) based :class:`ParticlePool` for
batched particle rendering.
"""

from .pool import Particle, ParticlePool

__all__ = [
    "Particle",
    "ParticlePool",
]
