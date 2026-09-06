from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from plyunit.core.particles import Particle, ParticlePool


class MockRenderer:
    def __init__(self) -> None:
        self.circle_batches: list[dict] = []
        self.sprites: list[dict] = []

    def render_circles(self, **kwargs) -> None:
        self.circle_batches.append(kwargs)

    def render_sprite(self, **kwargs) -> None:
        self.sprites.append(kwargs)


def _p(
    pos=(0.0, 0.0),
    vel=(0.0, 0.0),
    lifetime=1.0,
    age=0.0,
    size=1.0,
    rotation=0.0,
    angular_velocity=0.0,
    tint=(255, 255, 255, 255),
    texture=None,
    source_rect=None,
) -> Particle:
    return Particle(
        position=pos,
        velocity=vel,
        lifetime=lifetime,
        age=age,
        size=size,
        rotation=rotation,
        angular_velocity=angular_velocity,
        tint=tint,
        texture=texture,
        source_rect=source_rect,
    )


def test_spawn_increments_count():
    pr = ParticlePool(None, initial_capacity=8, max_alive=32)
    assert pr.spawn(_p(pos=(1.0, 2.0))) is not None
    assert pr.count == 1
    assert pr.alive_count == 1
    assert float(pr.pos_x[0]) == pytest.approx(1.0)
    assert float(pr.pos_y[0]) == pytest.approx(2.0)


def test_update_integrates_position_and_rotation():
    pr = ParticlePool(None, initial_capacity=4, max_alive=16)
    pr.spawn(_p(pos=(0.0, 0.0), vel=(10.0, -4.0), angular_velocity=90.0, lifetime=5.0))
    pr.update(0.5)
    assert float(pr.pos_x[0]) == pytest.approx(5.0)
    assert float(pr.pos_y[0]) == pytest.approx(-2.0)
    assert float(pr.rotation[0]) == pytest.approx(45.0)
    assert float(pr.age[0]) == pytest.approx(0.5)


def test_update_removes_dead_and_compacts():
    pr = ParticlePool(None, initial_capacity=8, max_alive=16)
    pr.spawn(_p(pos=(1.0, 0.0), lifetime=0.1, age=0.0))
    pr.spawn(_p(pos=(2.0, 0.0), lifetime=10.0, age=0.0))
    pr.spawn(_p(pos=(3.0, 0.0), lifetime=0.1, age=0.0))
    pr.update(0.2)
    assert pr.count == 1
    assert float(pr.pos_x[0]) == pytest.approx(2.0)


def test_grow_doubles_until_max():
    pr = ParticlePool(None, initial_capacity=2, max_alive=5)
    for i in range(5):
        assert pr.spawn(_p(pos=(float(i), 0.0))) is not None
    assert pr.count == 5
    assert pr.capacity == 5
    assert pr.spawn(_p()) is None
    assert pr.spawn_rejected == 1
    assert pr.count == 5


def test_spawn_reject_at_max_alive():
    pr = ParticlePool(None, initial_capacity=4, max_alive=3)
    assert pr.spawn(_p()) is not None
    assert pr.spawn(_p()) is not None
    assert pr.spawn(_p()) is not None
    rejected = pr.spawn(_p(pos=(9.0, 9.0)))
    assert rejected is None
    assert pr.count == 3
    assert pr.spawn_rejected == 1


def test_clear_resets_and_drops_texture_refs():
    tex = SimpleNamespace(id=7)
    pr = ParticlePool(None, initial_capacity=4, max_alive=8)
    pr.spawn(_p(texture=tex))
    assert pr.textures[0] is tex
    pr.clear()
    assert pr.count == 0
    assert pr.textures[0] is None


def test_submit_partitions_circle_batch_and_sprites():
    renderer = MockRenderer()
    pr = ParticlePool(renderer, initial_capacity=8, max_alive=16)
    tex_a = SimpleNamespace(id=1)
    tex_b = SimpleNamespace(id=2)
    pr.spawn(_p(pos=(1.0, 1.0), size=2.0, tint=(10, 20, 30, 40)))
    pr.spawn(
        _p(
            pos=(3.0, 4.0),
            size=1.5,
            rotation=12.0,
            tint=(1, 2, 3, 4),
            texture=tex_a,
            source_rect=(0.0, 0.0, 8.0, 8.0),
        )
    )
    pr.spawn(_p(pos=(5.0, 6.0), size=3.0, texture=tex_b))
    pr.spawn(_p(pos=(7.0, 8.0), size=4.0, tint=(5, 6, 7, 8)))

    pr.submit(layer=99)

    assert len(renderer.circle_batches) == 1
    batch = renderer.circle_batches[0]
    assert batch["layer"] == 99
    assert len(batch["centers"]) == 2
    assert (1.0, 1.0) in batch["centers"]
    assert (7.0, 8.0) in batch["centers"]
    assert len(batch["radii"]) == 2
    assert len(batch["colors"]) == 2

    assert len(renderer.sprites) == 2
    sprites_by_tex = {s["texture"].id: s for s in renderer.sprites}
    assert sprites_by_tex[1]["pos"] == (3.0, 4.0)
    assert sprites_by_tex[1]["source"] == (0.0, 0.0, 8.0, 8.0)
    assert sprites_by_tex[1]["rotation"] == pytest.approx(12.0)
    assert sprites_by_tex[1]["scale"] == pytest.approx(1.5)
    assert sprites_by_tex[1]["tint"] == (1, 2, 3, 4)
    assert sprites_by_tex[2]["pos"] == (5.0, 6.0)
    assert sprites_by_tex[2]["source"] is None


def test_submit_noop_without_renderer_or_particles():
    pr = ParticlePool(None, initial_capacity=4, max_alive=8)
    pr.submit()  # no renderer
    pr2 = ParticlePool(MockRenderer(), initial_capacity=4, max_alive=8)
    pr2.submit()  # empty
    assert pr2.count == 0


def test_dto_mutation_after_spawn_does_not_write_back():
    pr = ParticlePool(None, initial_capacity=4, max_alive=8)
    p = _p(pos=(1.0, 1.0), vel=(0.0, 0.0))
    pr.spawn(p)
    p.position = (99.0, 99.0)
    assert float(pr.pos_x[0]) == pytest.approx(1.0)


def test_update_all_dead():
    pr = ParticlePool(None, initial_capacity=4, max_alive=8)
    pr.spawn(_p(lifetime=0.1))
    pr.spawn(_p(lifetime=0.1))
    pr.update(1.0)
    assert pr.count == 0


def test_invalid_ctor_args():
    with pytest.raises(ValueError):
        ParticlePool(None, initial_capacity=0, max_alive=8)
    with pytest.raises(ValueError):
        ParticlePool(None, initial_capacity=4, max_alive=0)


def test_tint_and_source_written():
    pr = ParticlePool(None, initial_capacity=4, max_alive=8)
    pr.spawn(
        _p(
            tint=(10, 20, 30, 40),
            texture=object(),
            source_rect=(1.0, 2.0, 3.0, 4.0),
        )
    )
    assert tuple(int(x) for x in pr.tint[0]) == (10, 20, 30, 40)
    assert bool(pr.has_texture[0])
    assert bool(pr.has_source[0])
    assert np.allclose(pr.source_rect[0], (1.0, 2.0, 3.0, 4.0))
