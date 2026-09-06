from __future__ import annotations

import plyunit as pu


def test_component_defaults_and_state_properties():
    component = pu.Component(name="Health")

    assert component.enabled is True
    assert component.unit is None
    assert component._name == "Health"
    assert component.is_started is False
    assert component.is_destroyed is False


def test_component_lifecycle_methods_are_callable_noop():
    component = pu.Component(name="Health")

    component.on_attach()
    component.on_start()
    component.update(0.016)
    component.render_submit(renderer={"frame": 1})
    component.on_destroy()

    assert component.is_started is False
    assert component.is_destroyed is False
