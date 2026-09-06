"""Asset loading subpackage for the raylib backend (images, fonts, shaders)."""

from plyunit.backends.interfaces import IShaderLoader
from plyunit.backends.interfaces.i_assets_loader import IAssetsLoader
from plyunit.backends.interfaces.i_text import IFont

from . import assets_loader, font, shader
from .assets_loader import FILTER_MODE_MAP, WRAP_MODE_MAP


def AssetsLoader() -> IAssetsLoader:
    """Factory: return the ``assets_loader`` module as :class:`IAssetsLoader`.

    Returns:
        The active asset loader module.
    """
    return assets_loader


def get_assets_loader() -> IAssetsLoader:
    """Alias factory for the active asset loader module.

    Returns:
        The active asset loader module.
    """
    return assets_loader


def ShaderLoader() -> IShaderLoader:
    """Factory: return the ``shader`` module as :class:`IShaderLoader`.

    Returns:
        The active shader loader module.
    """
    return shader


def get_shader_loader() -> IShaderLoader:
    """Alias factory for the active shader loader module.

    Returns:
        The active shader loader module.
    """
    return shader


def Font() -> IFont:
    """Factory: return the ``font`` module as :class:`IFont`.

    Returns:
        The active font module.
    """
    return font


def get_font() -> IFont:
    """Alias factory for the active font module.

    Returns:
        The active font module.
    """
    return font


__all__ = (
    "FILTER_MODE_MAP",
    "WRAP_MODE_MAP",
    "AssetsLoader",
    "Font",
    "ShaderLoader",
    "get_assets_loader",
    "get_font",
    "get_shader_loader",
)
