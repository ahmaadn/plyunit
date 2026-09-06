from __future__ import annotations

from plyunit.utils.geometry import (
    aabb_contains,
    aabb_from_center,
    aabb_intersects,
    aabb_intersection,
    aabb_union,
    expand_aabb,
)


def test_aabb_intersects_and_contains():
    a = (0.0, 0.0, 10.0, 10.0)
    b = (5.0, 5.0, 10.0, 10.0)
    c = (20.0, 20.0, 5.0, 5.0)
    assert aabb_intersects(a, b) is True
    assert aabb_intersects(a, c) is False
    assert aabb_contains(a, (1.0, 1.0, 2.0, 2.0)) is True
    assert aabb_contains(a, b) is False


def test_aabb_ops():
    a = (0.0, 0.0, 10.0, 10.0)
    b = (5.0, 5.0, 10.0, 10.0)
    inter = aabb_intersection(a, b)
    assert inter[2] > 0 and inter[3] > 0
    none = aabb_intersection(a, (50.0, 50.0, 1.0, 1.0))
    assert none[2] == 0.0 and none[3] == 0.0
    uni = aabb_union(a, b)
    assert uni[2] >= 10.0
    ctr = aabb_from_center(0.0, 0.0, 5.0, 5.0)
    assert ctr == (-5.0, -5.0, 10.0, 10.0)
    exp = expand_aabb(a, 2.0)
    assert exp == (-2.0, -2.0, 14.0, 14.0)
