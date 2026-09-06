"""Dense Structure-of-Arrays (SoA) particle pool with batched renderer submission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

_DEFAULT_INITIAL = 512
"""Default initial capacity for :class:`ParticlePool`."""

_DEFAULT_MAX_ALIVE = 8192
"""Default upper bound of alive particles for :class:`ParticlePool`."""


@dataclass(slots=True)
class Particle:
    """Particle spawn DTO.

    Used as the payload for :meth:`ParticlePool.spawn`. After spawning,
    mutating this instance's fields is not written back to the SoA pool —
    the pool keeps its own copy of the values.

    Attributes:
        position: Initial particle position ``(x, y)`` (pixels).
        velocity: Initial velocity ``(vx, vy)`` (pixels/second).
        lifetime: Maximum lifetime in seconds.
        age: Initial age (default 0).
        size: Size scale (for sprites) or radius (for circles).
        rotation: Initial rotation in degrees.
        angular_velocity: Rotation speed (degrees/second).
        tint: RGBA color 0-255.
        texture: Backend texture object (None = circle).
        source_rect: Source rectangle ``(x, y, w, h)`` of the texture (None = full).
    """

    position: tuple[float, float]
    velocity: tuple[float, float] = (0.0, 0.0)
    lifetime: float = 1.0
    age: float = 0.0
    size: float = 1.0
    rotation: float = 0.0
    angular_velocity: float = 0.0
    tint: tuple[int, int, int, int] = (255, 255, 255, 255)
    texture: object | None = None
    source_rect: tuple[float, float, float, float] | None = None


class ParticlePool:
    """Dense NumPy Structure-of-Arrays (SoA) based particle pool.

    Supports partitioning alive particles with swap-remove and submitting
    batches to the renderer (sprite + circle). Buffers can grow up to
    ``max_alive``.

    Attributes:
        max_alive: Upper bound on the number of alive particles.
        spawn_rejected: Counter of rejected spawns (full or growth failed).
    """

    def __init__(
        self,
        renderer: Any = None,
        *,
        initial_capacity: int = _DEFAULT_INITIAL,
        max_alive: int = _DEFAULT_MAX_ALIVE,
    ) -> None:
        """Initialize the pool with a target renderer and capacities.

        Args:
            renderer: Backend renderer to submit to (may be ``None`` during
                initial setup; submit then becomes a no-op).
            initial_capacity: Initial capacity of the NumPy buffers (``>= 1``).
            max_alive: Upper bound on alive particles (``>= 1``).

        Raises:
            ValueError: If ``max_alive`` or ``initial_capacity`` < 1.
        """
        if max_alive < 1:
            raise ValueError("max_alive must be >= 1")
        if initial_capacity < 1:
            raise ValueError("initial_capacity must be >= 1")
        self._renderer = renderer
        self.max_alive = int(max_alive)
        self._count = 0
        self.spawn_rejected = 0
        cap = min(int(initial_capacity), self.max_alive)
        self._alloc(cap)
        self._staging_centers: list[tuple[float, float]] = []
        self._staging_radii: list[float] = []
        self._staging_colors: list[tuple[int, int, int, int]] = []

    def _alloc(self, capacity: int) -> None:
        """Reallocate the NumPy buffers with a new capacity.

        Args:
            capacity: New capacity (all existing particles are reset).
        """
        self.capacity = capacity
        self.pos_x = np.zeros(capacity, dtype=np.float32)
        self.pos_y = np.zeros(capacity, dtype=np.float32)
        self.vel_x = np.zeros(capacity, dtype=np.float32)
        self.vel_y = np.zeros(capacity, dtype=np.float32)
        self.age = np.zeros(capacity, dtype=np.float32)
        self.lifetime = np.zeros(capacity, dtype=np.float32)
        self.size = np.zeros(capacity, dtype=np.float32)
        self.rotation = np.zeros(capacity, dtype=np.float32)
        self.angular_velocity = np.zeros(capacity, dtype=np.float32)
        self.tint = np.zeros((capacity, 4), dtype=np.uint8)
        self.has_texture = np.zeros(capacity, dtype=np.bool_)
        self.textures = np.empty(capacity, dtype=object)
        self.textures[:] = None
        self.source_rect = np.zeros((capacity, 4), dtype=np.float32)
        self.has_source = np.zeros(capacity, dtype=np.bool_)
        self.capacity = capacity
        self.pos_x = np.zeros(capacity, dtype=np.float32)
        self.pos_y = np.zeros(capacity, dtype=np.float32)
        self.vel_x = np.zeros(capacity, dtype=np.float32)
        self.vel_y = np.zeros(capacity, dtype=np.float32)
        self.age = np.zeros(capacity, dtype=np.float32)
        self.lifetime = np.zeros(capacity, dtype=np.float32)
        self.size = np.zeros(capacity, dtype=np.float32)
        self.rotation = np.zeros(capacity, dtype=np.float32)
        self.angular_velocity = np.zeros(capacity, dtype=np.float32)
        self.tint = np.zeros((capacity, 4), dtype=np.uint8)
        self.has_texture = np.zeros(capacity, dtype=np.bool_)
        self.textures = np.empty(capacity, dtype=object)
        self.textures[:] = None
        self.source_rect = np.zeros((capacity, 4), dtype=np.float32)
        self.has_source = np.zeros(capacity, dtype=np.bool_)

    def _grow(self) -> bool:
        """Grow the NumPy buffers (doubling) up to ``max_alive``.

        Returns:
            bool: ``True`` if the buffers were grown, ``False`` if already
            at ``max_alive`` or no growth occurred.
        """
        if self.capacity >= self.max_alive:
            return False
        new_cap = min(max(self.capacity * 2, 1), self.max_alive)
        if new_cap <= self.capacity:
            return False
        n = self._count
        old = (
            self.pos_x,
            self.pos_y,
            self.vel_x,
            self.vel_y,
            self.age,
            self.lifetime,
            self.size,
            self.rotation,
            self.angular_velocity,
            self.tint,
            self.has_texture,
            self.textures,
            self.source_rect,
            self.has_source,
        )
        self._alloc(new_cap)
        self.pos_x[:n] = old[0][:n]
        self.pos_y[:n] = old[1][:n]
        self.vel_x[:n] = old[2][:n]
        self.vel_y[:n] = old[3][:n]
        self.age[:n] = old[4][:n]
        self.lifetime[:n] = old[5][:n]
        self.size[:n] = old[6][:n]
        self.rotation[:n] = old[7][:n]
        self.angular_velocity[:n] = old[8][:n]
        self.tint[:n] = old[9][:n]
        self.has_texture[:n] = old[10][:n]
        self.textures[:n] = old[11][:n]
        self.source_rect[:n] = old[12][:n]
        self.has_source[:n] = old[13][:n]
        return True

    @property
    def count(self) -> int:
        """Current number of alive particles.

        Returns:
            int: The ``_count`` value.
        """
        return self._count

    @property
    def alive_count(self) -> int:
        """Alias for :attr:`count`.

        Returns:
            int: Number of alive particles.
        """
        return self._count

    def clear(self) -> None:
        """Remove all alive particles from the pool (buffers stay allocated)."""
        if self._count > 0:
            self.textures[: self._count] = None
        self._count = 0

    def spawn(self, particle: Particle) -> Particle | None:
        """Spawn a single particle into the pool.

        Args:
            particle: Particle payload to copy into the buffers.

        Returns:
            Particle | None: Returns ``particle`` on success, or ``None``
            if the pool is full (``spawn_rejected`` is incremented).
        """
        if self._count >= self.max_alive:
            self.spawn_rejected += 1
            return None
        if self._count >= self.capacity and not self._grow():
            self.spawn_rejected += 1
            return None

        i = self._count
        px, py = particle.position
        vx, vy = particle.velocity
        self.pos_x[i] = px
        self.pos_y[i] = py
        self.vel_x[i] = vx
        self.vel_y[i] = vy
        self.age[i] = particle.age
        self.lifetime[i] = particle.lifetime
        self.size[i] = particle.size
        self.rotation[i] = particle.rotation
        self.angular_velocity[i] = particle.angular_velocity
        r, g, b, a = particle.tint
        self.tint[i, 0] = r
        self.tint[i, 1] = g
        self.tint[i, 2] = b
        self.tint[i, 3] = a
        tex = particle.texture
        self.has_texture[i] = tex is not None
        self.textures[i] = tex
        src = particle.source_rect
        if src is not None:
            self.has_source[i] = True
            self.source_rect[i, 0] = src[0]
            self.source_rect[i, 1] = src[1]
            self.source_rect[i, 2] = src[2]
            self.source_rect[i, 3] = src[3]
        else:
            self.has_source[i] = False
        self._count = i + 1
        return particle

    def update(self, dt: float) -> None:
        """Integrate particles and compact away dead ones.

        Args:
            dt: Delta time in seconds.
        """
        n = self._count
        if n == 0:
            return
        dt32 = np.float32(dt)
        sl = slice(0, n)
        self.age[sl] += dt32
        self.pos_x[sl] += self.vel_x[sl] * dt32
        self.pos_y[sl] += self.vel_y[sl] * dt32
        self.rotation[sl] += self.angular_velocity[sl] * dt32

        alive = self.age[sl] < self.lifetime[sl]
        alive_n = int(np.count_nonzero(alive))
        if alive_n == n:
            return
        if alive_n == 0:
            self.textures[:n] = None
            self._count = 0
            return

        idx = np.nonzero(alive)[0]
        self.pos_x[:alive_n] = self.pos_x[idx]
        self.pos_y[:alive_n] = self.pos_y[idx]
        self.vel_x[:alive_n] = self.vel_x[idx]
        self.vel_y[:alive_n] = self.vel_y[idx]
        self.age[:alive_n] = self.age[idx]
        self.lifetime[:alive_n] = self.lifetime[idx]
        self.size[:alive_n] = self.size[idx]
        self.rotation[:alive_n] = self.rotation[idx]
        self.angular_velocity[:alive_n] = self.angular_velocity[idx]
        self.tint[:alive_n] = self.tint[idx]
        self.has_texture[:alive_n] = self.has_texture[idx]
        self.textures[:alive_n] = self.textures[idx]
        self.source_rect[:alive_n] = self.source_rect[idx]
        self.has_source[:alive_n] = self.has_source[idx]
        if alive_n < n:
            self.textures[alive_n:n] = None
        self._count = alive_n

    def submit(self, **kwargs: Any) -> None:
        """Submit the batch of alive particles to the renderer.

        Particles with a ``texture`` are sent via ``render_sprite`` and
        grouped by texture ID; particles without a texture are sent as
        ``render_circles``.

        Args:
            **kwargs: Extra parameters forwarded to the renderer.
        """
        renderer = self._renderer
        if renderer is None:
            return
        n = self._count
        if n == 0:
            return

        has_tex = self.has_texture[:n]
        circle_idx = np.flatnonzero(~has_tex)
        tex_idx = np.flatnonzero(has_tex)

        if circle_idx.size:
            centers = self._staging_centers
            radii = self._staging_radii
            colors = self._staging_colors
            centers.clear()
            radii.clear()
            colors.clear()
            px = self.pos_x
            py = self.pos_y
            sz = self.size
            tint = self.tint
            for i in circle_idx:
                ii = int(i)
                centers.append((float(px[ii]), float(py[ii])))
                radii.append(float(sz[ii]))
                t = tint[ii]
                colors.append((int(t[0]), int(t[1]), int(t[2]), int(t[3])))
            renderer.render_circles(
                centers=centers, radii=radii, colors=colors, **kwargs
            )

        if tex_idx.size == 0:
            return

        groups: dict[int, list[int]] = {}
        textures = self.textures
        for i in tex_idx:
            ii = int(i)
            tex = textures[ii]
            if tex is None:
                continue
            tid = int(tex.id)
            bucket = groups.get(tid)
            if bucket is None:
                groups[tid] = [ii]
            else:
                bucket.append(ii)

        px = self.pos_x
        py = self.pos_y
        sz = self.size
        rot = self.rotation
        tint = self.tint
        has_source = self.has_source
        source_rect = self.source_rect
        for indices in groups.values():
            for ii in indices:
                tex = textures[ii]
                t = tint[ii]
                src = None
                if has_source[ii]:
                    s = source_rect[ii]
                    src = (float(s[0]), float(s[1]), float(s[2]), float(s[3]))
                renderer.render_sprite(
                    texture=tex,
                    pos=(float(px[ii]), float(py[ii])),
                    source=src,
                    rotation=float(rot[ii]),
                    scale=float(sz[ii]),
                    tint=(int(t[0]), int(t[1]), int(t[2]), int(t[3])),
                    **kwargs,
                )
