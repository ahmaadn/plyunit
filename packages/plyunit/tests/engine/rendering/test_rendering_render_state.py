from __future__ import annotations

from plyunit.rendering.enum import BlendMode
from plyunit.rendering.render_state import RenderState


def test_render_state_initialization() -> None:
    state = RenderState()
    assert state.scissor is None
    assert state.blend_mode == BlendMode.ALPHA
    assert state.shader is None

def test_render_state_equality_and_hash() -> None:
    from unittest.mock import MagicMock
    shader1 = MagicMock()
    shader2 = MagicMock()

    state1 = RenderState(scissor=(0, 0, 100, 100), blend_mode=BlendMode.ADDITIVE, shader=shader1)
    state2 = RenderState(scissor=(0, 0, 100, 100), blend_mode=BlendMode.ADDITIVE, shader=shader1)
    state3 = RenderState(scissor=(0, 0, 50, 50), blend_mode=BlendMode.ADDITIVE, shader=shader1)
    state4 = RenderState(scissor=(0, 0, 100, 100), blend_mode=BlendMode.MULTIPLIED, shader=shader1)
    state5 = RenderState(scissor=(0, 0, 100, 100), blend_mode=BlendMode.ADDITIVE, shader=shader2)
    RenderState(scissor=(0, 0, 100, 100), blend_mode=BlendMode.ADDITIVE, shader=shader1)

    assert state1 == state2
    assert state1 != state3
    assert state1 != state4
    assert state1 != state5
    assert state1 != "not_a_state"

    # Hash check
    assert hash(state1) == hash(state2)
    assert hash(state1) != hash(state3)

    # Dictionary grouping
    d = {state1: "group1"}
    assert d[state2] == "group1"
