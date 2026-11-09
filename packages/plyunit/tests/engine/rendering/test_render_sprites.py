"""Renderer.render_sprites: N textures at N positions (bulk SoA, no GPU)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import numpy as np
import pytest

from plyunit.rendering.renderer import Renderer
from rendering_fakes import TextureIdAdapter, make_texture


class FakeUbr(TextureIdAdapter):
    capacity = 64

    def __init__(self) -> None:
        self.submits: list[dict] = []

    def init(self, n: int) -> None:
        self.capacity = n

    def shutdown(self) -> None:
        pass

    def submit_frame(self, **kwargs) -> None:
        assert kwargs["n_sprites"] >= 1
        self.submits.append(kwargs)


def make_renderer(max_sprites: int = 64) -> tuple[Renderer, FakeUbr]:
    ubr = FakeUbr()
    renderer = Renderer(
        # pyrefly: ignore [bad-argument-type]
        canvas=SimpleNamespace(),
        ubr=ubr,
        max_sprites=max_sprites,
    )
    renderer.reset_frame()
    return renderer, ubr


def test_render_sprites_writes_soa_per_texture() -> None:
    renderer, _ubr = make_renderer()
    tex_a = make_texture(11, 8, 4)
    tex_b = make_texture(22, 16, 16)

    renderer.render_sprites(
        textures=[tex_a, tex_b],
        positions=[(1.0, 2.0), (3.0, 4.0)],
        rotations=[0.0, 90.0],
        tints=[(255, 0, 0, 255), (0, 255, 0, 128)],
        scales=[1.0, 2.0],
        origins=[(0.0, 0.0), (8.0, 8.0)],
    )

    fb = renderer._frame_buffer
    assert fb.count == 2
    assert [int(t) for t in fb.tex_id[:2]] == [11, 22]
    assert float(fb.pos_xy[0, 0]) == pytest.approx(1.0)
    assert float(fb.pos_xy[0, 1]) == pytest.approx(2.0)
    assert float(fb.pos_xy[1, 0]) == pytest.approx(3.0)
    assert float(fb.pos_xy[1, 1]) == pytest.approx(4.0)
    # size = texture size * scale, per sprite.
    assert float(fb.size_wh[0, 0]) == pytest.approx(8.0)
    assert float(fb.size_wh[0, 1]) == pytest.approx(4.0)
    assert float(fb.size_wh[1, 0]) == pytest.approx(32.0)
    assert float(fb.size_wh[1, 1]) == pytest.approx(32.0)
    assert float(fb.rotation_deg[0]) == pytest.approx(0.0)
    assert float(fb.rotation_deg[1]) == pytest.approx(90.0)
    assert list(fb.rgba[0]) == [255, 0, 0, 255]
    assert list(fb.rgba[1]) == [0, 255, 0, 128]
    assert float(fb.origin_xy[1, 0]) == pytest.approx(8.0)
    assert float(fb.origin_xy[1, 1]) == pytest.approx(8.0)
    # Tanpa source: UV penuh.
    assert list(fb.uv_rect[0]) == pytest.approx([0.0, 0.0, 1.0, 1.0])
    # submit_index berurutan.
    assert [int(i) for i in fb.submit_index[:2]] == [0, 1]


def test_render_sprites_sources_resolve_uv_per_texture() -> None:
    renderer, _ubr = make_renderer()
    tex = make_texture(7, 32, 32)

    renderer.render_sprites(
        textures=[tex, tex],
        positions=[(0.0, 0.0), (10.0, 10.0)],
        sources=[(0.0, 0.0, 16.0, 16.0), (16.0, 0.0, 16.0, 32.0)],
    )

    fb = renderer._frame_buffer
    assert fb.count == 2
    assert list(fb.uv_rect[0]) == pytest.approx([0.0, 0.0, 0.5, 0.5])
    assert list(fb.uv_rect[1]) == pytest.approx([0.5, 0.0, 1.0, 1.0])
    # size mengikuti source rect, bukan full texture.
    assert float(fb.size_wh[0, 0]) == pytest.approx(16.0)
    assert float(fb.size_wh[1, 1]) == pytest.approx(32.0)


def test_render_sprites_skips_none_and_empty_inputs() -> None:
    renderer, _ubr = make_renderer()
    tex = make_texture(1, 4, 4)

    renderer.render_sprites(textures=[], positions=[])
    renderer.render_sprites(textures=None, positions=None)
    renderer.render_sprites(textures=[tex], positions=None)
    assert renderer._frame_buffer.count == 0

    renderer.render_sprites(
        textures=[tex, None, tex],
        positions=[(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
    )
    fb = renderer._frame_buffer
    assert fb.count == 2
    assert [int(t) for t in fb.tex_id[:2]] == [1, 1]
    assert float(fb.pos_xy[1, 0]) == pytest.approx(2.0)


def test_render_sprites_min_length_semantics() -> None:
    renderer, _ubr = make_renderer()
    tex = make_texture(1, 4, 4)

    renderer.render_sprites(
        textures=[tex, tex, tex],
        positions=[(0.0, 0.0), (1.0, 1.0)],
    )
    assert renderer._frame_buffer.count == 2


def test_render_sprites_pos_xy_fast_path() -> None:
    renderer, _ubr = make_renderer()
    tex_a = make_texture(1, 4, 4)
    tex_b = make_texture(2, 8, 8)
    pos_xy = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)

    renderer.render_sprites(textures=[tex_a, tex_b], pos_xy=pos_xy)

    fb = renderer._frame_buffer
    assert fb.count == 2
    assert float(fb.pos_xy[1, 1]) == pytest.approx(3.0)
    assert [int(t) for t in fb.tex_id[:2]] == [1, 2]


def test_render_sprites_flush_submits_all_sprites() -> None:
    renderer, ubr = make_renderer()
    for name in ("ui", "debug"):
        p = renderer.get_pass(name)
        if p:
            p.enabled = False
    tex_a = make_texture(1, 4, 4)
    tex_b = make_texture(2, 8, 8)

    renderer.render_sprites(
        textures=[tex_a, tex_b, tex_a],
        positions=[(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
    )
    assert renderer._frame_buffer.count == 3
    renderer.flush_all()

    assert len(ubr.submits) == 1
    assert ubr.submits[0]["n_sprites"] == 3


def test_render_sprites_overflows_capacity_with_force_flush() -> None:
    renderer, ubr = make_renderer(max_sprites=4)
    tex = make_texture(1, 4, 4)
    positions = [(float(i), 0.0) for i in range(6)]

    renderer.render_sprites(textures=[tex] * 6, positions=positions)

    # Capacity 4: at least one force-flush happens mid-submit.
    assert len(ubr.submits) >= 1
    assert (
        sum(int(s["n_sprites"]) for s in ubr.submits) + (renderer._frame_buffer.count)
        == 6
    )


def test_render_sprites_submit_index_increments_after_single_sprite() -> None:
    renderer, _ubr = make_renderer()
    tex = make_texture(1, 4, 4)

    renderer.render_sprite(texture=tex, pos=(9.0, 9.0))
    renderer.render_sprites(textures=[tex, tex], positions=[(0.0, 0.0), (1.0, 1.0)])

    fb = renderer._frame_buffer
    assert fb.count == 3
    assert [int(i) for i in fb.submit_index[:3]] == [0, 1, 2]


def test_render_sprites_profile_counters() -> None:
    renderer, _ubr = make_renderer()
    renderer.profile_enabled = True
    renderer.reset_frame()
    tex = make_texture(1, 4, 4)

    renderer.render_sprites(textures=[tex, tex], positions=[(0.0, 0.0), (1.0, 1.0)])

    assert renderer.frame_profile["sprite_count"] == 2.0
    assert renderer.frame_profile["sprite_batch_count"] == 1.0


@pytest.mark.parametrize(
    "source_kind", ["implicit", "none", "explicit", "list", "array"]
)
def test_whole_texture_sources_skip_uv_recalculation(
    monkeypatch: pytest.MonkeyPatch, source_kind: str
) -> None:
    import plyunit.rendering.renderer as renderer_module

    renderer, _ubr = make_renderer()
    textures = [make_texture(index, 16, 8) for index in range(1, 9)]
    sources: Any
    if source_kind == "implicit":
        sources = None
    elif source_kind == "none":
        sources = [None] * len(textures)
    elif source_kind == "list":
        sources = [[0.0, 0.0, 16.0, 8.0] for _ in textures]
    elif source_kind == "array":
        sources = np.tile((0.0, 0.0, 16.0, 8.0), (len(textures), 1))
    else:
        sources = [(0.0, 0.0, 16.0, 8.0)] * len(textures)
    resolve = Mock(wraps=renderer_module.resolve_uv)
    monkeypatch.setattr(renderer_module, "resolve_uv", resolve)

    renderer.render_sprites(
        textures=textures,
        pos_xy=np.zeros((len(textures), 2), dtype=np.float32),
        sources=cast(Any, sources),
    )

    resolve.assert_not_called()
    assert renderer._frame_buffer.uv_rect[: len(textures)].tolist() == [
        [0.0, 0.0, 1.0, 1.0]
    ] * len(textures)
    assert renderer._frame_buffer.size_wh[: len(textures)].tolist() == [
        [16.0, 8.0]
    ] * len(textures)


@pytest.mark.parametrize("explicit", [False, True])
def test_bulk_fast_path_preserves_region_and_flipped_sources(
    monkeypatch: pytest.MonkeyPatch, explicit: bool
) -> None:
    import plyunit.rendering.renderer as renderer_module

    renderer, _ubr = make_renderer()
    rectangles = [
        (0.0, 0.0, 32.0, 32.0),
        (8.0, 16.0, 8.0, 8.0),
        (32.0, 32.0, -16.0, -16.0),
    ]
    textures = [
        make_texture(index, 32, 32, source_rect=rect)
        for index, rect in enumerate(rectangles, start=1)
    ]
    resolve = Mock(wraps=renderer_module.resolve_uv)
    monkeypatch.setattr(renderer_module, "resolve_uv", resolve)

    renderer.render_sprites(
        textures=textures,
        positions=[(0.0, 0.0)] * len(textures),
        sources=rectangles if explicit else None,
        scales=[1.0, 2.0, 0.5],
    )

    assert resolve.call_count == 2
    np.testing.assert_allclose(
        renderer._frame_buffer.uv_rect[:3],
        [(0.0, 0.0, 1.0, 1.0), (0.25, 0.5, 0.5, 0.75), (1.0, 1.0, 0.5, 0.5)],
    )
    np.testing.assert_allclose(
        renderer._frame_buffer.size_wh[:3], [(32.0, 32.0), (16.0, 16.0), (8.0, 8.0)]
    )
    assert renderer._frame_buffer.tex_id[:3].tolist() == [1, 2, 3]
