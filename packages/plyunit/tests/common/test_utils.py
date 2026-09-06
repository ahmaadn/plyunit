from __future__ import annotations

import math

import plyunit as pu


def test_math_helpers_clamp_and_lerp_vector2_behavior():

    assert pu.math.clamp(-3.0, 0.0, 1.0) == 0.0
    assert pu.math.clamp(0.5, 0.0, 1.0) == 0.5
    assert pu.math.clamp(4.0, 0.0, 1.0) == 1.0

    assert math.isclose(pu.math.lerp(0.0, 10.0, -1.0), 0.0)
    assert math.isclose(pu.math.lerp(0.0, 10.0, 0.25), 2.5)
    assert math.isclose(pu.math.lerp(0.0, 10.0, 2.0), 10.0)

    result = pu.math.lerp_vector2((0.0, 0.0), (8.0, 4.0), 0.25)
    assert math.isclose(result[0], 2.0)
    assert math.isclose(result[1], 1.0)


def test_transform2d_copy_and_combine_full_parent_transform():

    local = pu.Transform2D(position=(1.0, 2.0), rotation=15.0, scale=(4.0, 5.0))
    copied = local.copy()

    assert copied is not local
    assert math.isclose(copied.position[0], 1.0)
    assert math.isclose(copied.position[1], 2.0)
    assert math.isclose(copied.rotation, 15.0)
    assert math.isclose(copied.scale[0], 4.0)
    assert math.isclose(copied.scale[1], 5.0)

    parent = pu.Transform2D(position=(10.0, 20.0), rotation=90.0, scale=(2.0, 3.0))
    world = local.combine(parent)

    # local(1,2) -> scale parent => (2,6) -> rotate 90deg => (-6,2) -> translate => (4,22)
    assert math.isclose(world.position[0], 4.0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(world.position[1], 22.0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(world.rotation, 105.0)
    assert math.isclose(world.scale[0], 8.0)
    assert math.isclose(world.scale[1], 15.0)


def test_transform_state_recalc_and_lerp_world():

    state = pu.TransformState()
    assert state.dirty is True

    state.set_position(3.0, 4.0)
    state.set_rotation(45.0)
    state.set_scale(2.0, 2.0)
    assert state.dirty is True

    state.recalc_world(parent_world=None)
    assert state.dirty is False
    assert math.isclose(state.world.position[0], 3.0)
    assert math.isclose(state.world.position[1], 4.0)
    assert math.isclose(state.world.rotation, 45.0)

    parent = pu.Transform2D(position=(1.0, 1.0), rotation=0.0, scale=(2.0, 2.0))
    state.mark_dirty()
    state.recalc_world(parent_world=parent)
    assert math.isclose(state.world.position[0], 7.0)
    assert math.isclose(state.world.position[1], 9.0)

    state.previous_world = pu.Transform2D(
        position=(0.0, 0.0), rotation=0.0, scale=(1.0, 1.0)
    )
    state.world = pu.Transform2D(position=(10.0, 20.0), rotation=90.0, scale=(3.0, 5.0))

    # t < 0 must clamp to previous_world
    lerp_prev = state.lerp_world(-1.0)
    assert math.isclose(lerp_prev.position[0], 0.0)
    assert math.isclose(lerp_prev.position[1], 0.0)
    assert math.isclose(lerp_prev.rotation, 0.0)

    # t in the middle
    lerp_mid = state.lerp_world(0.5)
    assert math.isclose(lerp_mid.position[0], 5.0)
    assert math.isclose(lerp_mid.position[1], 10.0)
    assert math.isclose(lerp_mid.rotation, 45.0)
    assert math.isclose(lerp_mid.scale[0], 2.0)
    assert math.isclose(lerp_mid.scale[1], 3.0)

    # t > 1 must clamp to world
    lerp_world = state.lerp_world(2.0)
    assert math.isclose(lerp_world.position[0], 10.0)
    assert math.isclose(lerp_world.position[1], 20.0)
    assert math.isclose(lerp_world.rotation, 90.0)
