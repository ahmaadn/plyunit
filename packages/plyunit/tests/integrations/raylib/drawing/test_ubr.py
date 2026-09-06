from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import plyunit.backends.integrations.raylib.drawing.ubr as ubr_module


def _frame_arrays(size: int = 3) -> dict[str, np.ndarray]:
    return {
        "pos_xy": np.arange(size * 2, dtype=np.float64).reshape(size, 2),
        "size_wh": np.ones((size, 2), dtype=np.float64),
        "origin_xy": np.zeros((size, 2), dtype=np.float64),
        "rotation_deg": np.zeros(size, dtype=np.float64),
        "rgba": np.full((size, 4), 255, dtype=np.int16),
        "uv_rect": np.ones((size, 4), dtype=np.float64),
        "run_starts": np.array([0, 2], dtype=np.int64),
        "run_counts": np.array([2, 1], dtype=np.int64),
        "run_tex_ids": np.array([4, 5], dtype=np.int64),
    }


def test_submit_frame_requires_initialization() -> None:
    batch = ubr_module.UnifiedBufferBatch(max_sprites=8)
    with pytest.raises(RuntimeError, match="not initialized"):
        batch.submit_frame(**_frame_arrays(), n_sprites=3, n_runs=2)


def test_submit_frame_converts_and_limits_native_arrays(monkeypatch) -> None:
    submitted: list[tuple] = []
    disabled: list[bool] = []
    ext = SimpleNamespace(
        ubr_submit_frame=lambda *args: submitted.append(args),
    )
    raylib = SimpleNamespace(rlDisableShader=lambda: disabled.append(True))
    monkeypatch.setattr(ubr_module, "_prepare_fallback", lambda: raylib)

    batch = ubr_module.UnifiedBufferBatch(max_sprites=8)
    batch._ready = True
    batch._ext = ext
    batch.submit_frame(**_frame_arrays(), n_sprites=2, n_runs=1)

    args = submitted[0]
    assert [array.shape[0] for array in args[:9]] == [2, 2, 2, 2, 2, 2, 1, 1, 1]
    assert [array.dtype for array in args[:9]] == [
        np.dtype(np.float32),
        np.dtype(np.float32),
        np.dtype(np.float32),
        np.dtype(np.float32),
        np.dtype(np.uint8),
        np.dtype(np.float32),
        np.dtype(np.int32),
        np.dtype(np.int32),
        np.dtype(np.uint32),
    ]
    assert args[-2:] == (2, 1)
    assert disabled == [True]


def test_submit_frame_empty_is_noop(monkeypatch) -> None:
    batch = ubr_module.UnifiedBufferBatch(max_sprites=8)
    batch._ready = True
    batch._ext = SimpleNamespace(
        ubr_submit_frame=lambda *args: pytest.fail("native submit should not run")
    )
    monkeypatch.setattr(
        ubr_module,
        "_prepare_fallback",
        lambda: pytest.fail("shader preparation should not run"),
    )

    batch.submit_frame(**_frame_arrays(0), n_sprites=0, n_runs=0)


def test_shutdown_and_singleton_reset(monkeypatch) -> None:
    shutdowns: list[bool] = []
    batch = ubr_module.UnifiedBufferBatch(max_sprites=12)
    batch._ready = True
    batch._capacity = 12
    batch._ext = SimpleNamespace(ubr_shutdown=lambda: shutdowns.append(True))
    monkeypatch.setattr(ubr_module, "_ubr", batch)

    assert ubr_module.get_unified_buffer_batch() is batch
    ubr_module.reset_unified_buffer_batch()

    assert shutdowns == [True]
    assert batch.capacity == 0
    assert ubr_module._ubr is None
