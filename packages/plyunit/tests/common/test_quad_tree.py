from __future__ import annotations

from plyunit.utils.data_structures import QuadTree


def test_insert_split_and_spatial_queries() -> None:
    tree = QuadTree[object](0.0, 0.0, 100.0, 100.0, max_items=1, max_depth=3)
    northwest, southeast, spanning, outside = object(), object(), object(), object()

    assert tree.insert(northwest, 5.0, 5.0, 15.0, 15.0)
    assert tree.insert(southeast, 75.0, 75.0, 85.0, 85.0)
    assert tree.insert(spanning, 45.0, 45.0, 55.0, 55.0)
    assert not tree.insert(outside, 110.0, 110.0, 120.0, 120.0)

    assert len(tree) == tree.count == 3
    assert northwest in tree
    assert outside not in tree
    assert set(tree.query(0.0, 0.0, 100.0, 100.0)) == {
        northwest,
        southeast,
        spanning,
    }
    assert tree.query(101.0, 101.0, 105.0, 105.0) == []
    assert tree.query_point(50.0, 50.0) == [spanning]
    assert tree.query_point(-1.0, -1.0) == []


def test_remove_reinsert_rebuild_and_clear() -> None:
    tree = QuadTree[object](0.0, 0.0, 100.0, 100.0, max_items=1, max_depth=3)
    first, second, spanning, missing = object(), object(), object(), object()
    tree.insert(first, 5.0, 5.0, 15.0, 15.0)
    tree.insert(second, 75.0, 75.0, 85.0, 85.0)
    tree.insert(spanning, 45.0, 45.0, 55.0, 55.0)

    assert tree.remove(second)
    assert not tree.remove(missing)
    assert second not in tree

    assert tree.insert(first, 70.0, 5.0, 80.0, 15.0)
    assert tree.query_point(10.0, 10.0) == []
    assert tree.query_point(75.0, 10.0) == [first]

    tree.rebuild()
    assert set(tree.query(0.0, 0.0, 100.0, 100.0)) == {first, spanning}

    tree.clear()
    assert len(tree) == 0
    assert tree.query(0.0, 0.0, 100.0, 100.0) == []
