"""Domain FrameBuffer + runs (no GPU expand)."""

from __future__ import annotations

import numpy as np
import pytest

from plyunit.rendering.frame_buffer import (
    MAX_SPRITES,
    FrameBuffer,
    build_runs,
    pass_name_hash,
    resolve_uv,
)


def test_max_sprites_default():
    assert MAX_SPRITES == 16384


def test_resolve_uv():
    assert resolve_uv(None, 32, 32) == (0.0, 0.0, 1.0, 1.0)
    u0, v0, u1, v1 = resolve_uv((8, 0, 8, 16), 32, 32)
    assert abs(u0 - 0.25) < 1e-6 and abs(u1 - 0.5) < 1e-6


def test_build_runs():
    tex = np.array([1, 2, 2, 1], dtype=np.int32)
    order, runs = build_runs(tex, 4)
    assert list(tex[order]) == [1, 1, 2, 2]
    assert runs.shape[0] == 2


def test_frame_buffer_force_flush_on_full():
    flushes = []

    def on_full():
        flushes.append(fb.count)
        fb.reset()

    fb = FrameBuffer(capacity=2)
    fb.set_on_full(on_full)
    kw = dict(
        size=(1.0, 1.0),
        origin=(0.0, 0.0),
        rotation=0.0,
        rgba=(255, 255, 255, 255),
        uv=(0.0, 0.0, 1.0, 1.0),
        tex_id=1,
        sort_key=0.0,
        layer=100,
        state_id=0,
        pass_hash=1,
        depth_sorted=False,
        screen_space=False,
    )
    fb.append(pos=(0.0, 0.0), submit_index=0, **kw)
    fb.append(pos=(1.0, 0.0), submit_index=1, **kw)
    assert fb.count == 2
    fb.append(pos=(2.0, 0.0), submit_index=2, **kw)
    assert flushes == [2]
    assert fb.count == 1


def test_renderer_requires_ubr():
    from types import SimpleNamespace

    from plyunit.rendering.renderer import Renderer

    with pytest.raises(RuntimeError, match="UBR wajib"):
        Renderer(canvas=SimpleNamespace())


def test_renderer_submit_and_flush_calls_submit_frame():
    from types import SimpleNamespace

    from plyunit.rendering.renderer import Renderer

    class FakeUbr:
        capacity = 64
        calls = 0

        def init(self, n):
            self.capacity = n

        def shutdown(self):
            pass

        def submit_frame(self, **kwargs):
            FakeUbr.calls += 1
            self.last = kwargs
            assert kwargs["n_sprites"] >= 1

    FakeUbr.calls = 0
    ubr = FakeUbr()
    r = Renderer(canvas=SimpleNamespace(), ubr=ubr, max_sprites=64)
    for name in ("ui", "debug"):
        p = r.get_pass(name)
        if p:
            p.enabled = False
    r.reset_frame()
    tex = SimpleNamespace(id=42, width=8, height=8)
    r.render_sprite(texture=tex, pos=(1.0, 2.0))
    r.render_batch(texture=tex, positions=[(0.0, 0.0), (1.0, 1.0)])
    assert r._frame_buffer.count == 3
    r.flush_all()
    assert FakeUbr.calls == 1
    assert ubr.last["n_sprites"] == 3


def test_renderer_defers_gpu_initialization_until_requested():
    from types import SimpleNamespace

    from plyunit.rendering.renderer import Renderer

    class FakeUbr:
        def __init__(self):
            self.init_calls = 0

        def init(self, n):
            _ = n
            self.init_calls += 1

        def shutdown(self):
            pass

    ubr = FakeUbr()
    renderer = Renderer(canvas=SimpleNamespace(), ubr=ubr)

    assert ubr.init_calls == 0
    renderer.init()
    renderer.init()
    assert ubr.init_calls == 1


def test_submit_tile_writes_frame_buffer_soa():
    """Tiles share the same FrameBuffer path as sprites (UBR)."""
    from types import SimpleNamespace

    from plyunit.rendering.renderer import Renderer

    class FakeUbr:
        capacity = 64

        def init(self, n):
            self.capacity = n

        def shutdown(self):
            pass

        def submit_frame(self, **kwargs):
            pass

    r = Renderer(canvas=SimpleNamespace(), ubr=FakeUbr(), max_sprites=64)
    r.reset_frame()
    tex = SimpleNamespace(id=7, width=32, height=32)
    r.render_sprite(
        texture=tex,
        dest=(10.0, 20.0, 16.0, 16.0),
        source=(0.0, 0.0, 16.0, 16.0),
        tint=(255, 128, 64, 200),
        rotation=15.0,
    )
    r.render_sprite(
        texture=tex,
        dest=(0.0, 0.0, 64.0, 64.0),
        source=(0.0, 0.0, 32.0, 32.0),
    )
    fb = r._frame_buffer
    assert fb.count == 2
    assert int(fb.tex_id[0]) == 7
    assert float(fb.pos_xy[0, 0]) == pytest.approx(10.0)
    assert float(fb.pos_xy[0, 1]) == pytest.approx(20.0)
    assert float(fb.size_wh[0, 0]) == pytest.approx(16.0)
    assert float(fb.size_wh[0, 1]) == pytest.approx(16.0)
    assert float(fb.rotation_deg[0]) == pytest.approx(15.0)
    assert list(fb.rgba[0]) == [255, 128, 64, 200]
    # source (0,0,16,16) on 32x32 → UV half
    assert float(fb.uv_rect[0, 2]) == pytest.approx(0.5)
    assert float(fb.uv_rect[0, 3]) == pytest.approx(0.5)
    assert int(fb.tex_id[1]) == 7
    assert float(fb.size_wh[1, 0]) == pytest.approx(64.0)



def test_submit_text_shaped_writes_frame_buffer():
    """Shaped text glyphs land in FrameBuffer like sprites (UBR)."""
    from types import SimpleNamespace

    from plyunit.assets.types import ShapedText
    from plyunit.rendering.renderer import Renderer

    class FakeUbr:
        capacity = 64

        def init(self, n):
            self.capacity = n

        def shutdown(self):
            pass

        def submit_frame(self, **kwargs):
            pass

    r = Renderer(canvas=SimpleNamespace(), ubr=FakeUbr(), max_sprites=64)
    r.reset_frame()
    shaped = ShapedText(
        offsets_xy=np.array([[0.0, 0.0], [8.0, 0.0]], dtype=np.float32),
        sizes_wh=np.array([[8.0, 12.0], [8.0, 12.0]], dtype=np.float32),
        uv_rects=np.array(
            [[0.0, 0.0, 0.25, 0.375], [0.25, 0.0, 0.5, 0.375]], dtype=np.float32
        ),
        tex_id=11,
        total_width=16.0,
        total_height=16.0,
    )
    r.render_shaped_text(
        shaped, pos=(100.0, 50.0), color=(255, 0, 0, 255), origin=(0.0, 0.0)
    )
    fb = r._frame_buffer
    assert fb.count == 2
    assert int(fb.tex_id[0]) == 11
    assert float(fb.pos_xy[0, 0]) == pytest.approx(100.0)
    assert float(fb.pos_xy[1, 0]) == pytest.approx(108.0)
    assert float(fb.pos_xy[0, 1]) == pytest.approx(50.0)
    assert list(fb.rgba[0]) == [255, 0, 0, 255]
    assert float(fb.size_wh[0, 0]) == pytest.approx(8.0)

    # empty shaped is no-op
    empty = ShapedText(
        offsets_xy=np.empty((0, 2), np.float32),
        sizes_wh=np.empty((0, 2), np.float32),
        uv_rects=np.empty((0, 4), np.float32),
        tex_id=11,
        total_width=0.0,
        total_height=16.0,
    )
    r.render_shaped_text(empty, pos=(0, 0))
    assert fb.count == 2
