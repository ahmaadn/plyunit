"""Example: ParticlePool SoA vectorized particle system.

Demonstrates the particle pool owned by Renderer:
- spawn particles through renderer.particles
- vectorized SoA update each frame
- partition submit: circles via submit_circle_batch

Controls:
- Left mouse click: burst at cursor
"""

from __future__ import annotations

import math
import random

import plyunit as pu
from plyunit.core.particles import Particle, ParticlePool


class ParticleApp(pu.App):
    def on_load(self) -> None:
        self.mouse = pu.Mouse()
        self._rng = random.Random(7)
        self._emit_timer = 0.0
        self._time = 0.0
        self.particles = ParticlePool(
            renderer=self.renderer,
            initial_capacity=512,
            max_alive=8192,
        )
        self.text = pu.Text()

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.mouse.update(dt)
        self._time += dt
        self._emit_timer += dt

        while self._emit_timer >= 0.025:
            self._emit_timer -= 0.025
            x = 400.0 + math.sin(self._time * 1.7) * 170.0
            y = 270.0 + math.cos(self._time * 2.1) * 65.0
            self._spawn_particle((x, y), speed=120.0, size=4.0)

        if self.mouse.is_pressed("left"):
            self._spawn_burst(self.mouse.position, count=42)

        self.particles.update(dt)
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def _spawn_burst(self, pos: tuple[float, float], count: int) -> None:
        for _ in range(count):
            self._spawn_particle(pos, speed=260.0, size=5.0)

    def _spawn_particle(
        self, pos: tuple[float, float], *, speed: float, size: float
    ) -> None:
        angle = self._rng.uniform(0.0, math.tau)
        velocity_scale = self._rng.uniform(0.25, 1.0)
        velocity = (
            math.cos(angle) * speed * velocity_scale,
            math.sin(angle) * speed * velocity_scale,
        )
        color_shift = self._rng.randint(-20, 35)
        particle = Particle(
            position=pos,
            velocity=velocity,
            lifetime=self._rng.uniform(0.55, 1.35),
            size=self._rng.uniform(size * 0.55, size * 1.45),
            angular_velocity=self._rng.uniform(-180.0, 180.0),
            tint=(255, 170 + color_shift, 70 + color_shift, 210),
        )
        self.particles.spawn(particle)

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((12, 14, 24, 255))
        self.scene_manager.render(self.renderer)

        particles = self.particles
        particles.submit(layer=pu.Layer.EFFECTS)

        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="ParticlePool SoA: click to burst",
            pos=(20, 18),
            font_size=20,
            color=(235, 238, 255, 255),
        )
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text=(
                f"Alive: {particles.count}/{particles.max_alive}  "
                f"cap={particles.capacity}  rejected={particles.spawn_rejected}"
            ),
            pos=(20, 44),
            font_size=14,
            color=(160, 170, 200, 255),
        )

        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        ParticleApp(),
        pu.AppConfig(
            title="ParticlePool Example",
            window_width=800,
            window_height=520,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()
