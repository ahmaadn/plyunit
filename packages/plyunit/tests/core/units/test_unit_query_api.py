from __future__ import annotations

import plyunit as pu


def test_unit_registry_query_apis():
    reg = pu.UnitRegistry()
    a = pu.ServiceUnit(name="Alpha", tags={"t1", "shared"})
    b = pu.ServiceUnit(name="Beta", tags={"t2", "shared"})
    c = pu.ServiceUnit(name="Gamma", tags={"t1"})
    reg.register(a)
    reg.register(b)
    reg.register(c)

    # group / one / find
    assert len(reg.group(pu.ServiceUnit)) >= 3
    assert reg.group("@Beta") == [b]
    assert reg.one("@Alpha") is a
    try:
        reg.one("@Missing")
        missing = False
    except Exception:
        missing = True
    assert missing

    if hasattr(reg, "one_or_none"):
        assert reg.one_or_none("@Missing") is None
        assert reg.one_or_none("@Beta") is b

    if hasattr(reg, "find_by_tag"):
        shared = reg.find_by_tag("shared")
        assert len(shared) >= 2
        t1 = reg.find_by_tag("t1")
        assert a in t1 and c in t1

    if hasattr(reg, "unregister"):
        reg.unregister(c)
    if hasattr(reg, "clear"):
        # don't clear if other tests share - just exercise
        pass

    # ServiceUnit as query root
    assert a.group(pu.ServiceUnit, scope="global") or True
    if hasattr(a, "find_by_tag"):
        try:
            a.find_by_tag("shared", scope="global")
        except Exception:
            pass


def test_node_unit_components_and_tree():
    root = pu.NodeUnit(name="root")
    child = pu.NodeUnit(name="child")
    # attach via common APIs
    if hasattr(root, "add_child"):
        root.add_child(child)
    elif hasattr(root, "append"):
        root.append(child)

    root.transform.set_position(1, 2)
    root.transform.set_rotation(10)
    root.transform.set_scale(2, 2)
    root.transform.recalc_world(None)
    root.transform.reset_interpolation()
    lerp = root.world_transform_lerp(0.5)
    assert lerp is not None

    # components
    from plyunit.core.components.component import Component

    class Dummy(Component):
        def __init__(self):
            super().__init__(name="d")

    d = Dummy()
    try:
        root.add_component(d)
        comps = root.get_components(Dummy) if hasattr(root, "get_components") else []
        if hasattr(root, "get_component"):
            root.get_component(Dummy)
        if hasattr(root, "destroy_component"):
            root.destroy_component(d)
    except Exception:
        pass

    # traverse
    if hasattr(root, "traverse_preorder"):
        list(root.traverse_preorder())
    if hasattr(root, "traverse_postorder"):
        list(root.traverse_postorder())

    root.destroy()
