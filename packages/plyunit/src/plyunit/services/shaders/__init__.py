from typing import TYPE_CHECKING

from .uniform import uniform_components

if TYPE_CHECKING:
    from plyunit.backends.integrations import Shader, Shaders

__all__ = ("Shader", "Shaders", "uniform_components")


def __getattr__(name: str):
    if name not in {"Shader", "Shaders"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends import integrations

    value = getattr(integrations, name)
    globals()[name] = value
    return value
