from plyunit.audio.spatial import compute_spatial


def test_spatial_full_volume_inside_min_distance() -> None:
    vol, pan = compute_spatial((0.0, 0.0), (10.0, 0.0), 50.0, 800.0, 1.0)
    assert vol == 1.0
    assert 0.5 < pan <= 1.0


def test_spatial_silent_beyond_max_distance() -> None:
    vol, _ = compute_spatial((0.0, 0.0), (1000.0, 0.0), 50.0, 800.0, 1.0)
    assert vol == 0.0


def test_spatial_midpoint_linear() -> None:
    # dist = 425, min=50, max=800 → t = 375/750 = 0.5 → vol = 0.5
    vol, pan = compute_spatial((0.0, 0.0), (425.0, 0.0), 50.0, 800.0, 1.0)
    assert abs(vol - 0.5) < 1e-6
    assert abs(pan - (0.5 + 0.5 * (425.0 / 800.0))) < 1e-6


def test_spatial_pan_left() -> None:
    vol, pan = compute_spatial((0.0, 0.0), (-400.0, 0.0), 0.0, 800.0, 1.0)
    assert vol > 0.0
    assert pan < 0.5


def test_spatial_rolloff_faster() -> None:
    vol_lin, _ = compute_spatial((0.0, 0.0), (425.0, 0.0), 50.0, 800.0, 1.0)
    vol_fast, _ = compute_spatial((0.0, 0.0), (425.0, 0.0), 50.0, 800.0, 2.0)
    assert vol_fast < vol_lin
