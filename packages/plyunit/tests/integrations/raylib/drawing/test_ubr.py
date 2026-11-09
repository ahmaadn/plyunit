"""Native batch tests using the canonical raylib renderer and concrete handles."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import plyunit.backends.integrations.raylib.renderer.ubr as ubr_module
from plyunit.backends.integrations.raylib.handler import RenderTexture, Texture2D
from plyunit.backends.integrations.raylib.renderer import Canvas2D, canvas
from plyunit.backends.ports.renderer import ICanvas2D, IUnifiedBufferBatch


def _frame_arrays(size: int = 3) -> dict[str, np.ndarray]:
    """Build intentionally non-native array dtypes for conversion tests.

    Args:
        size: Number of sprite rows to allocate.

    Returns:
        Keyword arrays accepted by ``submit_frame``.
    """
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


def _live_batch(
    monkeypatch: pytest.MonkeyPatch, capacity: int = 8
) -> tuple[ubr_module.UnifiedBufferBatch, MagicMock]:
    """Set up a batch around a fake initialized native extension.

    Args:
        monkeypatch: Pytest patch manager.
        capacity: Batch capacity.

    Returns:
        The ready batch and native extension mock.
    """
    batch = ubr_module.UnifiedBufferBatch(max_sprites=capacity)
    ext = MagicMock(spec=ubr_module.NativeBatchModule)
    batch._ext = ext
    batch._shader = SimpleNamespace()
    batch._capacity = capacity
    monkeypatch.setattr(ubr_module, "_prepare_shader", MagicMock())
    monkeypatch.setattr(ubr_module, "rl", SimpleNamespace(rlDisableShader=MagicMock()))
    return batch, ext


def test_canvas_factory_returns_module_port() -> None:
    """The canonical canvas factory is consistently callable at runtime."""
    result = Canvas2D()
    assert result is canvas
    assert isinstance(result, ICanvas2D)


def test_batch_satisfies_canonical_port() -> None:
    """The batch implements the single canonical batch protocol."""
    assert isinstance(ubr_module.UnifiedBufferBatch(), IUnifiedBufferBatch)


def test_texture_id_uses_native_name_not_asset_id() -> None:
    """Logical asset and region IDs never leak into native texture-run arrays."""
    batch = ubr_module.UnifiedBufferBatch()
    raw = SimpleNamespace(id=42, width=32, height=16, format=7)
    root = Texture2D.from_raw(raw, texture_id="sprites")
    region = root.derive(
        texture_id="hero", parent_id="sprites", source_rect=(1.0, 2.0, 8.0, 8.0)
    )
    assert root.texture_id == "sprites"
    assert region.texture_id == "hero"
    assert batch.texture_id(root) == 42
    assert batch.texture_id(region) == 42
    assert batch.capacity == 0


def test_texture_id_handles_render_target_attachment() -> None:
    """An offscreen render target resolves its color texture, not its framebuffer."""
    batch = ubr_module.UnifiedBufferBatch()
    raw = SimpleNamespace(
        id=100, texture=SimpleNamespace(id=9, width=64, height=64, format=7)
    )
    target = RenderTexture(raw)
    assert batch.texture_id(target) == 9
    assert batch.texture_id(target.texture) == 9


@pytest.mark.parametrize(
    "raw",
    [
        None,
        4,
        SimpleNamespace(id=3),
        SimpleNamespace(raw_texture=SimpleNamespace(id=3)),
    ],
)
def test_texture_id_rejects_raw_or_foreign_handles(raw: object) -> None:
    """The raylib batch accepts concrete handles rather than structural raw data."""
    batch = ubr_module.UnifiedBufferBatch()
    with pytest.raises(TypeError, match="raylib"):
        batch.texture_id(raw)


def test_submit_frame_requires_initialization() -> None:
    """Native submission remains fail-fast with no pure-Python draw fallback."""
    batch = ubr_module.UnifiedBufferBatch(max_sprites=8)
    with pytest.raises(RuntimeError, match="not initialized"):
        batch.submit_frame(**_frame_arrays(), n_sprites=3, n_runs=2)


def test_submit_frame_converts_and_limits_native_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each native array has the requested row count, dtype, and contiguity."""
    batch, ext = _live_batch(monkeypatch)
    batch.submit_frame(**_frame_arrays(), n_sprites=2, n_runs=1)
    args = ext.ubr_submit_frame.call_args.args
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
    assert all(array.flags.c_contiguous for array in args[:9])
    assert args[-2:] == (2, 1)
    ubr_module.rl.rlDisableShader.assert_called_once()


def test_submit_frame_empty_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty initialized frame makes no shader or native draw calls."""
    batch, ext = _live_batch(monkeypatch)
    batch.submit_frame(**_frame_arrays(0), n_sprites=0, n_runs=0)
    ext.ubr_submit_frame.assert_not_called()
    ubr_module._prepare_shader.assert_not_called()


@pytest.mark.parametrize("n_sprites,n_runs", [(-1, 0), (9, 2), (2, 0), (2, 3), (4, 2)])
def test_submit_rejects_invalid_counts(
    monkeypatch: pytest.MonkeyPatch, n_sprites: int, n_runs: int
) -> None:
    """Invalid counts cannot make the C extension read beyond supplied arrays."""
    batch, ext = _live_batch(monkeypatch)
    with pytest.raises(ValueError):
        batch.submit_frame(**_frame_arrays(), n_sprites=n_sprites, n_runs=n_runs)
    ext.ubr_submit_frame.assert_not_called()
    ubr_module._prepare_shader.assert_not_called()


def test_submit_rejects_short_texture_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every texture-run array must hold the declared number of runs."""
    batch, ext = _live_batch(monkeypatch)
    arrays = _frame_arrays()
    arrays["run_tex_ids"] = arrays["run_tex_ids"][:1]
    with pytest.raises(ValueError, match="texture-run"):
        batch.submit_frame(**arrays, n_sprites=3, n_runs=2)
    ext.ubr_submit_frame.assert_not_called()


def test_shader_is_disabled_after_native_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native submission errors still restore shader state."""
    batch, ext = _live_batch(monkeypatch)
    ext.ubr_submit_frame.side_effect = RuntimeError("draw failed")
    with pytest.raises(RuntimeError, match="draw failed"):
        batch.submit_frame(**_frame_arrays(), n_sprites=3, n_runs=2)
    ubr_module.rl.rlDisableShader.assert_called_once()


def test_shader_is_disabled_after_prepare_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partially bound shader is disabled when uniform setup raises."""
    batch, _ = _live_batch(monkeypatch)
    ubr_module._prepare_shader.side_effect = RuntimeError("uniform failed")
    with pytest.raises(RuntimeError, match="uniform failed"):
        batch.submit_frame(**_frame_arrays(), n_sprites=3, n_runs=2)
    ubr_module.rl.rlDisableShader.assert_called_once()


def test_failed_init_releases_native_buffers(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unsuccessful native initialization releases partial allocations."""
    ext = MagicMock(spec=ubr_module.NativeBatchModule)
    ext.ubr_is_ready.return_value = False
    shader = SimpleNamespace(sampler_loc=2)
    monkeypatch.setattr(ubr_module, "_load_native", lambda: ext)
    monkeypatch.setattr(ubr_module, "_resolve_shader_state", lambda: shader)
    monkeypatch.setattr(ubr_module, "_bind_dispatch", lambda *args, **kwargs: None)
    batch = ubr_module.UnifiedBufferBatch(max_sprites=8)
    with pytest.raises(RuntimeError, match="not ready"):
        batch.init()
    ext.ubr_shutdown.assert_called_once()
    assert batch.capacity == 0
    assert batch._ext is None


def test_live_batch_capacity_cannot_be_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated init is idempotent only when the existing capacity agrees."""
    batch, ext = _live_batch(monkeypatch)
    batch.init(8)
    with pytest.raises(ValueError, match="capacity"):
        batch.init(16)
    assert batch.capacity == 8
    ext.ubr_init.assert_not_called()


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_capacity_is_rejected(capacity: object) -> None:
    """Capacity must be a positive integer before any native work occurs."""
    with pytest.raises(ValueError, match="positive integer"):
        ubr_module.UnifiedBufferBatch(capacity)


def test_shutdown_and_singleton_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Singleton reset shuts down the actual batch at most once."""
    batch, ext = _live_batch(monkeypatch, capacity=12)
    monkeypatch.setattr(ubr_module, "_ubr", batch)
    assert ubr_module.get_unified_buffer_batch() is batch
    ubr_module.reset_unified_buffer_batch()
    batch.shutdown()
    ext.ubr_shutdown.assert_called_once()
    assert batch.capacity == 0
    assert ubr_module._ubr is None
