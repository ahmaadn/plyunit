from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations as integrations_mod
from plyunit.core.app import App, AppConfig, AudioConfig, ImGuiConfig, PhysicsConfig
from plyunit.core.units.service_unit import ServiceUnit


def _patch_rendering_stack(monkeypatch: pytest.MonkeyPatch, *, fake_window=None, fake_canvas=None):
    """Stub window/canvas/batching factories used by init."""
    if fake_window is None:
        fake_window = SimpleNamespace(
            init_window=lambda *a: None,
            set_target_fps=lambda *a: None,
        )
    if fake_canvas is None:
        fake_canvas = object()

    fake_batching = SimpleNamespace(
        capacity=16384,
        init=lambda *a, **k: None,
        shutdown=lambda: None,
        submit_frame=lambda **k: None,
    )

    monkeypatch.setattr(
        "plyunit.backends.integrations.raylib.core.get_window",
        lambda: fake_window,
    )
    monkeypatch.setattr(
        "plyunit.backends.integrations.raylib.drawing.get_canvas",
        lambda: fake_canvas,
    )
    monkeypatch.setattr(
        "plyunit.backends.integrations.raylib.drawing.get_batching_backend",
        lambda: fake_batching,
    )
    return fake_window, fake_canvas


def test_init_default(monkeypatch: pytest.MonkeyPatch):
    fake_window, fake_canvas = _patch_rendering_stack(monkeypatch)
    fake_renderer = SimpleNamespace()
    fake_scene = SimpleNamespace()
    fake_assets = SimpleNamespace()
    fake_anims = SimpleNamespace()

    monkeypatch.setattr(
        "plyunit.rendering.renderer.Renderer",
        lambda canvas, **kwargs: fake_renderer,
    )
    monkeypatch.setattr(
        "plyunit.services.scene_manager.SceneManager", lambda: fake_scene
    )
    monkeypatch.setattr("plyunit.assets.assets.Assets", lambda: fake_assets)
    monkeypatch.setattr("plyunit.assets.animations.Animations", lambda: fake_anims)

    class MiniApp(App):
        # pyrefly: ignore [bad-override]
        def init(self, cfg):
            self.config = cfg
            self.running = False

    app = MiniApp()
    out = integrations_mod.init(
        app, AppConfig(title="t", window_width=100, window_height=100)
    )
    assert out is app
    assert app.window is fake_window
    assert app.canvas is fake_canvas
    assert app.renderer is fake_renderer


def test_bootstrap_physics_and_imgui_flags(monkeypatch: pytest.MonkeyPatch):
    _patch_rendering_stack(monkeypatch)

    monkeypatch.setattr(
        "plyunit.rendering.renderer.Renderer",
        lambda canvas, **kwargs: object(),
    )
    monkeypatch.setattr("plyunit.services.scene_manager.SceneManager", lambda: object())
    monkeypatch.setattr("plyunit.assets.assets.Assets", lambda: object())
    monkeypatch.setattr("plyunit.assets.animations.Animations", lambda: object())
    # Patch factories on the modules bootstrap imports (lazy facades).
    import sys
    from types import ModuleType

    class FakePhysics(ServiceUnit):
        def __init__(self, cfg) -> None:
            super().__init__(name="phys")
            self.cfg = cfg

    fake_phys = ModuleType("plyunit.backends.physics")
    fake_phys.build_physics_service = FakePhysics  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "plyunit.backends.physics", fake_phys)

    class FakeImGui(ServiceUnit):
        def __init__(self, cfg) -> None:
            super().__init__(name="imgui")
            self.cfg = cfg

    fake_imgui = ModuleType("plyunit.backends.imgui")
    fake_imgui.build_imgui_service = FakeImGui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "plyunit.backends.imgui", fake_imgui)

    class MiniApp(App):
        # pyrefly: ignore [bad-override]
        def init(self, cfg):
            self.config = cfg

    fake_audio = ModuleType("plyunit.audio.service")

    class FakeAudio(ServiceUnit):
        @classmethod
        def from_config(cls, cfg):
            service = cls(name="Audio")
            service.cfg = cfg
            return service

        def __init__(self, name="Audio") -> None:
            super().__init__(name=name)

    fake_audio.Audio = FakeAudio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "plyunit.audio.service", fake_audio)

    app = MiniApp()
    integrations_mod.init(
        app,
        AppConfig(
            title="t",
            window_width=64,
            window_height=64,
            physics=PhysicsConfig(enabled=True),
            imgui=ImGuiConfig(enabled=True),
            audio=AudioConfig(enabled=True),
        ),
    )
    assert app.one_or_none("phys", scope="global") is not None
    assert app.one_or_none("imgui", scope="global") is not None
    assert app.one_or_none("@Audio", scope="global") is not None
