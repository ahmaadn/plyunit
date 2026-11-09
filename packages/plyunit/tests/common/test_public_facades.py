"""Regression tests for the current lazy facade and backend-neutral imports."""

from __future__ import annotations

import importlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import plyunit
import plyunit.backends.imgui as imgui_facade
import plyunit.backends.integrations as integrations
import plyunit.backends.ports as ports


def test_ports_export_handle_and_service_contracts() -> None:
    from plyunit.backends.ports.assets import IAssets
    from plyunit.backends.ports.handler import Texture2DHandle
    from plyunit.backends.ports.imgui import DrawCallback, ImGuiPort
    from plyunit.backends.ports.text import IText

    assert ports.IAssets is IAssets
    assert ports.Texture2DHandle is Texture2DHandle
    assert ports.DrawCallback is DrawCallback
    assert ports.ImGuiPort is ImGuiPort
    assert ports.IText is IText
    assert plyunit.ports is ports


def test_services_resolve_to_selected_backend_implementations() -> None:
    from plyunit.backends.integrations import raylib

    for name in ("Assets", "Audio", "Camera2D", "Text", "Shaders", "Input", "Mouse"):
        assert getattr(plyunit, name) is getattr(integrations, name)
        assert getattr(integrations, name) is getattr(raylib, name)


def test_imgui_facade_resolves_and_caches_selected_integration(monkeypatch) -> None:
    from plyunit.backends import _selector

    monkeypatch.setattr(_selector, "BACKEND", "raylib")
    selected = object()
    backend = SimpleNamespace(ImGui=selected)
    load = Mock(return_value=backend)
    monkeypatch.delitem(vars(imgui_facade), "ImGui", raising=False)
    monkeypatch.setattr(imgui_facade, "_active_backend", None)
    monkeypatch.setattr(imgui_facade, "import_module", load)
    try:
        assert imgui_facade.__all__ == ("ImGui",)
        assert "ImGui" in dir(imgui_facade)
        load.assert_not_called()
        assert imgui_facade.ImGui is selected
        assert vars(imgui_facade)["ImGui"] is selected
        assert imgui_facade._get_active_backend() is backend
        backend.ImGui = object()
        assert imgui_facade.ImGui is selected
        namespace = {}
        exec("from plyunit.backends.imgui import *", namespace)
        assert namespace["ImGui"] is selected
        load.assert_called_once_with("plyunit.backends.imgui.raylib_integration")
    finally:
        vars(imgui_facade).pop("ImGui", None)


def test_imgui_root_export_resolves_to_selected_integration() -> None:
    pytest.importorskip("imgui_bundle")
    pytest.importorskip("OpenGL")
    from plyunit.backends.imgui.raylib_integration import ImGui

    assert imgui_facade.ImGui is ImGui
    assert plyunit.ImGui is ImGui


@pytest.mark.parametrize("facade", [plyunit, imgui_facade])
@pytest.mark.parametrize(
    "name", ["ImGuiBackend", "build_imgui_service", "RemovedPlyunitApi", "__missing__"]
)
def test_unknown_imgui_exports_do_not_load_backend(monkeypatch, facade, name) -> None:
    def unexpected_lookup():
        raise AssertionError("unknown ImGui names must not load a backend")

    monkeypatch.setattr(imgui_facade, "_get_active_backend", unexpected_lookup)
    assert name not in facade.__all__
    assert name not in dir(facade)
    with pytest.raises(AttributeError, match=name):
        getattr(facade, name)


@pytest.mark.parametrize("dependency", ["imgui_bundle", "OpenGL.GL"])
def test_imgui_facade_preserves_dependency_import_error(
    monkeypatch, dependency
) -> None:
    error = ModuleNotFoundError(f"No module named {dependency!r}", name=dependency)
    monkeypatch.delitem(vars(imgui_facade), "ImGui", raising=False)
    monkeypatch.setattr(imgui_facade, "_active_backend", None)
    monkeypatch.setattr(imgui_facade, "import_module", Mock(side_effect=error))

    with pytest.raises(ModuleNotFoundError) as caught:
        getattr(imgui_facade, "ImGui")

    assert caught.value is error
    assert "ImGui" not in vars(imgui_facade)
    assert imgui_facade._active_backend is None


def test_unknown_audio_service_name_does_not_resolve_backend(monkeypatch) -> None:
    import plyunit.services.audio as audio

    def unexpected_lookup(name):
        raise AssertionError("unknown audio names must not load a backend")

    monkeypatch.setattr(plyunit, "__getattr__", unexpected_lookup)
    with pytest.raises(AttributeError, match="RemovedPlyunitApi"):
        getattr(audio, "RemovedPlyunitApi")


@pytest.mark.parametrize("name", ["Assets", "Image", "ImageProcessor"])
def test_assets_service_facade_resolves_and_caches_exports(monkeypatch, name) -> None:
    import plyunit.services.assets as assets

    selected = object()
    monkeypatch.setattr(integrations, name, selected)
    monkeypatch.delitem(vars(assets), name, raising=False)
    try:
        assert getattr(assets, name) is selected
        assert vars(assets)[name] is selected
        assert name in assets.__all__
        monkeypatch.setattr(integrations, name, object())
        assert getattr(assets, name) is selected
    finally:
        vars(assets).pop(name, None)


def test_unknown_assets_service_name_does_not_resolve_backend(monkeypatch) -> None:
    import plyunit.services.assets as assets

    def unexpected_lookup(name):
        raise AssertionError("unknown assets names must not load a backend")

    monkeypatch.setattr(plyunit, "__getattr__", unexpected_lookup)
    with pytest.raises(AttributeError, match="RemovedPlyunitApi"):
        getattr(assets, "RemovedPlyunitApi")


def test_shared_exports_do_not_point_to_backend_implementations() -> None:
    from plyunit._enums import ShaderUniform, TextureFilter
    from plyunit.backends.ports.handler import ShaderHandle
    from plyunit.backends.ports.text import TemplateText
    from plyunit.services.animations import Animations
    from plyunit.services.spatial_index import SpatialIndex

    assert plyunit.ShaderHandle is ShaderHandle
    assert plyunit.TemplateText is TemplateText
    assert plyunit.Animations is Animations
    assert plyunit.SpatialIndex is SpatialIndex
    assert plyunit.ShaderUniform is ShaderUniform
    assert plyunit.TextureFilter is TextureFilter


def test_concrete_handles_belong_to_selected_backend() -> None:
    from plyunit.backends.integrations.raylib import handler
    from plyunit.backends.integrations.raylib.renderer import (
        Canvas2D,
        UnifiedBufferBatch,
        canvas,
    )

    for name in ("Image", "Texture2D", "RenderTexture", "Shader", "Font"):
        assert getattr(integrations, name) is getattr(handler, name)
    assert plyunit.Canvas2D is Canvas2D
    assert Canvas2D() is canvas
    assert plyunit.UnifiedBufferBatch is UnifiedBufferBatch


@pytest.mark.parametrize("facade", [plyunit, integrations])
@pytest.mark.parametrize(
    "name",
    ["AssetsLoader", "ShaderLoader", "AudioBackend", "Canvas", "get_assets_loader"],
)
def test_removed_api_is_not_reintroduced(facade, name: str) -> None:
    with pytest.raises(AttributeError):
        getattr(facade, name)


@pytest.mark.parametrize(
    "module_name",
    [
        "plyunit.assets",
        "plyunit.audio",
        "plyunit.backends.interfaces",
        "plyunit.backends.imgui.raylib",
        "plyunit.backends.integrations.raylib.drawing",
        "plyunit.backends.integrations.raylib.core",
    ],
)
def test_removed_packages_have_no_compatibility_shims(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_unknown_facade_names_fail_without_backend_lookup(monkeypatch) -> None:
    def unexpected_lookup():
        raise AssertionError("unknown names must not load a backend")

    monkeypatch.setattr(integrations, "_get_active_integration", unexpected_lookup)
    with pytest.raises(AttributeError):
        getattr(integrations, "RemovedPlyunitApi")


def test_core_services_and_ports_import_without_optional_backends() -> None:
    code = """
import importlib.abc
import sys

class BlockBackends(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'raylib', 'pyray', 'pymunk', 'imgui_bundle', 'OpenGL'}:
            raise AssertionError(f'optional backend imported: {fullname}')
        return None

sys.meta_path.insert(0, BlockBackends())
import plyunit
from plyunit import App, Animations, ShaderHandle, SpatialIndex, TemplateText, ports
import plyunit.backends.imgui as imgui_facade
from plyunit.backends.ports.imgui import DrawCallback, ImGuiPort
assert ports.DrawCallback is DrawCallback
assert ports.ImGuiPort is ImGuiPort
assert imgui_facade.__all__ == ('ImGui',)
assert 'ImGui' in dir(imgui_facade)
assert not any(name.startswith('plyunit.backends.imgui.') for name in sys.modules)
import plyunit.core.components.builtin
import plyunit.rendering
import plyunit.services.input
import plyunit.services.assets.schemas
import plyunit.services.audio.spatial
import plyunit.services.text
import plyunit.services.shaders
import plyunit.tilemap
assert not any(name.startswith('plyunit.backends.integrations.') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stdout + result.stderr
