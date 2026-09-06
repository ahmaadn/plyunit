from __future__ import annotations

from plyunit.core.components.component import Component
from plyunit.core.particles import Particle, ParticlePool


class ParticleEmitter(Component):
    """Minimal particle emitter component (SoA pool)."""

    def __init__(
        self,
        *,
        initial_capacity: int = 512,
        max_alive: int = 8192,
    ) -> None:
        """Initializes the emitter with a ``ParticlePool`` of a given capacity.

        Args:
            initial_capacity: Initial capacity of the particle pool.
            max_alive: Maximum capacity of alive particles.
        """
        super().__init__("ParticleEmitter")
        self.particles = ParticlePool(
            None,
            initial_capacity=initial_capacity,
            max_alive=max_alive,
        )

    def spawn(
        self,
        position: tuple[float, float],
        *,
        velocity: tuple[float, float] = (0.0, 0.0),
        lifetime: float = 1.0,
        size: float = 1.0,
        tint: tuple[int, int, int, int] = (255, 255, 255, 255),
    ) -> Particle | None:
        """Spawns a single particle into the pool.

        Args:
            position: Initial position ``(x, y)``.
            velocity: Initial velocity ``(vx, vy)``.
            lifetime: Time to live (seconds).
            size: Particle size.
            tint: Particle RGBA color.

        Returns:
            Particle | None: The spawned particle, or ``None`` if the pool is full.
        """
        particle = Particle(
            position=position,
            velocity=velocity,
            lifetime=lifetime,
            size=size,
            tint=tint,
        )
        return self.particles.spawn(particle)
