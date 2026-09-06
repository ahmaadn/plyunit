from __future__ import annotations

import plyunit
import plyunit.assets as assets
import plyunit.backends.integrations as integrations
import plyunit.backends.interfaces as interfaces


def test_interfaces_export_current_font_contract() -> None:
    from plyunit.backends.interfaces.i_text import IFont

    assert interfaces.IFont is IFont
    assert "IFont" in interfaces.__all__
    assert "IFontBackend" not in interfaces.__all__
    assert "ITextBackend" not in interfaces.__all__


def test_asset_facade_exports_latest_loaders() -> None:
    assert plyunit.ShaderLoader is integrations.ShaderLoader
    assert plyunit.get_shader_loader is integrations.get_shader_loader
    assert "ShaderLoader" not in assets.__all__
    assert "get_shader_loader" not in assets.__all__


def test_root_text_exports_resolve_from_assets() -> None:
    assert plyunit.Text is assets.Text
    assert plyunit.TemplateText is assets.TemplateText


def test_input_exports_use_moved_service_facade() -> None:
    import plyunit.services.input as input_service

    assert plyunit.Input is input_service.Input
    assert "Input" in input_service.__all__


def test_integration_facade_routes_consolidated_drawing_exports() -> None:
    import plyunit.backends.integrations.raylib as raylib
    from plyunit.backends.integrations.raylib import drawing

    assert raylib.drawing is drawing
    assert "drawing" in raylib.__all__
    names = (
        "UnifiedBufferBatch",
        "get_batching_backend",
        "get_unified_buffer_batch",
        "StreamingTexture",
        "create_streaming_texture",
        "begin_stencil_mask",
    )
    for name in names:
        assert getattr(integrations, name) is getattr(drawing, name)
        assert name in integrations.__all__


def test_only_root_and_integration_facades_are_lazy() -> None:
    facades = (plyunit, integrations)
    eager_modules = (assets, __import__("plyunit.services.input", fromlist=["input"]))

    assert all(hasattr(facade, "__getattr__") for facade in facades)
    assert all(not hasattr(module, "__getattr__") for module in eager_modules)


def test_unknown_facade_attributes_raise_attribute_error() -> None:
    for facade in (plyunit, integrations):
        try:
            getattr(facade, "RemovedPlyunitApi")
        except AttributeError:
            continue
        raise AssertionError(f"{facade.__name__} accepted an unknown public name")
