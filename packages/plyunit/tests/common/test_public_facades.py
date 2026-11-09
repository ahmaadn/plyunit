"""Regression tests for the current lazy facade and backend-neutral imports."""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

import plyunit
import plyunit.backends.integrations as integrations
import plyunit.backends.ports as ports


def test_ports_export_handle_and_service_contracts() -> None:
    from plyunit.backends.ports.assets import IAssets
    from plyunit.backends.ports.handler import Texture2DHandle
    from plyunit.backends.ports.text import IText

    assert ports.IAssets is IAssets
    assert ports.Texture2DHandle is Texture2DHandle
    assert ports.IText is IText
    assert plyunit.ports is ports


def test_services_resolve_to_selected_backend_implementations() -> None:
    from plyunit.backends.integrations import raylib

    for name in ("Assets", "Audio", "Camera2D", "Text", "Shaders", "Input", "Mouse"):
        assert getattr(plyunit, name) is getattr(integrations, name)
        assert getattr(integrations, name) is getattr(raylib, name)


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
        if fullname.split('.')[0] in {'raylib', 'pyray', 'pymunk', 'imgui_bundle'}:
            raise AssertionError(f'optional backend imported: {fullname}')
        return None

sys.meta_path.insert(0, BlockBackends())
import plyunit
from plyunit import App, Animations, ShaderHandle, SpatialIndex, TemplateText, ports
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
