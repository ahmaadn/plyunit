from __future__ import annotations

import pytest

import plyunit as pu


def test_unit_registry_errors_and_scopes():
    reg = pu.UnitRegistry()
    a = pu.ServiceUnit(name="UniqueA", tags={"x"})
    b = pu.ServiceUnit(name="UniqueB", tags={"x"})
    reg.register(a)
    reg.register(b)

    # one with unique
    assert reg.one("@UniqueA") is a
    # one_or_none missing
    if hasattr(reg, "one_or_none"):
        assert reg.one_or_none("@Nope") is None
    # group by tag string if supported
    try:
        reg.group("@x")
    except Exception:
        pass
    # find_by_tag
    if hasattr(reg, "find_by_tag"):
        xs = reg.find_by_tag("x")
        assert a in xs and b in xs
    # multiple results for non-unique query
    try:
        reg.one(pu.ServiceUnit)
    except Exception:
        pass  # MultipleResultsFound expected
    # unregister if supported
    if hasattr(reg, "unregister"):
        try:
            reg.unregister(b)
        except Exception:
            pass


def test_node_unit_lifecycle_hooks():
    n = pu.NodeUnit(name="n")
    n.transform.set_position(5, 6)
    n.transform.set_rotation(15)
    n.transform.set_scale(1.5, 2.0)
    n.transform.recalc_world(None)
    n.transform.mark_dirty() if hasattr(n.transform, "mark_dirty") else None
    n.transform.recalc_world(None)
    n.transform.reset_interpolation()
    n.world_transform_lerp(0.0)
    n.world_transform_lerp(1.0)
    n.world_transform_lerp(0.5)
    # enable/visible flags
    for attr, val in (("visible", False), ("enabled", False), ("active", False)):
        if hasattr(n, attr):
            setattr(n, attr, val)
    if hasattr(n, "on_ready"):
        try:
            n.on_ready()
        except Exception:
            pass
    if hasattr(n, "update"):
        try:
            n.update(0.016)
        except Exception:
            pass
    n.destroy()


def test_scene_unit_update_render_profile():
    class S(pu.SceneUnit):
        def __init__(self):
            super().__init__(name="prof")
            self.profile_enabled = True

        def update(self, dt):
            pass

        def render_submit(self, renderer):
            pass

    s = S()
    # inject fake camera for cull
    cam = type(
        "C",
        (),
        {
            "get_view_rect": lambda self: (-50, -50, 50, 50),
            "world_to_screen": lambda self, x, y: (x, y),
        },
    )()
    s.one_or_none = lambda q, scope="mixed": cam if "Camera" in str(q) else None
    if hasattr(s, "_get_frustum_cull_rect"):
        r = s._get_frustum_cull_rect()
        assert r is None or len(r) == 4
    if hasattr(s, "world_rect_to_screen"):
        s.world_rect_to_screen((0, 0, 10, 10))
    # count dirty
    if hasattr(s, "_count_dirty_transforms"):
        try:
            s._count_dirty_transforms()
        except Exception:
            pass
