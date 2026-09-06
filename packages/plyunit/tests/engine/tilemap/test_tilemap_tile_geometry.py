"""Tests for :mod:`plyunit.tilemap.tile_geometry`.

Rules: a 100x90 image on a 16x16 grid is not forced to 16x16, and its
anchor is the **bottom-left** corner of the cell (not the center / top-left).
"""

from __future__ import annotations

import pytest

from plyunit.tilemap.tile_geometry import (
    TILE_ANCHOR,
    source_size,
    tile_dest_rect,
    tile_is_oversized,
    tile_overhang,
)

TILE = 16


def test_anchor_is_bottom_left() -> None:
    assert TILE_ANCHOR == "bottom_left"


class TestNativeSize:
    def test_oversized_keeps_native_size(self) -> None:
        assert tile_dest_rect(0, 0, TILE, 100, 90)[2:] == (100.0, 90.0)

    def test_cell_sized_matches_legacy_rect(self) -> None:
        assert tile_dest_rect(3, 5, TILE, 16, 16) == (48.0, 80.0, 16.0, 16.0)

    def test_smaller_than_cell_keeps_native_size(self) -> None:
        assert tile_dest_rect(0, 0, TILE, 8, 8)[2:] == (8.0, 8.0)


class TestBottomLeftAnchor:
    def test_known_rect(self) -> None:
        assert tile_dest_rect(3, 5, TILE, 100, 90) == (48.0, 6.0, 100.0, 90.0)

    def test_bottom_edge_matches_cell_bottom(self) -> None:
        _, y, _, h = tile_dest_rect(0, 0, TILE, 100, 90)
        assert y + h == float(TILE)

    def test_left_edge_matches_cell_left(self) -> None:
        assert tile_dest_rect(3, 5, TILE, 100, 90)[0] == 3 * float(TILE)

    def test_not_top_left(self) -> None:
        assert tile_dest_rect(0, 5, TILE, 100, 90)[1] != 5 * float(TILE)

    def test_not_centered(self) -> None:
        x, y, w, h = tile_dest_rect(0, 0, TILE, 100, 90)
        assert (x + w / 2.0, y + h / 2.0) != (TILE / 2.0, TILE / 2.0)

    @pytest.mark.parametrize("height", [16, 32, 90, 128])
    def test_footing_stable_across_heights(self, height: int) -> None:
        _, y, _, h = tile_dest_rect(2, 9, TILE, 16, height)
        assert y + h == (9 + 1) * float(TILE)

    def test_negative_cell(self) -> None:
        _, y, _, h = tile_dest_rect(-2, -3, TILE, 100, 90)
        assert y + h == (-3 + 1) * float(TILE)


class TestOversizedDetection:
    @pytest.mark.parametrize(
        ("w", "h", "expected"),
        [
            (100, 90, True),
            (16, 16, False),
            (8, 8, False),
            (16, 90, True),
            (100, 16, True),
        ],
    )
    def test_detection(self, w: int, h: int, expected: bool) -> None:
        assert tile_is_oversized(TILE, w, h) is expected


class TestOverhang:
    def test_values(self) -> None:
        assert tile_overhang(TILE, 100, 90) == (84.0, 74.0)

    def test_never_negative(self) -> None:
        assert tile_overhang(TILE, 4, 4) == (0.0, 0.0)


class TestSourceSize:
    def test_negative_height_uses_absolute(self) -> None:
        assert source_size(TILE, 100, -90) == (100.0, 90.0)

    def test_zero_falls_back_to_tile_size(self) -> None:
        assert source_size(TILE, 0, 0) == (16.0, 16.0)

    def test_zero_tile_size_clamped(self) -> None:
        assert source_size(0, 0, 0) == (1.0, 1.0)
